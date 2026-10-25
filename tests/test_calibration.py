"""Tests for selector calibration, deterministic labelling, and held-out evaluation
(Milestone 8.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rbp.algorithms.ilp_exact import solve_ilp_exact
from rbp.generation import generate_extended
from rbp.selector.calibration import (
    calibrate_threshold,
    run_held_out_evaluation,
    validate_calibration_seeds,
    verify_threshold_release,
    write_selector_eval_report,
    write_threshold_json,
)


def test_t8_3_01_grid_search_synthetic_labels():
    """T8.3-01: Grid search on scores [0.1, 0.2, 0.8, 0.9] and labels [1, 1, 0, 0].

    Expected result: theta in [0.2, 0.8), accuracy 1.0.
    """
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [1, 1, 0, 0]

    theta, acc = calibrate_threshold(scores, labels, step=0.01)

    assert 0.2 <= theta < 0.8
    assert acc == pytest.approx(1.0)


def test_t8_3_02_all_labels_equal():
    """T8.3-02: All labels equal (all 1) returns a valid theta without crash."""
    scores = [0.1, 0.3, 0.5, 0.7]
    labels = [1, 1, 1, 1]

    theta, acc = calibrate_threshold(scores, labels, step=0.01)

    assert 0.0 <= theta <= 1.0
    assert acc == pytest.approx(1.0)


def test_t8_3_03_seed_leakage_negative():
    """T8.3-03: Passing an evaluation seed (2000-2099) to calibration raises ValueError."""
    cal_seeds_ok = [1001, 1002, 1003]
    validate_calibration_seeds(cal_seeds_ok)  # no error

    cal_seeds_leaked = [1001, 2005, 1003]
    with pytest.raises(ValueError, match="Data leakage detected"):
        validate_calibration_seeds(cal_seeds_leaked)


def test_t8_3_04_determinism(tmp_path: Path):
    """T8.3-04: Running calibration logic on tiny suite twice yields identical results."""
    scores = [0.15, 0.35, 0.65, 0.85]
    labels = [1, 1, 0, 0]
    alpha = [0.2, 0.2, 0.2, 0.2, 0.2]

    theta1, _ = calibrate_threshold(scores, labels, step=0.01)
    file1 = tmp_path / "t1.json"
    d1 = write_threshold_json(
        file1, theta1, alpha, [1000, 1003], {"limit": 1.0}, version=1,
    )

    theta2, _ = calibrate_threshold(scores, labels, step=0.01)
    file2 = tmp_path / "t2.json"
    d2 = write_threshold_json(
        file2, theta2, alpha, [1000, 1003], {"limit": 1.0}, version=1,
    )

    assert theta1 == theta2
    # Exclude dynamic timestamp
    del d1["date"]
    del d2["date"]
    assert d1 == d2


def test_t8_3_05_deterministic_ilp_limit():
    """T8.3-05: Same instance solved twice with deterministic limit gives same status and
    objective.
    """
    inst = generate_extended(n=10, seed=1005)

    res1 = solve_ilp_exact(inst, deterministic_time_limit=1.0, num_workers=1)
    res2 = solve_ilp_exact(inst, deterministic_time_limit=1.0, num_workers=1)

    assert res1.meta["status"] == res2.meta["status"]
    assert res1.objective == res2.objective
    assert res1.schedule.starts == res2.schedule.starts


def test_t8_3_06_threshold_file_schema(tmp_path: Path):
    """T8.3-06: Calibrated file is valid, version >= 1, alpha sums to 1.0."""
    out_file = tmp_path / "threshold.json"
    alpha = [0.2, 0.2, 0.2, 0.2, 0.2]
    write_threshold_json(
        out_file, threshold=0.45, alpha=alpha,
        calibration_seeds=[1000, 1010], labelling_limits={"max_det_time": 5.0},
        version=1,
    )

    loaded = verify_threshold_release(out_file)
    assert loaded["version"] >= 1
    assert loaded["threshold"] == pytest.approx(0.45)
    assert len(loaded["alpha"]) == 5
    assert sum(loaded["alpha"]) == pytest.approx(1.0)


def test_t8_3_07_placeholder_rejected_for_release(tmp_path: Path):
    """T8.3-07: Version 0 placeholder is rejected with a clear error message."""
    placeholder_file = tmp_path / "placeholder.json"
    placeholder_data = {
        "version": 0,
        "threshold": 0.5,
        "alpha": [0.2, 0.2, 0.2, 0.2, 0.2],
    }
    placeholder_file.write_text(json.dumps(placeholder_data), encoding="utf-8")

    with pytest.raises(ValueError, match="version = 0"):
        verify_threshold_release(placeholder_file)


def test_t8_3_08_held_out_report(tmp_path: Path):
    """T8.3-08: Held-out evaluation report file is written with accuracy and baseline."""
    eval_seeds = [2001, 2002, 2003, 2004]
    alpha = [0.2, 0.2, 0.2, 0.2, 0.2]

    metrics = run_held_out_evaluation(
        eval_seeds=eval_seeds,
        threshold=0.5,
        alpha=alpha,
        deterministic_limit=0.5,
    )

    report_path = tmp_path / "reports" / "selector_eval.md"
    content = write_selector_eval_report(
        report_path=report_path,
        eval_metrics=metrics,
        threshold=0.5,
        alpha=alpha,
    )

    assert report_path.exists()
    assert "Selector Accuracy" in content
    assert "Majority-Class Baseline" in content
    assert "Evaluation Samples" in content
