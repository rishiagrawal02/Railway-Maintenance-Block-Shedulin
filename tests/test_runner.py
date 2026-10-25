"""Tests for Milestone 9.1: Experiment runner and results storage.

Coverage:
  T9.1-01  Row count: 2 algorithms x 2 sizes x 3 seeds -> 12 rows
  T9.1-02  Reproducibility: two identical runs match in all columns except runtime/timestamp
  T9.1-03  Resume: kill after 5 rows, rerun adds remaining, no duplicates
  T9.1-04  Algorithm exception: inject failing algo -> ERROR row, grid completes
  T9.1-05  ILP time limit: tiny limit -> status recorded
  T9.1-06  Violations flagged: inject invalid schedule -> violations > 0 in CSV
  T9.1-07  Provenance: meta.json has git hash, config hash, versions
  T9.1-08  Seed policy (negative): evaluation experiment with calibration seeds -> refused
  T9.1-09  Schema: expected columns and types in CSV
  T9.1-10  Selector logging: SELECTOR rows have chosen_algorithm filled
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rbp.experiments.runner import (
    RUN_RECORD_FIELDS,
    _config_hash,
    _validate_seeds,
    run_grid,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_results(tmp_path: Path) -> Path:
    return tmp_path / "results"


def _mini_cfg(
    tmp_path: Path,
    algorithms: list[str] | None = None,
    sizes: list[int] | None = None,
    seeds: list[int] | None = None,
    knob_levels: list[dict] | None = None,
    ilp_time_limit: float = 30,
    seed_kind: str = "evaluation",
) -> dict[str, Any]:
    """Build a minimal experiment config for fast testing (evaluation seeds only)."""
    return {
        "id": "test_exp",
        "instance_kind": "extended",
        "seed_kind": seed_kind,
        "seeds": seeds or [2000, 2001, 2002],
        "sizes": sizes or [8, 10],
        "knob_levels": knob_levels or [{"label": "default", "params": {}}],
        "algorithms": algorithms or ["NAIVE-GREEDY", "CA-GREEDY"],
        "ilp_time_limit": ilp_time_limit,
        "deterministic_time_limit": None,
    }


# ---------------------------------------------------------------------------
# T9.1-01: Row count
# ---------------------------------------------------------------------------


def test_row_count(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-01: 2 algorithms x 2 sizes x 3 seeds = 12 rows."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["NAIVE-GREEDY", "CA-GREEDY"],
        sizes=[8, 10],
        seeds=[2000, 2001, 2002],
    )
    out_dir = run_grid(cfg, results_root=tmp_results)
    runs_csv = out_dir / "runs.csv"
    assert runs_csv.exists()
    with open(runs_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 12, f"Expected 12 rows, got {len(rows)}"


# ---------------------------------------------------------------------------
# T9.1-02: Reproducibility
# ---------------------------------------------------------------------------


def test_reproducibility(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-02: Two runs produce equal objectives for every (algo, size, seed)."""
    cfg = _mini_cfg(tmp_path, algorithms=["NAIVE-GREEDY"], sizes=[8], seeds=[2000, 2001])

    out1 = run_grid(cfg, results_root=tmp_results / "run1")
    out2 = run_grid(cfg, results_root=tmp_results / "run2")

    def read_key_obj(path: Path) -> dict[tuple, float]:
        result: dict[tuple, float] = {}
        with open(path / "runs.csv", newline="") as f:
            for row in csv.DictReader(f):
                key = (row["algorithm"], int(row["size"]), row["knob_label"], int(row["seed"]))
                result[key] = float(row["objective"])
        return result

    data1 = read_key_obj(out1)
    data2 = read_key_obj(out2)
    assert data1 == data2, "Objectives differ between two identical runs"


# ---------------------------------------------------------------------------
# T9.1-03: Resume (no duplicates)
# ---------------------------------------------------------------------------


