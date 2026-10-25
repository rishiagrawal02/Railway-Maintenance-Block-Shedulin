"""Tests for threshold-based algorithm selector and routing rules (Milestone 8.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rbp.generation import generate_extended, generate_simplified
from rbp.metrics.runner import ALGORITHMS
from rbp.models.instance import Instance
from rbp.selector import Decision, run_selected, select
from rbp.validation.validator import validate_schedule


def _make_sample_simplified() -> Instance:
    """Small simplified instance fixture."""
    return generate_simplified(n=4, seed=42)


def _make_sample_extended() -> Instance:
    """Small extended instance fixture."""
    return generate_extended(n=6, seed=42)


def test_t8_2_01_score_equals_threshold_edge():
    """T8.2-01: When score == threshold, routes to exact solver."""
    inst_simp = _make_sample_simplified()
    # Find its exact score
    d_init = select(inst_simp, threshold=1.0)
    exact_score = d_init.score

    # Set threshold exactly equal to score
    d_edge_simp = select(inst_simp, threshold=exact_score)
    assert d_edge_simp.algorithm == "WIS-DP"

    inst_ext = _make_sample_extended()
    d_init_ext = select(inst_ext, threshold=1.0)
    exact_score_ext = d_init_ext.score

    d_edge_ext = select(
        inst_ext,
        threshold=exact_score_ext,
        config={"selector": {"exact_route_for_extended": "ilp", "ilp_max_tasks": 150}},
    )
    assert d_edge_ext.algorithm == "ILP-EXACT"


def test_t8_2_02_just_above_threshold():
    """T8.2-02: When score = threshold + 0.001, routes to CA-GREEDY."""
    inst = _make_sample_simplified()
    d_init = select(inst, threshold=1.0)
    score = d_init.score

    d_above = select(inst, threshold=score - 0.001)
    assert d_above.algorithm == "CA-GREEDY"


def test_t8_2_03_low_score_simplified():
    """T8.2-03: Simplified fixture with low score <= threshold routes to WIS-DP."""
    inst = _make_sample_simplified()
    d = select(inst, threshold=0.5)

    assert d.algorithm == "WIS-DP"
    assert d.score <= 0.5


def test_t8_2_04_low_score_extended_flag_ilp():
    """T8.2-04: Extended fixture with low score and flag exact_route_for_extended='ilp'
    routes to ILP-EXACT.
    """
    inst = _make_sample_extended()
    d = select(
        inst,
        threshold=1.0,  # Ensure score <= threshold
        config={"selector": {"exact_route_for_extended": "ilp", "ilp_max_tasks": 150}},
    )
    assert d.algorithm == "ILP-EXACT"


def test_t8_2_05_low_score_extended_flag_none():
    """T8.2-05: Extended fixture with low score and flag exact_route_for_extended='none'
    routes to CA-GREEDY.
    """
    inst = _make_sample_extended()
    d = select(
        inst,
        threshold=1.0,  # Ensure score <= threshold
        config={"selector": {"exact_route_for_extended": "none"}},
    )
    assert d.algorithm == "CA-GREEDY"
    assert "exact_route_for_extended" in d.reason or "none" in d.reason


def test_t8_2_06_ilp_size_guard():
    """T8.2-06: Task count above ilp_max_tasks triggers size guard -> CA-GREEDY with explanation."""
    inst = _make_sample_extended()
    n = len(inst.tasks)

    # Set ilp_max_tasks lower than n
    d = select(
        inst,
        threshold=1.0,
        config={"selector": {"exact_route_for_extended": "ilp", "ilp_max_tasks": n - 1}},
    )
    assert d.algorithm == "CA-GREEDY"
    assert "size guard" in d.reason.lower() or "ilp_max_tasks" in d.reason


def test_t8_2_07_always_dp_flag():
    """T8.2-07: Simplified instance with high score and simplified_always_dp=True -> WIS-DP."""
    inst = _make_sample_simplified()
    # Set threshold low so score > threshold
    d = select(
        inst,
        threshold=0.001,
        config={"selector": {"simplified_always_dp": True}},
    )
    assert d.algorithm == "WIS-DP"
    assert "simplified_always_dp" in d.reason


def test_t8_2_08_reason_content():
    """T8.2-08: Reason contains score, threshold, and all 5 feature names with values."""
    inst = _make_sample_simplified()
    d = select(inst, threshold=0.5)

    assert "Score:" in d.reason or "Score " in d.reason
    assert "Threshold:" in d.reason or "threshold " in d.reason
    assert "f1_size" in d.reason
    assert "f2_conflict_density" in d.reason
    assert "f3_resource_contention" in d.reason
    assert "f4_window_tightness" in d.reason
    assert "f5_corridor_utilization" in d.reason
    assert "Dominant feature:" in d.reason


def test_t8_2_09_determinism():
    """T8.2-09: Calling select twice yields identical Decision objects and reason text."""
    inst = _make_sample_extended()
    d1 = select(inst, threshold=0.5)
    d2 = select(inst, threshold=0.5)

    assert d1 == d2
    assert d1.reason == d2.reason


def test_t8_2_10_missing_threshold_file():
    """T8.2-10: Missing threshold file raises clear FileNotFoundError."""
    inst = _make_sample_simplified()
    missing_path = Path("non_existent_dir/missing_threshold.json")

    with pytest.raises(FileNotFoundError, match="not found"):
        select(inst, threshold=None, threshold_path=missing_path)


def test_t8_2_11_run_and_validate():
    """T8.2-11: run_selected on 30 instances produces valid schedules and records decision."""
    for seed in range(15):
        s_inst = generate_simplified(n=8, seed=seed)
        res_s = run_selected(s_inst, threshold=0.5)
        assert "decision" in res_s.meta
        assert isinstance(res_s.meta["decision"], Decision)
        report_s = validate_schedule(s_inst, res_s.schedule)
        assert len(report_s.violations) == 0

        e_inst = generate_extended(n=8, seed=seed)
        res_e = run_selected(e_inst, threshold=0.5)
        assert "decision" in res_e.meta
        assert isinstance(res_e.meta["decision"], Decision)
        report_e = validate_schedule(e_inst, res_e.schedule)
        assert len(report_e.violations) == 0


def test_t8_2_12_never_routes_wis_dp_to_extended():
    """T8.2-12: Select on 50 extended instances never routes to WIS-DP."""
    for seed in range(50):
        inst = generate_extended(n=10, seed=seed)
        for t_val in [0.0, 0.2, 0.5, 0.8, 1.0]:
            d = select(inst, threshold=t_val)
            assert d.algorithm != "WIS-DP"
            assert d.algorithm in ("ILP-EXACT", "CA-GREEDY")


def test_t8_2_registry_membership():
    """Verification checklist: Every chosen algorithm exists in the ALGORITHMS registry."""
    s_inst = _make_sample_simplified()
    e_inst = _make_sample_extended()

    for inst in (s_inst, e_inst):
        for t_val in [0.0, 0.5, 1.0]:
            d = select(inst, threshold=t_val)
            assert d.algorithm in ALGORITHMS
