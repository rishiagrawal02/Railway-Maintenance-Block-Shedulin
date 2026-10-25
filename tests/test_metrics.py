"""Tests for scheduling metrics module and uniform algorithm runner (Milestone 7.1)."""

from __future__ import annotations

import time
from typing import Any

import pytest

from rbp.algorithms.base import AlgoResult
from rbp.generation import generate_extended, generate_simplified
from rbp.metrics import (
    ALGORITHMS,
    count_coverage,
    fragmentation,
    objective_value,
    optimality_gap,
    register_algorithm,
    run_algorithm,
    scheduled_count,
    utilization,
    weighted_coverage,
)
from rbp.models.corridor import Corridor
from rbp.models.instance import Instance
from rbp.models.schedule import Schedule
from rbp.models.task import Task
from rbp.validation.validator import validate_schedule


def _make_hand_instance() -> Instance:
    """Fixture instance with 3 tasks on corridor 1."""
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=30,
        criticality=1, urgency=0,
    )
    t2 = Task(
        id=2, corridor_id=1, asset_id=2, window_start=50, window_end=150, duration=40,
        criticality=2, urgency=0,
    )
    t3 = Task(
        id=3, corridor_id=1, asset_id=3, window_start=100, window_end=200, duration=50,
        criticality=1, urgency=4,
    )
    c1 = Corridor(id=1, traffic_level="MEDIUM", asset_ids=(1, 2, 3))
    return Instance(tasks=(t1, t2, t3), corridors=(c1,), horizon=240, meta={"seed": 42})


def test_t7_1_01_objective():
    """T7.1-01: Objective on hand schedule equals sum of weights."""
    inst = _make_hand_instance()
    # Schedule task 1 (weight 10) and task 3 (weight 14)
    sched = Schedule(starts={1: 10, 3: 110})
    assert objective_value(sched, inst) == 24
    assert scheduled_count(sched) == 2


def test_t7_1_02_coverage_edges():
    """T7.1-02: Coverage edges: all scheduled (1.0), none (0.0), total weight 0 (0.0)."""
    inst = _make_hand_instance()

    # All scheduled
    sched_all = Schedule(starts={1: 0, 2: 50, 3: 100})
    assert weighted_coverage(sched_all, inst) == pytest.approx(1.0)
    assert count_coverage(sched_all, inst) == pytest.approx(1.0)

    # None scheduled
    sched_none = Schedule(starts={})
    assert weighted_coverage(sched_none, inst) == pytest.approx(0.0)
    assert count_coverage(sched_none, inst) == pytest.approx(0.0)

    # Total weight 0
    t_zero = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=30,
        criticality=0, urgency=0,
    )
    inst_zero = Instance(tasks=(t_zero,), corridors=inst.corridors, horizon=240)
    sched_zero = Schedule(starts={1: 10})
    assert weighted_coverage(sched_zero, inst_zero) == pytest.approx(0.0)
    assert count_coverage(sched_zero, inst_zero) == pytest.approx(1.0)

    # Empty instance tasks
    inst_empty = Instance(tasks=(), corridors=inst.corridors, horizon=240)
    assert weighted_coverage(sched_none, inst_empty) == pytest.approx(0.0)
    assert count_coverage(sched_none, inst_empty) == pytest.approx(0.0)


def test_t7_1_03_gap_formula():
    """T7.1-03: Gap formula: optimum 44, objective 40 -> 0.0909 (4/44)."""
    gap = optimality_gap(40, 44)
    assert gap is not None
    assert gap == pytest.approx(4 / 44, rel=1e-3)


def test_t7_1_04_gap_undefined():
    """T7.1-04: Gap undefined: optimum None or 0 -> None."""
    assert optimality_gap(40, None) is None
    assert optimality_gap(40, 0) is None
    assert optimality_gap(40, -10) is None


def test_t7_1_05_negative_gap():
    """T7.1-05: Negative gap when objective > optimum sets anomaly=True."""
    inst = _make_hand_instance()

    def mock_super_algo(i: Instance) -> AlgoResult:
        # Schedule all 3 tasks (objective = 44)
        return AlgoResult(
            name="mock_super",
            schedule=Schedule(starts={1: 0, 2: 50, 3: 100}),
            objective=44,
        )

    # Run with stated optimum of 40 (objective is 44 > 40)
    record = run_algorithm(mock_super_algo, inst, optimum=40)
    assert record.objective == 44
    assert record.gap is not None
    assert record.gap == pytest.approx((40 - 44) / 40)
    assert record.gap < 0
    assert record.anomaly is True


def test_t7_1_06_violation_count():
    """T7.1-06: Violation count on mutated schedule matches validator count."""
    # Create two tasks on the same asset that overlap in time
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=60,
        criticality=1, urgency=0,
    )
    t2 = Task(
        id=2, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=60,
        criticality=1, urgency=0,
    )
    inst = Instance(tasks=(t1, t2), horizon=240)

    # Place both overlapping on asset 1: [0, 60) and [20, 80)
    invalid_sched = Schedule(starts={1: 0, 2: 20})

    def mock_invalid_algo(i: Instance) -> AlgoResult:
        return AlgoResult(name="invalid_algo", schedule=invalid_sched, objective=20)

    record = run_algorithm(mock_invalid_algo, inst)
    expected_report = validate_schedule(inst, invalid_sched)

    assert record.violations == len(expected_report.violations)
    assert record.violations > 0


