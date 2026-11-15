"""Serial, durable experiment grids. Run with ``python -m rbp.experiments.runner``."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ortools
import yaml

from rbp.config import load_config
from rbp.generation import generate_extended, generate_simplified
from rbp.io.serialize import instance_to_dict
from rbp.metrics.runner import ALGORITHMS, RunRecord, run_algorithm
from rbp.selector.features import compute_features

ROOT = Path(__file__).resolve().parents[3]
KEY = ("kind", "algo", "size", "knob", "seed")
COLUMNS = [f.name for f in fields(RunRecord)] + [
    "kind", "size", "knob", "timestamp", "chosen_algorithm", "solver_status",
    "instance_hash", "conflict_density", "selector_score", "selector_reason",
]


def canonical(value: Any) -> str:
    """Stable JSON, including immutable domain objects in RunRecord metadata."""
    def encode(obj: Any) -> Any:
        if is_dataclass(obj):
            return {f.name: getattr(obj, f.name) for f in fields(obj)}
        if hasattr(obj, "items"):
            return dict(obj)
        raise TypeError(f"Cannot serialize {type(obj).__name__}")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def source_hash() -> str:
    return digest({
        str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
        for p in sorted((ROOT / "src" / "rbp").rglob("*.py"))
    })


def prepare_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Resolve and validate all settings before creating result files."""
    cfg = json.loads(canonical(cfg))
    identifier = cfg.get("id", "")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if not identifier or any(c not in allowed for c in identifier):
        raise ValueError("id must contain only letters, digits, hyphens and underscores")
    seeds = cfg.get("seeds", [])
    if not seeds or any(type(s) is not int or not 2000 <= s <= 2099 for s in seeds):
        raise ValueError("Evaluation experiments require evaluation seeds 2000–2099 only")
    sizes = cfg.get("sizes", [])
    if not sizes or any(type(n) is not int or n < 1 for n in sizes):
        raise ValueError("sizes must be positive integers")
    if len(set(seeds)) != len(seeds) or len(set(sizes)) != len(sizes):
        raise ValueError("Duplicate sizes or seeds")
    cfg["sizes"] = sorted(sizes)
    cfg["seeds"] = sorted(seeds)
    studies = cfg.get("studies", [])
    if not studies or len({s["kind"] for s in studies}) != len(studies):
        raise ValueError("Provide one study per instance kind")
    for study in studies:
        if study["kind"] not in ("simplified", "extended"):
            raise ValueError("Unknown instance kind")
        algorithms = study.get("algorithms", [])
        if not algorithms or len(set(algorithms)) != len(algorithms):
            raise ValueError("Provide unique algorithms")
        if set(algorithms) - ALGORITHMS.keys():
            raise ValueError("Unknown algorithm in study")
        study.setdefault("generator", {})
        study.setdefault("knobs", [{}])
        if not study["knobs"] or len({canonical(k) for k in study["knobs"]}) != len(study["knobs"]):
            raise ValueError("Provide unique knob levels")
        for knob in study["knobs"]:
            if {"n", "seed", "meta"} & (study["generator"].keys() | knob.keys()):
                raise ValueError("Generator knobs cannot override n, seed or meta")
    cfg.setdefault("repeats", 1)
    if type(cfg["repeats"]) is not int or cfg["repeats"] < 1:
        raise ValueError("repeats must be positive")
    cfg.setdefault("solver_options", {})
    ilp = cfg["solver_options"].setdefault("ILP-EXACT", {})
    ilp.setdefault("time_limit_s", 30.0)
    ilp.setdefault("deterministic_time_limit", 1.0)
    ilp.setdefault("num_workers", 1)
    ilp.setdefault("random_seed", 0)
    if ilp["num_workers"] != 1:
        raise ValueError("Experiments require single-worker CP-SAT for reproducibility")
    if ilp["time_limit_s"] <= 0 or ilp["deterministic_time_limit"] <= 0:
        raise ValueError("ILP limits must be positive")
    cfg.setdefault("selector_config", load_config(ROOT / "config" / "defaults.yaml"))
    threshold = json.loads((ROOT / "config" / "threshold.json").read_text())
    cfg.setdefault("selector_threshold", threshold["threshold"])
    return cfg


