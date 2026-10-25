"""Tests for ILP-EXACT CP-SAT solver (Milestone 6.1)."""

from unittest.mock import patch

import pytest
from ortools.sat.python import cp_model

from rbp.algorithms.ilp_exact import solve_ilp_exact
from rbp.generation.extended import generate_extended
from rbp.models import (
    Corridor,
    Instance,
    Interval,
    Resource,
    Task,
    Timetable,
    TrainInterval,
)
from rbp.validation.validator import validate_schedule
from tests.test_wis_dp import _make_hand_instance


def test_t61_01_simplified_hand_example():
    """T6.1-01: Hand fixture from 4.1 yields OPTIMAL with objective 44."""
    inst = _make_hand_instance()
    res = solve_ilp_exact(inst)

    assert res.meta["status"] == "OPTIMAL"
    assert res.meta["optimal"] is True
    assert res.objective == 44
    assert set(res.schedule.starts.keys()) == {2, 4}


def test_t61_02_empty_instance():
    """T6.1-02: Empty instance (n=0) yields objective 0 and optimal=True."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res_def = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    inst = Instance(
        tasks=(),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(),
        horizon=1440,
    )
    res = solve_ilp_exact(inst)

    assert res.objective == 0
    assert res.meta["optimal"] is True
    assert len(res.schedule.starts) == 0


def test_t61_03_train_forces_later_start():
    """T6.1-03: Train blocking corridor at [0, 50) forces task to start at or after 50."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res_def = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(0, 50),))
    task = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=150,
        duration=40,
        criticality=1,
        urgency=1,
        demands={},
        depends_on=(),
    )
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(tt,),
        horizon=1440,
    )

    res = solve_ilp_exact(inst)
    assert 1 in res.schedule.starts
    assert res.schedule.starts[1] >= 50


def test_t61_04_capacity_forces_sequencing():
    """T6.1-04: Resource capacity 1 forces two tasks to sequence without temporal overlap."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    # Crew capacity 1
    res_def = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    # Both tasks need crew: 1, on different assets so C3 does not constrain them
    t1 = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=100,
        duration=30,
        criticality=2,
        urgency=1,
        demands={"crew": 1},
        depends_on=(),
    )
    t2 = Task(
        id=2,
        corridor_id=1,
        asset_id=2,
        window_start=0,
        window_end=100,
        duration=30,
        criticality=2,
        urgency=1,
        demands={"crew": 1},
        depends_on=(),
    )
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(),
        horizon=1440,
    )

    res = solve_ilp_exact(inst)
    assert res.meta["optimal"] is True
    assert 1 in res.schedule.starts and 2 in res.schedule.starts

    s1, s2 = res.schedule.starts[1], res.schedule.starts[2]
    # No overlap
    assert s1 + 30 <= s2 or s2 + 30 <= s1


def test_t61_05_asset_conflict():
    """T6.1-05: Two overlapping tasks on the same asset: heavier task is chosen."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res_def = Resource(type="crew", capacity=5, availability=(Interval(0, 1440),))

    # Task 1: weight 10, [0, 50), d=50
    t1 = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=50,
        duration=50,
        criticality=1,
        urgency=0,
        demands={},
        depends_on=(),
    )
    # Task 2: weight 50, [0, 50), d=50
    t2 = Task(
        id=2,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=50,
        duration=50,
        criticality=5,
        urgency=0,
        demands={},
        depends_on=(),
    )
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(),
        horizon=1440,
    )

    res = solve_ilp_exact(inst)
    assert res.objective == 50
    assert 2 in res.schedule.starts
    assert 1 not in res.schedule.starts


def test_t61_06_dependency():
    """T6.1-06: Dependent heavier than prerequisite -> both placed in order, or neither."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    res_def = Resource(type="crew", capacity=5, availability=(Interval(0, 1440),))

    p = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=100,
        duration=20,
        criticality=1,
        urgency=1,
        demands={},
        depends_on=(),
    )  # w=11
    d = Task(
        id=2,
        corridor_id=1,
        asset_id=2,
        window_start=0,
        window_end=100,
        duration=20,
        criticality=9,
        urgency=9,
        demands={},
        depends_on=(1,),
    )  # w=99
    inst = Instance(
        tasks=(p, d),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(),
        horizon=1440,
    )

    res = solve_ilp_exact(inst)
    assert res.objective == 11 + 99
    assert res.schedule.starts[2] >= res.schedule.starts[1] + 20


def test_t61_07_impossible_task():
    """T6.1-07: Task whose window is completely blocked is omitted without solver error."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res_def = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    # Train blocks entire window [0, 30)
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(0, 30),))
    task = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=30,
        duration=20,
        criticality=3,
        urgency=1,
        demands={},
        depends_on=(),
    )
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(tt,),
        horizon=1440,
    )

    res = solve_ilp_exact(inst)
    assert res.objective == 0
    assert 1 not in res.schedule.starts


def test_t61_08_time_limit_hit():
    """T6.1-08: Time limit hit handles gracefully, optimal=False, valid schedule."""
    inst = generate_extended(n=120, seed=99)
    # Extremely short time limit forces solver to stop early
    res = solve_ilp_exact(inst, time_limit_s=0.01)

    # Regardless of whether feasible or unknown, optimal must not be True unless proven
    if res.meta["status"] != "OPTIMAL":
        assert res.meta["optimal"] is False

    report = validate_schedule(inst, res.schedule)
    assert report.valid


def test_t61_09_repeatability():
    """T6.1-09: Same random seed and num_workers=1 produces identical objective."""
    inst = generate_extended(n=25, seed=12)
    res1 = solve_ilp_exact(inst, random_seed=42, num_workers=1)
    res2 = solve_ilp_exact(inst, random_seed=42, num_workers=1)

    assert res1.objective == res2.objective
    assert res1.schedule.starts == res2.schedule.starts


def test_t61_10_validity_30_extended_instances():
    """T6.1-10: 30 extended instances (n<=30) all produce 100% valid schedules."""
    for seed in range(30):
        inst = generate_extended(n=15, seed=seed)
        res = solve_ilp_exact(inst, time_limit_s=2.0)
        report = validate_schedule(inst, res.schedule)
        assert report.valid, f"Seed {seed} invalid: {report.violations}"


def test_t61_11_infeasible_guard():
    """T6.1-11: If solver unexpectedly reports INFEASIBLE, explicit RuntimeError is raised."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    res_def = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    task = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=10,
        duration=5,
        criticality=1,
        urgency=1,
        demands={},
        depends_on=(),
    )
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(res_def,),
        timetable=(),
        horizon=1440,
    )

    with patch.object(cp_model.CpSolver, "Solve", return_value=cp_model.INFEASIBLE):
        with pytest.raises(RuntimeError, match="CP-SAT solver returned INFEASIBLE"):
            solve_ilp_exact(inst)