def test_t7_1_07_fragmentation():
    """T7.1-07: Fragmentation: touching tasks -> 1 block, separated tasks -> 2 blocks."""
    # Corridor 1, touching tasks: [0, 60) and [60, 120)
    t1 = Task(
        id=1, corridor_id=1, asset_id=1, window_start=0, window_end=200, duration=60,
        criticality=1, urgency=0,
    )
    t2 = Task(
        id=2, corridor_id=1, asset_id=2, window_start=0, window_end=200, duration=60,
        criticality=1, urgency=0,
    )
    inst = Instance(tasks=(t1, t2), horizon=200)

    touching_sched = Schedule(starts={1: 0, 2: 60})
    assert fragmentation(touching_sched, inst) == 1

    # Separated tasks: [0, 60) and [80, 140)
    separated_sched = Schedule(starts={1: 0, 2: 80})
    assert fragmentation(separated_sched, inst) == 2


def test_t7_1_08_not_applicable():
    """T7.1-08: WIS-DP on extended instance returns status NOT_APPLICABLE."""
    ext_inst = generate_extended(n=10, seed=123)
    record = run_algorithm("WIS-DP", ext_inst)

    assert record.status == "NOT_APPLICABLE"
    assert record.objective == 0
    assert record.violations == 0
    assert "NotSimplifiedError" in str(record.meta.get("error", ""))


def test_t7_1_09_error_captured():
    """T7.1-09: Algorithm exception is captured, status ERROR, no crash."""
    inst = _make_hand_instance()

    def crashing_algo(i: Instance) -> Any:
        raise ValueError("Simulated algorithm failure")

    record = run_algorithm(crashing_algo, inst)
    assert record.status == "ERROR"
    assert record.objective == 0
    assert "Simulated algorithm failure" in str(record.meta.get("error", ""))


def test_t7_1_10_runtime_recorded():
    """T7.1-10: Runtime recorded accurately for fixture with sleep 0.05s."""
    inst = _make_hand_instance()

    def sleeping_algo(i: Instance) -> AlgoResult:
        time.sleep(0.05)
        return AlgoResult(name="sleeper", schedule=Schedule(starts={}), objective=0)

    record = run_algorithm(sleeping_algo, inst, repeats=1)
    assert record.runtime_s >= 0.045


def test_t7_1_11_repeatability():
    """T7.1-11: Running on same instance twice gives equal fields except runtime."""
    inst = generate_simplified(n=12, seed=77)
    rec1 = run_algorithm("CA-GREEDY", inst, repeats=1)
    rec2 = run_algorithm("CA-GREEDY", inst, repeats=1)

    assert rec1.algo == rec2.algo
    assert rec1.n == rec2.n
    assert rec1.seed == rec2.seed
    assert rec1.objective == rec2.objective
    assert rec1.coverage == rec2.coverage
    assert rec1.scheduled == rec2.scheduled
    assert rec1.violations == rec2.violations
    assert rec1.status == rec2.status
    assert rec1.optimal == rec2.optimal
    assert rec1.gap == rec2.gap
    assert rec1.anomaly == rec2.anomaly


def test_t7_1_utilization():
    """Verify utilization calculation: busy minutes over horizon."""
    inst = _make_hand_instance()  # horizon = 240
    # Task 1 (dur 30) and Task 2 (dur 40) scheduled -> 70 busy minutes
    sched = Schedule(starts={1: 0, 2: 50})
    assert utilization(sched, inst) == pytest.approx(70 / 240)


def test_t7_1_all_registered_algorithms():
    """Verify run_algorithm works for all 5 registered algorithms on simplified instance."""
    inst = generate_simplified(n=6, seed=99)
    for name in ["WIS-DP", "NAIVE-GREEDY", "CA-GREEDY", "ILP-EXACT", "BRUTE-FORCE"]:
        rec = run_algorithm(name, inst)
        assert rec.status == "OK"
        assert rec.violations == 0
        assert rec.objective > 0
        assert rec.scheduled > 0
        assert rec.coverage > 0.0
        if name in ("WIS-DP", "BRUTE-FORCE", "ILP-EXACT"):
            assert rec.optimal is True
            assert rec.gap == 0.0
        else:
            assert rec.optimal is False


def test_t7_1_register_algorithm_and_as_dict():
    """Verify register_algorithm extension and RunRecord.as_dict conversion."""
    custom_name = "TEST-CUSTOM-ALGO"

    def my_algo(inst: Instance) -> AlgoResult:
        return AlgoResult(name="my_algo", schedule=Schedule(starts={}), objective=0)

    register_algorithm(custom_name, my_algo)
    assert custom_name in ALGORITHMS

    inst = _make_hand_instance()
    rec = run_algorithm(custom_name, inst)
    d = rec.as_dict()
    assert d["algo"] == custom_name
    assert d["status"] == "OK"
    assert "objective" in d
    assert "runtime_s" in d


def test_t7_1_unknown_algorithm():
    """Verify unknown algorithm name raises ValueError."""
    inst = _make_hand_instance()
    with pytest.raises(ValueError, match="Unknown algorithm"):
        run_algorithm("NON_EXISTENT_ALGORITHM", inst)
