"""Tests for constraint predicates C1-C5 and PlacementState (Milestone 2.1)."""


from rbp.constraints import (
    PlacementState,
    c1_window_ok,
    c2_train_ok,
    c3_asset_ok,
    c4_resource_ok,
    c5_dependency_ok,
    first_violation,
    is_feasible,
)
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_task(
    id: int = 1,
    corridor_id: int = 1,
    asset_id: int = 1,
    window_start: int = 0,
    window_end: int = 300,
    duration: int = 50,
    criticality: int = 3,
    urgency: int = 2,
    demands: dict | None = None,
    depends_on: tuple = (),
) -> Task:
    return Task(
        id=id,
        corridor_id=corridor_id,
        asset_id=asset_id,
        window_start=window_start,
        window_end=window_end,
        duration=duration,
        criticality=criticality,
        urgency=urgency,
        demands=demands or {},
        depends_on=depends_on,
    )


def _make_instance(
    tasks=None,
    train_intervals: list[tuple[int, int]] | None = None,
    resource_capacity: int = 2,
    availability: list[tuple[int, int]] | None = None,
    n_assets: int = 2,
) -> Instance:
    if availability is None:
        availability = [(0, 1440)]
    avail_ivs = tuple(Interval(s, e) for s, e in availability)
    corridor = Corridor(id=1, traffic_level="low", asset_ids=tuple(range(1, n_assets + 1)))
    resource = Resource(type="crew", capacity=resource_capacity, availability=avail_ivs)
    tt_intervals = tuple(
        TrainInterval(start=s, end=e) for s, e in (train_intervals or [])
    )
    timetable = (Timetable(corridor_id=1, intervals=tt_intervals),) if tt_intervals else ()
    return Instance(
        tasks=tuple(tasks or [_make_task()]),
        corridors=(corridor,),
        resources=(resource,),
        timetable=timetable,
        horizon=1440,
    )


def _empty_state(instance: Instance) -> PlacementState:
    return PlacementState(instance)


# ---------------------------------------------------------------------------
# C1: Time-window feasibility
# ---------------------------------------------------------------------------


class TestC1Window:
    def test_start_at_window_start(self):
        """T2.1-01: Start exactly at window_start is OK."""
        task = _make_task(window_start=100, window_end=200, duration=50)
        assert c1_window_ok(task, 100) is True

    def test_end_exactly_at_window_end(self):
        """T2.1-02: Task ending exactly at window_end is OK (end == 150+50=200)."""
        task = _make_task(window_start=100, window_end=200, duration=50)
        assert c1_window_ok(task, 150) is True

    def test_end_one_past_window_end(self):
        """T2.1-03: Task ending one minute past window_end fails C1."""
        task = _make_task(window_start=100, window_end=200, duration=50)
        assert c1_window_ok(task, 151) is False

    def test_start_before_window(self):
        """T2.1-04: Start before window_start fails C1."""
        task = _make_task(window_start=100, window_end=200, duration=50)
        assert c1_window_ok(task, 99) is False

    def test_fits_exactly(self):
        task = _make_task(window_start=0, window_end=30, duration=30)
        assert c1_window_ok(task, 0) is True


# ---------------------------------------------------------------------------
# C2: Train conflict
# ---------------------------------------------------------------------------


