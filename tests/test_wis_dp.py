"""Tests for Weighted Interval Scheduling DP solver (Milestone 4.1)."""

import time

import pytest

from rbp.algorithms.base import NotSimplifiedError
from rbp.algorithms.wis_dp import solve_wis_dp
from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.models import Corridor, Instance, Interval, Resource, Task
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_hand_instance() -> Instance:
    """Hand fixture from Playbook Milestone 4.1:

    A [0,3) w15 (crit=1, urg=5)
    B [2,5) w21 (crit=2, urg=1)
    C [4,7) w14 (crit=1, urg=4)
    D [6,9) w23 (crit=2, urg=3)
    E [8,10) w13 (crit=1, urg=3)
    """
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks = (
        Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=3, duration=3,
             criticality=1, urgency=5, demands={"crew": 1}, depends_on=()),
        Task(id=2, corridor_id=1, asset_id=1, window_start=2, window_end=5, duration=3,
             criticality=2, urgency=1, demands={"crew": 1}, depends_on=()),
        Task(id=3, corridor_id=1, asset_id=1, window_start=4, window_end=7, duration=3,
             criticality=1, urgency=4, demands={"crew": 1}, depends_on=()),
        Task(id=4, corridor_id=1, asset_id=1, window_start=6, window_end=9, duration=3,
             criticality=2, urgency=3, demands={"crew": 1}, depends_on=()),
        Task(id=5, corridor_id=1, asset_id=1, window_start=8, window_end=10, duration=2,
             criticality=1, urgency=3, demands={"crew": 1}, depends_on=()),
    )
    return Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )


# ---------------------------------------------------------------------------
# T4.1-01: Hand example
# ---------------------------------------------------------------------------


def test_hand_example_optimum():
    """T4.1-01: Hand fixture produces objective 44 and chooses tasks {B, D} (IDs 2, 4)."""
    inst = _make_hand_instance()
    result = solve_wis_dp(inst)
    assert result.objective == 44
    assert set(result.schedule.starts.keys()) == {2, 4}


# ---------------------------------------------------------------------------
# T4.1-02: Predecessor array p(i) values
# ---------------------------------------------------------------------------


def test_hand_example_p_values():
    """T4.1-02: Hand fixture computes expected p and OPT tables."""
    inst = _make_hand_instance()
    result = solve_wis_dp(inst)
    assert result.meta["p"] == [0, 0, 1, 2, 3]
    assert result.meta["opt"] == [0, 15, 21, 29, 44, 44]


# ---------------------------------------------------------------------------
# T4.1-03: Empty instance
# ---------------------------------------------------------------------------


def test_empty_instance():
    """T4.1-03: n=0 instance produces objective 0 and empty schedule."""
    inst = generate_simplified(n=0, seed=1)
    result = solve_wis_dp(inst)
    assert result.objective == 0
    assert len(result.schedule.starts) == 0


# ---------------------------------------------------------------------------
# T4.1-04: Single task
# ---------------------------------------------------------------------------


def test_single_task():
    """T4.1-04: n=1 instance chooses the single task."""
    inst = generate_simplified(n=1, seed=42)
    result = solve_wis_dp(inst)
    task = inst.tasks[0]
    assert result.objective == task.weight
    assert result.schedule.starts == {task.id: task.window_start}


# ---------------------------------------------------------------------------
# T4.1-05: All overlapping tasks
# ---------------------------------------------------------------------------