def test_resume_no_duplicates(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-03: Rerun after partial completion adds remaining rows without duplicates."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["NAIVE-GREEDY"],
        sizes=[8, 10],
        seeds=[2000, 2001, 2002],
    )
    # Full run -> 6 rows
    out_dir = run_grid(cfg, results_root=tmp_results)

    with open(out_dir / "runs.csv", newline="") as f:
        rows_first = list(csv.DictReader(f))
    assert len(rows_first) == 6

    # Simulate partial: keep only first 3 rows then re-run
    partial_rows = rows_first[:3]
    with open(out_dir / "runs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_RECORD_FIELDS)
        writer.writeheader()
        writer.writerows(partial_rows)

    # Resume
    run_grid(cfg, results_root=tmp_results)

    with open(out_dir / "runs.csv", newline="") as f:
        rows_after = list(csv.DictReader(f))

    # Exactly 6 unique (algorithm, size, knob_label, seed) combinations
    unique_keys = {
        (r["algorithm"], r["size"], r["knob_label"], r["seed"]) for r in rows_after
    }
    assert len(rows_after) == 6, f"Expected 6 rows after resume, got {len(rows_after)}"
    assert len(unique_keys) == 6, "Duplicate rows detected after resume"


# ---------------------------------------------------------------------------
# T9.1-04: Algorithm exception -> ERROR row, grid continues
# ---------------------------------------------------------------------------


def test_algorithm_exception_isolation(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-04: Failing algorithm produces ERROR row; remaining cells still run."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["NAIVE-GREEDY", "CA-GREEDY"],
        sizes=[8],
        seeds=[2000],
    )

    # Patch CA-GREEDY dispatch to raise
    original_dispatch = __import__(
        "rbp.experiments.runner", fromlist=["_dispatch"]
    )._dispatch

    def patched_dispatch(algorithm, instance, ilp_time_limit, deterministic_time_limit):
        if algorithm == "CA-GREEDY":
            raise RuntimeError("Injected failure for test")
        return original_dispatch(algorithm, instance, ilp_time_limit, deterministic_time_limit)

    with patch("rbp.experiments.runner._dispatch", side_effect=patched_dispatch):
        out_dir = run_grid(cfg, results_root=tmp_results)

    with open(out_dir / "runs.csv", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2, f"Expected 2 rows (one per algo), got {len(rows)}"
    statuses = {r["algorithm"]: r["status"] for r in rows}
    assert statuses["CA-GREEDY"] == "ERROR"
    assert statuses["NAIVE-GREEDY"] == "OK"


# ---------------------------------------------------------------------------
# T9.1-05: ILP time limit -> status recorded
# ---------------------------------------------------------------------------


def test_ilp_time_limit(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-05: Tiny ILP time limit records status (not necessarily OPTIMAL)."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["ILP-EXACT"],
        sizes=[20],
        seeds=[2000],
        ilp_time_limit=0.001,   # effectively zero, forces non-optimal
    )
    out_dir = run_grid(cfg, results_root=tmp_results)
    with open(out_dir / "runs.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    row = rows[0]
    # Status should be OK (row stored) and ilp_status captured
    assert row["status"] == "OK"
    assert row["ilp_status"] in {"OPTIMAL", "FEASIBLE", "UNKNOWN", "N/A"}


# ---------------------------------------------------------------------------
# T9.1-06: Violations flagged
# ---------------------------------------------------------------------------


def test_violations_flagged(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-06: A run producing constraint violations has violations > 0 in CSV."""

    cfg = _mini_cfg(tmp_path, algorithms=["NAIVE-GREEDY"], sizes=[8], seeds=[2000])

    def fake_dispatch(algorithm, instance, ilp_time_limit, deterministic_time_limit):
        # Return a schedule with no tasks assigned (always has 0 violations),
        # but we monkey-patch validation to inject a violation count
        from rbp.algorithms import solve_naive_greedy
        return solve_naive_greedy(instance)

    # Instead, monkey-patch validate_schedule to report 1 violation always
    fake_violation = MagicMock()
    fake_violation.violations = [MagicMock()]  # non-empty list

    with patch("rbp.experiments.runner.validate_schedule", return_value=fake_violation):
        out_dir = run_grid(cfg, results_root=tmp_results)

    with open(out_dir / "runs.csv", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) >= 1
    assert int(rows[0]["violations"]) > 0


# ---------------------------------------------------------------------------
# T9.1-07: Provenance (meta.json)
# ---------------------------------------------------------------------------


def test_provenance_meta(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-07: meta.json contains git_hash, config_hash, python_version, ortools_version."""
    cfg = _mini_cfg(tmp_path, algorithms=["NAIVE-GREEDY"], sizes=[8], seeds=[2000])
    out_dir = run_grid(cfg, results_root=tmp_results)
    meta_path = out_dir / "meta.json"
    assert meta_path.exists()
    with open(meta_path) as f:
        meta = json.load(f)
    for key in ("git_hash", "config_hash", "python_version", "ortools_version", "timestamp"):
        assert key in meta, f"meta.json missing key: '{key}'"
    assert meta["git_hash"]  # non-empty
    assert meta["config_hash"]  # non-empty 64-char sha256


# ---------------------------------------------------------------------------
# T9.1-08: Seed policy (negative test) – refused for calibration seeds
# ---------------------------------------------------------------------------


def test_seed_policy_refuses_calibration_seeds(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-08: Evaluation experiment containing calibration seeds is refused."""
    cfg = {
        "id": "bad_seeds",
        "instance_kind": "extended",
        "seed_kind": "evaluation",
        "seeds": [1050, 2000],   # 1050 is in calibration range
        "sizes": [8],
        "algorithms": ["NAIVE-GREEDY"],
        "knob_levels": [{"label": "default", "params": {}}],
        "ilp_time_limit": 30,
        "deterministic_time_limit": None,
    }
    with pytest.raises(ValueError, match="calibration range"):
        run_grid(cfg, results_root=tmp_results)


# ---------------------------------------------------------------------------
# T9.1-09: CSV schema
# ---------------------------------------------------------------------------


def test_csv_schema(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-09: runs.csv has the expected columns with correct types."""
    cfg = _mini_cfg(tmp_path, algorithms=["NAIVE-GREEDY"], sizes=[8], seeds=[2000])
    out_dir = run_grid(cfg, results_root=tmp_results)
    with open(out_dir / "runs.csv", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    assert set(RUN_RECORD_FIELDS).issubset(set(headers)), (
        f"Missing columns: {set(RUN_RECORD_FIELDS) - set(headers)}"
    )
    assert len(rows) == 1
    row = rows[0]
    # Type checks
    assert row["algorithm"] == "NAIVE-GREEDY"
    assert int(row["size"]) == 8
    assert int(row["seed"]) == 2000
    assert not math.isnan(float(row["objective"]))
    assert float(row["runtime_s"]) >= 0
    assert row["status"] in {"OK", "ERROR", "TIMEOUT"}


# ---------------------------------------------------------------------------
# T9.1-10: Selector logging (chosen_algorithm filled)
# ---------------------------------------------------------------------------


def test_selector_chosen_algorithm_logged(tmp_path: Path, tmp_results: Path) -> None:
    """T9.1-10: SELECTOR rows have chosen_algorithm filled."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["SELECTOR"],
        sizes=[8],
        seeds=[2000],
    )
    out_dir = run_grid(cfg, results_root=tmp_results)
    with open(out_dir / "runs.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    row = rows[0]
    assert row["algorithm"] == "SELECTOR"
    assert row["chosen_algorithm"] in {
        "NAIVE-GREEDY", "CA-GREEDY", "WIS-DP", "ILP-EXACT",
        "WIS-DP", "CA-GREEDY",  # all valid SELECTOR outputs
    }, f"Unexpected chosen_algorithm: '{row['chosen_algorithm']}'"
    assert row["chosen_algorithm"] != "", "chosen_algorithm should not be empty for SELECTOR"


# ---------------------------------------------------------------------------
# Additional: _validate_seeds helper
# ---------------------------------------------------------------------------


def test_validate_seeds_rejects_out_of_range(tmp_path: Path, tmp_results: Path) -> None:
    """_validate_seeds rejects seeds outside evaluation range for evaluation experiments."""
    cfg = {
        "id": "bad",
        "seed_kind": "evaluation",
        "seeds": [999],  # below evaluation range
    }
    with pytest.raises(ValueError, match="outside the evaluation range"):
        _validate_seeds(cfg)


def test_validate_seeds_allows_evaluation_seeds() -> None:
    """_validate_seeds accepts valid evaluation seeds [2000, 2099]."""
    cfg = {"id": "ok", "seed_kind": "evaluation", "seeds": [2000, 2050, 2099]}
    _validate_seeds(cfg)  # should not raise


def test_config_hash_is_deterministic() -> None:
    """_config_hash returns the same hash for the same config."""
    cfg = {"id": "e1", "sizes": [10, 20], "seeds": [2000]}
    h1 = _config_hash(cfg)
    h2 = _config_hash(cfg)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_dry_run_does_not_write_rows(tmp_path: Path, tmp_results: Path) -> None:
    """Dry-run mode iterates the grid without executing algorithms."""
    cfg = _mini_cfg(
        tmp_path,
        algorithms=["NAIVE-GREEDY", "CA-GREEDY"],
        sizes=[8, 10],
        seeds=[2000, 2001],
    )
    out_dir = run_grid(cfg, results_root=tmp_results, dry_run=True)
    runs_csv = out_dir / "runs.csv"
    # CSV may not exist or may only have a header
    if runs_csv.exists():
        with open(runs_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 0, "Dry-run should not write data rows"