class TestC2Train:
    def test_touching_train_is_ok(self):
        """T2.1-05: Task [100,140) touching train [140,150) is OK."""
        task = _make_task(window_start=0, window_end=200, duration=40)
        instance = _make_instance(train_intervals=[(140, 150)])
        assert c2_train_ok(instance, task, 100) is True

    def test_overlap_by_one_minute(self):
        """T2.1-06: Task [100,140) overlaps train [139,150) by 1 minute → C2."""
        task = _make_task(window_start=0, window_end=200, duration=40)
        instance = _make_instance(train_intervals=[(139, 150)])
        assert c2_train_ok(instance, task, 100) is False

    def test_train_on_different_corridor_is_ok(self):
        """T2.1-07: Train on corridor 2 does not affect task on corridor 1."""
        task = _make_task(corridor_id=1, window_start=0, window_end=200, duration=40)
        corridor2 = Corridor(id=2, traffic_level="low", asset_ids=(3,))
        corridor1 = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
        resource = Resource(type="crew", capacity=2, availability=(Interval(0, 1440),))
        ti = TrainInterval(start=100, end=200)
        tt2 = Timetable(corridor_id=2, intervals=(ti,))
        instance = Instance(
            tasks=(task,), corridors=(corridor1, corridor2),
            resources=(resource,), timetable=(tt2,), horizon=1440,
        )
        assert c2_train_ok(instance, task, 100) is True

    def test_no_timetable_always_ok(self):
        """No timetable entry for corridor → C2 always passes."""
        task = _make_task(window_start=0, window_end=200, duration=40)
        instance = _make_instance(train_intervals=None)
        assert c2_train_ok(instance, task, 0) is True


# ---------------------------------------------------------------------------
# C3: Asset conflict
# ---------------------------------------------------------------------------


class TestC3Asset:
    def test_adjacent_tasks_ok(self):
        """T2.1-08: Placed [0,10) and new [10,20) on same asset is OK (touching)."""
        t1 = _make_task(id=1, asset_id=1, duration=10, window_end=100)
        t2 = _make_task(id=2, asset_id=1, duration=10, window_end=100)
        instance = _make_instance(tasks=[t1, t2])
        state = _empty_state(instance)
        state.place(t1, 0)
        assert c3_asset_ok(state, t2, 10) is True

    def test_overlap_same_asset(self):
        """T2.1-09: Placed [0,10) and new [9,19) on same asset → C3."""
        t1 = _make_task(id=1, asset_id=1, duration=10, window_end=100)
        t2 = _make_task(id=2, asset_id=1, duration=10, window_end=100)
        instance = _make_instance(tasks=[t1, t2])
        state = _empty_state(instance)
        state.place(t1, 0)
        assert c3_asset_ok(state, t2, 9) is False

    def test_overlap_different_asset_ok(self):
        """T2.1-10: Same times but different assets → no conflict."""
        t1 = _make_task(id=1, asset_id=1, duration=10, window_end=100)
        t2 = _make_task(id=2, asset_id=2, duration=10, window_end=100)
        instance = _make_instance(tasks=[t1, t2])
        state = _empty_state(instance)
        state.place(t1, 0)
        assert c3_asset_ok(state, t2, 0) is True


# ---------------------------------------------------------------------------
# C4: Resource capacity
# ---------------------------------------------------------------------------


class TestC4Resource:
    def test_capacity_exactly_met(self):
        """T2.1-11: cap=2, one placed demand=1, new demand=1 → OK."""
        t1 = _make_task(id=1, demands={"crew": 1}, duration=20, window_end=100)
        t2 = _make_task(id=2, demands={"crew": 1}, duration=20, window_end=100)
        instance = _make_instance(tasks=[t1, t2], resource_capacity=2)
        state = _empty_state(instance)
        state.place(t1, 0)
        assert c4_resource_ok(state, instance, t2, 0) is True

    def test_capacity_exceeded_by_one(self):
        """T2.1-12: cap=2, two placed overlapping, new demand=1 → C4."""
        t1 = _make_task(id=1, demands={"crew": 1}, duration=20, window_end=100)
        t2 = _make_task(id=2, asset_id=2, demands={"crew": 1}, duration=20, window_end=100)
        t3 = _make_task(id=3, asset_id=3, demands={"crew": 1}, duration=20, window_end=100)
        instance = _make_instance(tasks=[t1, t2, t3], resource_capacity=2, n_assets=3)
        state = _empty_state(instance)
        state.place(t1, 0)
        state.place(t2, 0)
        assert c4_resource_ok(state, instance, t3, 0) is False

    def test_outside_availability(self):
        """T2.1-13: availability [0,60), task [50,70) → C4."""
        t1 = _make_task(id=1, demands={"crew": 1}, duration=20, window_start=50, window_end=200)
        instance = _make_instance(tasks=[t1], resource_capacity=2, availability=[(0, 60)])
        state = _empty_state(instance)
        assert c4_resource_ok(state, instance, t1, 50) is False