def test_all_overlapping_tasks():
    """T4.1-05: 5 identical overlapping windows chooses only the heaviest task."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    # Tasks with weights 11, 21, 31, 41, 51 (all [0, 10))
    tasks = tuple(
        Task(
            id=i,
            corridor_id=1,
            asset_id=1,
            window_start=0,
            window_end=10,
            duration=10,
            criticality=i,
            urgency=1,
            demands={"crew": 1},
            depends_on=(),
        )
        for i in range(1, 6)
    )
    inst = Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    result = solve_wis_dp(inst)
    assert result.objective == 51
    assert set(result.schedule.starts.keys()) == {5}


# ---------------------------------------------------------------------------
# T4.1-06: All disjoint tasks
# ---------------------------------------------------------------------------


def test_all_disjoint_tasks():
    """T4.1-06: 5 spaced disjoint tasks are all chosen."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tasks = tuple(
        Task(
            id=i,
            corridor_id=1,
            asset_id=1,
            window_start=i * 20,
            window_end=i * 20 + 10,
            duration=10,
            criticality=2,
            urgency=1,
            demands={"crew": 1},
            depends_on=(),
        )
        for i in range(1, 6)
    )
    inst = Instance(
        tasks=tasks,
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    result = solve_wis_dp(inst)
    assert len(result.schedule.starts) == 5
    assert result.objective == sum(t.weight for t in tasks)


# ---------------------------------------------------------------------------
# T4.1-07: Touching intervals
# ---------------------------------------------------------------------------


def test_touching_intervals_both_chosen():
    """T4.1-07: Touching intervals [0,5) and [5,9) are compatible and both chosen."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    t1 = Task(
        id=1,
        corridor_id=1,
        asset_id=1,
        window_start=0,
        window_end=5,
        duration=5,
        criticality=1,
        urgency=1,
        demands={"crew": 1},
        depends_on=(),
    )
    t2 = Task(
        id=2,
        corridor_id=1,
        asset_id=1,
        window_start=5,
        window_end=9,
        duration=4,
        criticality=1,
        urgency=1,
        demands={"crew": 1},
        depends_on=(),
    )
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    result = solve_wis_dp(inst)
    assert result.objective == t1.weight + t2.weight
    assert set(result.schedule.starts.keys()) == {1, 2}


# ---------------------------------------------------------------------------
# T4.1-08: Equal weights tie breaking is deterministic
# ---------------------------------------------------------------------------


def test_equal_weights_tie_deterministic():
    """T4.1-08: Solving an instance with equal-weight alternatives produces identical output."""
    inst = generate_simplified(n=20, seed=123)
    res1 = solve_wis_dp(inst)
    res2 = solve_wis_dp(inst)
    assert res1.schedule.starts == res2.schedule.starts
    assert res1.objective == res2.objective


# ---------------------------------------------------------------------------
# T4.1-09: Not simplified raises NotSimplifiedError
# ---------------------------------------------------------------------------


def test_not_simplified_raises_error():
    """T4.1-09: Extended instance raises NotSimplifiedError."""
    inst = generate_extended(n=10, seed=1)
    with pytest.raises(NotSimplifiedError):
        solve_wis_dp(inst)


# ---------------------------------------------------------------------------
# T4.1-10: Output schedules are valid according to independent validator
# ---------------------------------------------------------------------------


def test_output_schedules_valid_50_seeds():
    """T4.1-10: Schedules generated for 50 simplified instances pass independent validation."""
    for seed in range(1, 51):
        inst = generate_simplified(n=30, seed=seed)
        result = solve_wis_dp(inst)
        report = validate_schedule(inst, result.schedule)
        assert report.valid is True, f"Seed {seed} schedule invalid: {report.violations}"


# ---------------------------------------------------------------------------
# T4.1-11: Input instance is not mutated
# ---------------------------------------------------------------------------


def test_input_not_mutated():
    """T4.1-11: solve_wis_dp does not mutate the input instance."""
    inst = generate_simplified(n=25, seed=77)
    tasks_before = list(inst.tasks)
    solve_wis_dp(inst)
    assert list(inst.tasks) == tasks_before


# ---------------------------------------------------------------------------
# T4.1-12: Scalability test (slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_scalability_100k():
    """T4.1-12: n=100,000 tasks solves in seconds."""
    inst = generate_simplified(n=100000, seed=42)
    t0 = time.perf_counter()
    result = solve_wis_dp(inst)
    elapsed = time.perf_counter() - t0
    assert result.objective > 0
    assert elapsed < 5.0