@contextmanager
def grid_lock(directory: Path):
    """OS-released lock: interrupted processes do not leave a stale lock."""
    with (directory / ".runner.lock").open("a+b") as handle:
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError("Result schema does not match this runner")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed results CSV; restore the last complete row before resuming")
    keys = [tuple(row[k] for k in KEY) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate run keys in results")
    return rows


def run_grid(cfg: dict[str, Any], output_root: str | Path = "results") -> Path:
    """Append one validated record per run; resume only compatible grids."""
    cfg = prepare_config(cfg)
    directory = Path(output_root) / cfg["id"]
    directory.mkdir(parents=True, exist_ok=True)
    with grid_lock(directory):
        return _run_grid(cfg, directory)


def _run_grid(cfg: dict[str, Any], directory: Path) -> Path:
    identity = {
        "schema_version": 1, "config_hash": digest(cfg), "source_hash": source_hash(),
        "python_version": platform.python_version(), "ortools_version": ortools.__version__,
    }
    meta_path = directory / "meta.json"
    if meta_path.exists():
        previous = json.loads(meta_path.read_text())
        if any(previous.get(k) != v for k, v in identity.items()):
            raise ValueError("Resume refused: configuration, source or environment changed")
    else:
        if (directory / "runs.csv").exists():
            raise ValueError("Cannot resume results without provenance")
        metadata = {
            **identity, "git_hash": git_output("rev-parse", "HEAD"),
            "git_dirty": bool(git_output("status", "--porcelain")),
            "timestamp": utc_now(), "platform": platform.platform(), "config": cfg,
        }
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    path = directory / "runs.csv"
    # A killed append may leave an incomplete final line. JSON metadata is escaped,
    # so every record occupies exactly one physical line; only the tail is discarded.
    if path.exists():
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            path.write_bytes(data[:data.rfind(b"\n") + 1])
    rows = read_rows(path)
    completed = {tuple(row[k] for k in KEY) for row in rows}
    stopped = {
        (r["kind"], r["knob"], int(r["seed"]))
        for r in rows if r["algo"] == "ILP-EXACT" and r["optimal"] != "True"
    } if cfg.get("stop_ilp_after_limit", False) else set()
    with path.open("a", newline="", encoding="utf-8") as handle, (
        directory / "failures.log"
    ).open("a", encoding="utf-8") as failures:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if not rows:
            if handle.tell() == 0:
                writer.writeheader()
                handle.flush()
        for study in cfg["studies"]:
            kind = study["kind"]
            generator = generate_simplified if kind == "simplified" else generate_extended
            for size in cfg["sizes"]:
                for knobs in study["knobs"]:
                    knob = canonical(knobs)
                    for seed in cfg["seeds"]:
                        pending = [a for a in study["algorithms"] if
                                   (kind, a, str(size), knob, str(seed)) not in completed]
                        if not pending:
                            continue
                        instance = None
                        error = None
                        try:
                            instance = generator(n=size, seed=seed, **{
                                **study["generator"], **knobs,
                            })
                            instance_hash = digest(instance_to_dict(instance))
                            density = compute_features(instance).f2_conflict_density
                        except Exception as exc:
                            error = f"Generation: {type(exc).__name__}: {exc}"
                        for algorithm in pending:
                            if error:
                                rec = failure_record(algorithm, size, seed, error)
                            elif algorithm == "ILP-EXACT" and (kind, knob, seed) in stopped:
                                rec = failure_record(algorithm, size, seed,
                                                     "Earlier size exhausted ILP budget",
                                                     status="SKIPPED_LIMIT")
                            else:
                                options = cfg["solver_options"].get(algorithm, {})
                                if algorithm == "SELECTOR":
                                    options = {
                                        "solver_options": cfg["solver_options"],
                                        "config": cfg["selector_config"],
                                        "threshold": cfg["selector_threshold"],
                                    }
                                try:
                                    rec = run_algorithm(algorithm, instance,
                                                        repeats=cfg["repeats"], **options)
                                except Exception as exc:
                                    rec = failure_record(algorithm, size, seed,
                                                         f"{type(exc).__name__}: {exc}")
                            if (algorithm == "ILP-EXACT" and not rec.optimal
                                    and cfg.get("stop_ilp_after_limit", False)):
                                stopped.add((kind, knob, seed))
                            row = rec.as_dict()
                            decision = rec.meta.get("decision")
                            row.update(
                                kind=kind, size=size, knob=knob, timestamp=utc_now(),
                                chosen_algorithm=decision.algorithm if decision else algorithm,
                                solver_status=rec.meta.get("status", ""),
                                instance_hash=instance_hash if not error else "",
                                conflict_density=density if not error else "",
                                selector_score=decision.score if decision else "",
                                selector_reason=decision.reason if decision else "",
                            )
                            row["meta"] = canonical(rec.meta)
                            writer.writerow(row)
                            handle.flush()
                            os.fsync(handle.fileno())
                            if rec.status != "OK" or rec.violations or rec.anomaly:
                                failures.write(canonical({k: row[k] for k in KEY} | {
                                    "status": rec.status, "violations": rec.violations,
                                    "anomaly": rec.anomaly, "error": rec.meta.get("error"),
                                    "solver_status": row["solver_status"],
                                }) + "\n")
                                failures.flush()
                            print(f"{cfg['id']} {kind} n={size} {knob} seed={seed} "
                                  f"{algorithm}: {rec.status} objective={rec.objective} "
                                  f"({rec.runtime_s:.3f}s)", flush=True)
    return path


def failure_record(algo: str, n: int, seed: int, error: str,
                   status: str = "ERROR") -> RunRecord:
    return RunRecord(algo, n, seed, 0, 0.0, 0, 0.0, 0, status, False, None, False,
                     {"error": error})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("results"))
    parser.add_argument("--dry-run", action="store_true",
                        help="Execute a tiny end-to-end grid in a separate <id>-dry-run directory")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.dry_run:
        cfg["id"] += "-dry-run"
        cfg["sizes"] = [min(8, min(cfg["sizes"]))]
        cfg["seeds"] = [cfg["seeds"][0]]
        for study in cfg["studies"]:
            study["knobs"] = study.get("knobs", [{}])[:1]
    print(run_grid(cfg, args.output_root))


if __name__ == "__main__":
    main()