# ---------------------------------------------------------------------------
# C5: Dependency precedence
# ---------------------------------------------------------------------------


class TestC5Dependency:
    def test_start_equals_prereq_end_ok(self):
        """T2.1-14: prereq placed [0,30), start=30 → OK (end == start)."""
        prereq = _make_task(id=1, duration=30, window_end=200)
        dep = _make_task(id=2, duration=20, window_end=200, depends_on=(1,))
        instance = _make_instance(tasks=[prereq, dep])
        state = _empty_state(instance)
        state.place(prereq, 0)
        assert c5_dependency_ok(state, dep, 30) is True

    def test_start_before_prereq_end_fails(self):
        """T2.1-15: prereq placed [0,30), start=29 → C5."""
        prereq = _make_task(id=1, duration=30, window_end=200)
        dep = _make_task(id=2, duration=20, window_end=200, depends_on=(1,))
        instance = _make_instance(tasks=[prereq, dep])
        state = _empty_state(instance)
        state.place(prereq, 0)
        assert c5_dependency_ok(state, dep, 29) is False

    def test_prereq_not_placed_fails(self):
        """T2.1-16: Dependency not yet placed → C5."""
        prereq = _make_task(id=1, duration=30, window_end=200)
        dep = _make_task(id=2, duration=20, window_end=200, depends_on=(1,))
        instance = _make_instance(tasks=[prereq, dep])
        state = _empty_state(instance)
        # prereq NOT placed
        assert c5_dependency_ok(state, dep, 30) is False


# ---------------------------------------------------------------------------
# PlacementState: place / unplace round-trip
# ---------------------------------------------------------------------------


class TestPlacementState:
    def test_place_then_unplace_leaves_no_residue(self):
        """T2.1-17: After place then unplace, state is identical to initial."""
        t1 = _make_task(id=1, demands={"crew": 1}, duration=20, window_end=100)
        t2 = _make_task(id=2, demands={"crew": 1}, duration=20, window_end=100)
        instance = _make_instance(tasks=[t1, t2], resource_capacity=2)
        state = _empty_state(instance)

        usage_before = list(state._resource_usage["crew"])
        asset_before = list(state.asset_intervals(1))

        state.place(t1, 0)
        state.unplace(t1)

        assert list(state._resource_usage["crew"]) == usage_before
        assert list(state.asset_intervals(1)) == asset_before
        assert not state.is_placed(1)

    def test_empty_state_no_violations(self):
        """is_feasible always passes for no competing placements (empty state)."""
        task = _make_task(demands={"crew": 1})
        instance = _make_instance(resource_capacity=2)
        state = _empty_state(instance)
        assert is_feasible(instance, state, task, 0) is True

    def test_first_violation_order(self):
        """first_violation returns lowest-numbered failing constraint."""
        task = _make_task(window_start=100, window_end=200, duration=50)
        instance = _make_instance()
        state = _empty_state(instance)
        # C1 fires because start=0 < window_start=100
        result = first_violation(instance, state, task, 0)
        assert result == "C1"

    def test_first_violation_none_when_feasible(self):
        task = _make_task(window_start=0, window_end=200, duration=50)
        instance = _make_instance()
        state = _empty_state(instance)
        assert first_violation(instance, state, task, 0) is None


# ---------------------------------------------------------------------------
# T2.1-18: Regression of Phase 1
# ---------------------------------------------------------------------------


def test_regression_phase1():
    """T2.1-18: Phase 1 tests still pass."""
    from rbp.io.input_checks import validate_instance

    task = _make_task()
    instance = _make_instance(tasks=[task])
    assert validate_instance(instance) == []
