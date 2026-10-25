"""Reproducible, resumable experiment grid runner (Milestone 9.1).

run_grid(cfg) iterates over every (algorithm, size, knob, seed) combination defined
in an experiment config dict and writes:
  - results/<id>/runs.csv        One row per run (RunRecord)
  - results/<id>/meta.json       Provenance: git hash, config hash, versions, timestamp
  - results/<id>/failures.log    One line per failure with traceback

Design constraints:
  - Serial execution (parallel timing would distort runtime comparisons)
  - Resume: skips rows already present for the same (algorithm, size, knob, seed)
  - Failure isolation: one failing run is recorded and the grid continues
  - Evaluation experiments may only use evaluation seeds [2000, 2099]
  - SELECTOR is a registered algorithm that logs the algorithm it chose
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from rbp.algorithms import (
    AlgoResult,
    solve_ca_greedy,
    solve_ilp_exact,
    solve_naive_greedy,
    solve_wis_dp,
)
from rbp.generation import generate_extended, generate_simplified
from rbp.selector import run_selected
from rbp.validation import validate_schedule

# ------------------------------------------------------------------
# Seed policy constants (mirrors calibration.py)
# ------------------------------------------------------------------
CALIBRATION_SEED_MIN = 1000
CALIBRATION_SEED_MAX = 1099
EVALUATION_SEED_MIN = 2000
EVALUATION_SEED_MAX = 2099

# ------------------------------------------------------------------
# Registered algorithms
# ------------------------------------------------------------------
ALGORITHM_KEYS = ["NAIVE-GREEDY", "CA-GREEDY", "WIS-DP", "ILP-EXACT", "SELECTOR"]

# ------------------------------------------------------------------
# CSV schema
# ------------------------------------------------------------------
RUN_RECORD_FIELDS = [
    "experiment_id",
    "algorithm",
    "size",
    "knob_label",
    "seed",
    "objective",
    "runtime_s",
    "status",         # OK | ERROR | TIMEOUT
    "ilp_status",     # OPTIMAL | FEASIBLE | UNKNOWN | N/A
    "violations",
    "chosen_algorithm",  # filled for SELECTOR rows
    "timestamp",
]


@dataclass
class RunRecord:
    """One row in runs.csv."""

    experiment_id: str
    algorithm: str
    size: int
    knob_label: str
    seed: int
    objective: float
    runtime_s: float
    status: str            # OK | ERROR | TIMEOUT
    ilp_status: str        # OPTIMAL | FEASIBLE | UNKNOWN | N/A
    violations: int
    chosen_algorithm: str  # empty for non-SELECTOR rows
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_git_hash() -> str:
    """Return HEAD commit hash, or 'unknown'."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def _get_git_dirty() -> bool:
    """Return True if the working tree has uncommitted changes."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        return bool(res.stdout.strip())
    except Exception:
        return False


def _config_hash(cfg: dict[str, Any]) -> str:
    """Deterministic SHA-256 of the config dict (sorted JSON)."""
    serialized = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()


def _get_ortools_version() -> str:
    try:
        from ortools import __version__ as v  # type: ignore[attr-defined]
        return v
    except Exception:
        return "unknown"


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ------------------------------------------------------------------
# Seed policy enforcement
# ------------------------------------------------------------------

def _validate_seeds(cfg: dict[str, Any]) -> None:
    """Refuse evaluation experiments that include calibration seeds."""
    seed_kind = cfg.get("seed_kind", "")
    seeds: list[int] = cfg.get("seeds", [])
    if seed_kind == "evaluation":
        bad = [s for s in seeds if CALIBRATION_SEED_MIN <= s <= CALIBRATION_SEED_MAX]
        if bad:
            raise ValueError(
                f"Experiment '{cfg.get('id')}' uses seed_kind='evaluation' "
                f"but seeds {bad} overlap with calibration range "
                f"[{CALIBRATION_SEED_MIN}, {CALIBRATION_SEED_MAX}]."
            )
    # Also reject seeds clearly outside evaluation range for evaluation experiments
    if seed_kind == "evaluation":
        out_of_range = [
            s for s in seeds
            if not (EVALUATION_SEED_MIN <= s <= EVALUATION_SEED_MAX)
        ]
        if out_of_range:
            raise ValueError(
                f"Experiment '{cfg.get('id')}' uses seed_kind='evaluation' "
                f"but seeds {out_of_range} are outside the evaluation range "
                f"[{EVALUATION_SEED_MIN}, {EVALUATION_SEED_MAX}]."
            )


# ------------------------------------------------------------------
# Instance generation
# ------------------------------------------------------------------

def _generate_instance(kind: str, n: int, seed: int, knob_params: dict[str, Any]):
    """Generate an instance of the given kind with optional knob_params."""
    if kind == "simplified":
        return generate_simplified(n=n, seed=seed)
    elif kind == "extended":
        return generate_extended(n=n, seed=seed, **knob_params)
    else:
        raise ValueError(f"Unknown instance_kind: '{kind}'")


# ------------------------------------------------------------------
# Single-run execution
# ------------------------------------------------------------------

def _run_single(
    exp_id: str,
    algorithm: str,
    instance,
    size: int,
    knob_label: str,
    seed: int,
    ilp_time_limit: float,
    deterministic_time_limit: float | None,
) -> RunRecord:
    """Execute one (algorithm, instance) pair and return a RunRecord."""
    t0 = time.perf_counter()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        result = _dispatch(
            algorithm=algorithm,
            instance=instance,
            ilp_time_limit=ilp_time_limit,
            deterministic_time_limit=deterministic_time_limit,
        )

        runtime = time.perf_counter() - t0

        # Validate schedule
        vreport = validate_schedule(instance, result.schedule)
        violations = len(vreport.violations)

        # Extract ILP status
        ilp_status = result.meta.get("status", "N/A")

        # Extract chosen algorithm for SELECTOR rows
        chosen = ""
        if algorithm == "SELECTOR":
            dec = result.meta.get("decision")
            if dec is not None:
                chosen = dec.algorithm

        return RunRecord(
            experiment_id=exp_id,
            algorithm=algorithm,
            size=size,
            knob_label=knob_label,
            seed=seed,
            objective=float(result.objective),
            runtime_s=round(runtime, 6),
            status="OK",
            ilp_status=str(ilp_status),
            violations=violations,
            chosen_algorithm=chosen,
            timestamp=ts,
        )

    except Exception:
        runtime = time.perf_counter() - t0
        return RunRecord(
            experiment_id=exp_id,
            algorithm=algorithm,
            size=size,
            knob_label=knob_label,
            seed=seed,
            objective=float("nan"),
            runtime_s=round(runtime, 6),
            status="ERROR",
            ilp_status="N/A",
            violations=-1,
            chosen_algorithm="",
            timestamp=ts,
        )


def _dispatch(
    algorithm: str,
    instance,
    ilp_time_limit: float,
    deterministic_time_limit: float | None,
) -> AlgoResult:
    """Route to the correct algorithm function."""
    if algorithm == "NAIVE-GREEDY":
        return solve_naive_greedy(instance)
    elif algorithm == "CA-GREEDY":
        return solve_ca_greedy(instance)
    elif algorithm == "WIS-DP":
        return solve_wis_dp(instance)
    elif algorithm == "ILP-EXACT":
        kwargs: dict[str, Any] = {"time_limit_s": ilp_time_limit}
        if deterministic_time_limit is not None:
            kwargs["deterministic_time_limit"] = float(deterministic_time_limit)
        return solve_ilp_exact(instance, **kwargs)
    elif algorithm == "SELECTOR":
        return run_selected(instance)
    else:
        raise ValueError(f"Unknown algorithm: '{algorithm}'")


# ------------------------------------------------------------------
# Resume support
# ------------------------------------------------------------------

def _load_existing_keys(runs_csv: Path) -> set[tuple[str, int, str, int]]:
    """Return set of (algorithm, size, knob_label, seed) already in runs.csv."""
    if not runs_csv.exists():
        return set()
    keys: set[tuple[str, int, str, int]] = set()
    with open(runs_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((row["algorithm"], int(row["size"]), row["knob_label"], int(row["seed"])))
    return keys


# ------------------------------------------------------------------
# run_grid
# ------------------------------------------------------------------

def run_grid(
    cfg: dict[str, Any],
    results_root: str | Path = "results",
    dry_run: bool = False,
) -> Path:
    """Execute the full experiment grid defined by cfg.

    Parameters
    ----------
    cfg:
        Experiment configuration dict (loaded from YAML).
    results_root:
        Base directory for results (default: 'results/').
    dry_run:
        If True, iterate the grid without executing any algorithm.

    Returns
    -------
    Path to the experiment results directory.
    """
    exp_id: str = cfg["id"]
    instance_kind: str = cfg.get("instance_kind", "extended")
    seeds: list[int] = [int(s) for s in cfg.get("seeds", [])]
    sizes: list[int] = [int(s) for s in cfg.get("sizes", [])]
    algorithms: list[str] = cfg.get("algorithms", [])
    knob_levels: list[dict[str, Any]] = cfg.get("knob_levels", [{"label": "default", "params": {}}])
    ilp_time_limit: float = float(cfg.get("ilp_time_limit", 120))
    deterministic_time_limit = cfg.get("deterministic_time_limit", None)
    if deterministic_time_limit is not None:
        deterministic_time_limit = float(deterministic_time_limit)

    # Seed policy check
    _validate_seeds(cfg)

    # Prepare output directory
    out_dir = Path(results_root) / exp_id
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_csv = out_dir / "runs.csv"
    meta_json = out_dir / "meta.json"
    failures_log = out_dir / "failures.log"

    # Set up failure logger
    flogger = logging.getLogger(f"rbp.experiments.failures.{exp_id}")
    flogger.setLevel(logging.ERROR)
    if not flogger.handlers:
        fh = logging.FileHandler(str(failures_log), mode="a", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        flogger.addHandler(fh)

    # Resume: load existing run keys
    existing_keys = _load_existing_keys(runs_csv)

    # Open CSV for appending (write header only if new file)
    file_exists = runs_csv.exists() and runs_csv.stat().st_size > 0
    csv_file = open(runs_csv, "a", newline="", encoding="utf-8")  # noqa: SIM115
    writer = csv.DictWriter(csv_file, fieldnames=RUN_RECORD_FIELDS)
    if not file_exists:
        writer.writeheader()

    new_rows = 0
    skipped = 0
    errors = 0

    try:
        for algorithm in algorithms:
            for size in sizes:
                for knob in knob_levels:
                    knob_label: str = knob.get("label", "default")
                    knob_params: dict[str, Any] = knob.get("params", {})

                    for seed in seeds:
                        key = (algorithm, size, knob_label, seed)
                        if key in existing_keys:
                            skipped += 1
                            continue

                        if dry_run:
                            # Just log the cell without running
                            print(
                                f"[DRY-RUN] {exp_id}: {algorithm} n={size} "
                                f"knob={knob_label} seed={seed}"
                            )
                            new_rows += 1
                            continue

                        # Generate instance
                        try:
                            instance = _generate_instance(
                                kind=instance_kind,
                                n=size,
                                seed=seed,
                                knob_params=knob_params,
                            )
                        except Exception as e:
                            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            msg = (
                                f"GENERATION_ERROR exp={exp_id} algo={algorithm} "
                                f"n={size} knob={knob_label} seed={seed}: {e}\n"
                                + traceback.format_exc()
                            )
                            flogger.error(msg)
                            record = RunRecord(
                                experiment_id=exp_id,
                                algorithm=algorithm,
                                size=size,
                                knob_label=knob_label,
                                seed=seed,
                                objective=float("nan"),
                                runtime_s=0.0,
                                status="ERROR",
                                ilp_status="N/A",
                                violations=-1,
                                chosen_algorithm="",
                                timestamp=ts,
                            )
                            writer.writerow(record.as_dict())
                            csv_file.flush()
                            errors += 1
                            existing_keys.add(key)
                            continue

                        # Execute run with failure isolation
                        record = _run_single(
                            exp_id=exp_id,
                            algorithm=algorithm,
                            instance=instance,
                            size=size,
                            knob_label=knob_label,
                            seed=seed,
                            ilp_time_limit=ilp_time_limit,
                            deterministic_time_limit=deterministic_time_limit,
                        )

                        if record.status == "ERROR":
                            errors += 1
                            # Write detailed failure info to failures.log
                            flogger.error(
                                f"RUN_ERROR exp={exp_id} algo={algorithm} "
                                f"n={size} knob={knob_label} seed={seed}"
                            )

                        writer.writerow(record.as_dict())
                        csv_file.flush()
                        new_rows += 1
                        existing_keys.add(key)

    finally:
        csv_file.close()

    # Write provenance meta.json
    meta = {
        "experiment_id": exp_id,
        "git_hash": _get_git_hash(),
        "git_dirty": _get_git_dirty(),
        "config_hash": _config_hash(cfg),
        "python_version": sys.version,
        "ortools_version": _get_ortools_version(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "new_rows": new_rows,
        "skipped_rows": skipped,
        "error_rows": errors,
    }
    with open(meta_json, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return out_dir


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """CLI: python -m rbp.experiments.runner <config.yaml> [--dry-run]."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run an experiment grid from a YAML config file."
    )
    parser.add_argument("config", help="Path to experiment YAML config file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Iterate the grid without executing algorithms.",
    )
    parser.add_argument(
        "--results-root",
        default="results",
        help="Base directory for results (default: results/).",
    )
    args = parser.parse_args(argv)

    cfg = _load_yaml(Path(args.config))
    out_dir = run_grid(cfg, results_root=args.results_root, dry_run=args.dry_run)
    print(f"Results written to: {out_dir}")


if __name__ == "__main__":
    main()
