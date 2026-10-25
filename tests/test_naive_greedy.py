"""Tests for NAIVE-GREEDY baseline heuristic (Milestone 5.1)."""

from rbp.algorithms.naive_greedy import solve_naive_greedy
from rbp.algorithms.wis_dp import solve_wis_dp
from rbp.generation.extended import generate_extended
from rbp.generation.simplified import generate_simplified
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# T5.1-01: Ordering (weight desc, duration asc, id asc)
# ---------------------------------------------------------------------------


def test_ordering():
    """T5.1-01: Tasks are sorted by (-weight, duration, id)."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2, 3))
    resource = Resource(type="crew", capacity=3, availability=(Interval(0, 1440),))

    # T1: w=31, d=20
    # T2: w=31, d=10 (shorter duration than T1)
    # T3: w=41, d=30 (higher weight)
    # T4: w=31, d=10, id=4 (same weight & dur as T2, higher id)
    t1 = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=20,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    t2 = Task(id=2, corridor_id=1, asset_id=2, window_start=0, window_end=100, duration=10,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    t3 = Task(id=3, corridor_id=1, asset_id=3, window_start=0, window_end=100, duration=30,
              criticality=4, urgency=1, demands={"crew": 1}, depends_on=())
    t4 = Task(id=4, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=10,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())

    inst = Instance(
        tasks=(t1, t2, t3, t4),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    ordered = sorted(inst.tasks, key=lambda t: (-t.weight, t.duration, t.id))
    assert [t.id for t in ordered] == [3, 2, 4, 1]


# ---------------------------------------------------------------------------
# T5.1-02: Free slot (placed at window_start)
# ---------------------------------------------------------------------------


def test_free_slot():
    """T5.1-02: With no conflicts, each task is placed at its window_start."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    resource = Resource(type="crew", capacity=2, availability=(Interval(0, 1440),))
    t1 = Task(id=1, corridor_id=1, asset_id=1, window_start=10, window_end=100, duration=20,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    t2 = Task(id=2, corridor_id=1, asset_id=2, window_start=30, window_end=100, duration=20,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    assert res.schedule.starts == {1: 10, 2: 30}


# ---------------------------------------------------------------------------
# T5.1-03: Train blocks start
# ---------------------------------------------------------------------------


def test_train_blocks_start():
    """T5.1-03: Train interval [0, 20) delays task placement to t=20."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(0, 20),))
    task = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=30,
                criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(tt,),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    assert res.schedule.starts == {1: 20}


# ---------------------------------------------------------------------------
# T5.1-04: Window too small after trains
# ---------------------------------------------------------------------------


def test_window_too_small_after_trains():
    """T5.1-04: Task is skipped when train leaves no gap >= duration."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1,))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    # Train occupies [10, 50), task window [0, 50), duration 30
    # Available gaps: [0, 10) length 10 < 30.
    tt = Timetable(corridor_id=1, intervals=(TrainInterval(10, 50),))
    task = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=50, duration=30,
                criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    inst = Instance(
        tasks=(task,),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(tt,),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    assert len(res.schedule.starts) == 0


# ---------------------------------------------------------------------------
# T5.1-05: Capacity forces delay
# ---------------------------------------------------------------------------


def test_capacity_forces_delay():
    """T5.1-05: Single resource capacity forces second task to start after first finishes."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    t1 = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=20,
              criticality=4, urgency=1, demands={"crew": 1}, depends_on=())
    t2 = Task(id=2, corridor_id=1, asset_id=2, window_start=0, window_end=100, duration=20,
              criticality=3, urgency=1, demands={"crew": 1}, depends_on=())
    inst = Instance(
        tasks=(t1, t2),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    assert res.schedule.starts == {1: 0, 2: 20}


# ---------------------------------------------------------------------------
# T5.1-06: Dependent with heavier weight (skipped under single-pass D12)
# ---------------------------------------------------------------------------


def test_dependent_with_heavier_weight_skipped():
    """T5.1-06: Under single-pass D12, dependent with heavier weight than prereq is skipped."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    resource = Resource(type="crew", capacity=2, availability=(Interval(0, 1440),))
    # Prerequisite has lower weight (crit=1 -> w=11)
    prereq = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=20,
                  criticality=1, urgency=1, demands={"crew": 1}, depends_on=())
    # Dependent has higher weight (crit=5 -> w=51)
    dep = Task(id=2, corridor_id=1, asset_id=2, window_start=20, window_end=100, duration=20,
               criticality=5, urgency=1, demands={"crew": 1}, depends_on=(1,))
    inst = Instance(
        tasks=(prereq, dep),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    # dep is considered first because of higher weight, but prereq is unplaced -> dep skipped!
    # then prereq is placed
    assert 2 not in res.schedule.starts
    assert 1 in res.schedule.starts


# ---------------------------------------------------------------------------
# T5.1-07: Dependent with lighter weight (both placed)
# ---------------------------------------------------------------------------


def test_dependent_with_lighter_weight_placed():
    """T5.1-07: Prerequisite heavier -> both placed, dependent starts after prereq end."""
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    resource = Resource(type="crew", capacity=2, availability=(Interval(0, 1440),))
    prereq = Task(id=1, corridor_id=1, asset_id=1, window_start=0, window_end=100, duration=20,
                  criticality=5, urgency=1, demands={"crew": 1}, depends_on=())
    dep = Task(id=2, corridor_id=1, asset_id=2, window_start=0, window_end=100, duration=20,
               criticality=1, urgency=1, demands={"crew": 1}, depends_on=(1,))
    inst = Instance(
        tasks=(prereq, dep),
        corridors=(corridor,),
        resources=(resource,),
        timetable=(),
        horizon=1440,
    )
    res = solve_naive_greedy(inst)
    assert res.schedule.starts[1] == 0
    assert res.schedule.starts[2] >= 20  # starts at or after prereq end


# ---------------------------------------------------------------------------
# T5.1-09: Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """T5.1-09: Running naive greedy twice produces identical schedules."""
    inst = generate_extended(n=30, seed=42)
    res1 = solve_naive_greedy(inst)
    res2 = solve_naive_greedy(inst)
    assert res1.schedule.starts == res2.schedule.starts
    assert res1.objective == res2.objective


# ---------------------------------------------------------------------------
# T5.1-10: Validity across 50 extended instances
# ---------------------------------------------------------------------------


def test_validity_50_extended_instances():
    """T5.1-10: Schedules generated for 50 extended instances pass independent validation."""
    for seed in range(1, 51):
        inst = generate_extended(n=25, seed=seed)
        res = solve_naive_greedy(inst)
        report = validate_schedule(inst, res.schedule)
        assert report.valid is True, f"Seed {seed} invalid: {report.violations}"


# ---------------------------------------------------------------------------
# T5.1-11: Never beats WIS-DP on simplified instances
# ---------------------------------------------------------------------------


def test_never_beats_wis_dp():
    """T5.1-11: Across 50 simplified instances, naive greedy objective <= WIS-DP."""
    for seed in range(1, 51):
        inst = generate_simplified(n=25, seed=seed)
        res_naive = solve_naive_greedy(inst)
        res_dp = solve_wis_dp(inst)
        assert res_naive.objective <= res_dp.objective, (
            f"Seed {seed}: Naive ({res_naive.objective}) > DP ({res_dp.objective})"
        )


# ---------------------------------------------------------------------------
# T5.1-12: Empty instance and input immutability
# ---------------------------------------------------------------------------


def test_empty_instance_and_immutability():
    """T5.1-12: n=0 returns empty schedule; input instance is not mutated."""
    inst = generate_extended(n=10, seed=1)
    tasks_before = list(inst.tasks)
    solve_naive_greedy(inst)
    assert list(inst.tasks) == tasks_before

    empty_inst = generate_simplified(n=0, seed=1)
    res_empty = solve_naive_greedy(empty_inst)
    assert res_empty.objective == 0
    assert len(res_empty.schedule.starts) == 0
