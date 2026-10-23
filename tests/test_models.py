"""Tests for domain models (Milestone 1.1)."""

import pytest

from rbp.models import (
    Corridor,
    Instance,
    Interval,
    Resource,
    Schedule,
    Task,
    Timetable,
    TrainInterval,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_task(
    id: int = 1,
    corridor_id: int = 1,
    asset_id: int = 1,
    window_start: int = 0,
    window_end: int = 100,
    duration: int = 30,
    criticality: int = 3,
    urgency: int = 1,
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


def make_instance(tasks=None, corridors=None, resources=None, timetable=None, horizon=1440):
    corridor = Corridor(id=1, traffic_level="low", asset_ids=(1, 2))
    resource = Resource(type="crew", capacity=1, availability=(Interval(0, 1440),))
    return Instance(
        tasks=tuple(tasks or [make_task()]),
        corridors=tuple(corridors or [corridor]),
        resources=tuple(resources or [resource]),
        timetable=tuple(timetable or []),
        horizon=horizon,
    )


# ---------------------------------------------------------------------------
# Interval tests
# ---------------------------------------------------------------------------


class TestInterval:
    def test_touching_intervals_do_not_overlap(self):
        """T1.1-03: [0,5) and [5,9) do not overlap."""
        a = Interval(0, 5)
        b = Interval(5, 9)
        assert a.overlaps(b) is False
        assert b.overlaps(a) is False

    def test_overlap_by_one_unit(self):
        """T1.1-04: [0,5) and [4,9) overlap by one unit."""
        a = Interval(0, 5)
        b = Interval(4, 9)
        assert a.overlaps(b) is True
        assert b.overlaps(a) is True

    def test_nested_overlap(self):
        """T1.1-05a: [0,10) vs [2,3) nested overlap."""
        a = Interval(0, 10)
        b = Interval(2, 3)
        assert a.overlaps(b) is True

    def test_identical_overlap(self):
        """T1.1-05b: [1,4) vs [1,4) identical overlap."""
        a = Interval(1, 4)
        b = Interval(1, 4)
        assert a.overlaps(b) is True

    def test_empty_interval(self):
        """Zero-length interval [3,3) is valid and touches nothing."""
        a = Interval(3, 3)
        b = Interval(3, 5)
        assert a.overlaps(b) is False

    def test_length_property(self):
        a = Interval(10, 20)
        assert a.length == 10

    def test_contains_point(self):
        a = Interval(0, 10)
        assert a.contains(0) is True
        assert a.contains(9) is True
        assert a.contains(10) is False

    def test_invalid_start_exceeds_end(self):
        with pytest.raises(ValueError):
            Interval(10, 5)


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------


class TestTask:
    def test_weight_formula(self):
        """T1.1-01: weight = 10 * criticality + urgency."""
        task = make_task(criticality=3, urgency=1)
        assert task.weight == 31

    def test_immutability(self):
        """T1.1-02: Task must be frozen (immutable)."""
        task = make_task()
        with pytest.raises(Exception):
            task.duration = 5  # type: ignore[misc]

    def test_window_property(self):
        task = make_task(window_start=10, window_end=50)
        w = task.window
        assert w.start == 10
        assert w.end == 50

    def test_demands_immutable(self):
        task = make_task(demands={"crew": 2})
        assert task.demands["crew"] == 2
        with pytest.raises(Exception):
            task.demands["crew"] = 99  # type: ignore[index]

    def test_depends_on_coerced_to_tuple(self):
        task = Task(
            id=1,
            corridor_id=1,
            asset_id=1,
            window_start=0,
            window_end=50,
            duration=10,
            criticality=1,
            urgency=1,
            depends_on=(2, 3),
        )
        assert isinstance(task.depends_on, tuple)
        assert task.depends_on == (2, 3)


# ---------------------------------------------------------------------------
# Instance tests
# ---------------------------------------------------------------------------


class TestInstance:
    def test_task_lookup_found(self):
        """T1.1-06: Instance.task(id) returns correct task."""
        tasks = [make_task(id=1), make_task(id=2), make_task(id=3)]
        inst = make_instance(tasks=tasks)
        assert inst.task(2).id == 2

    def test_task_lookup_not_found(self):
        """T1.1-06: Unknown task id raises KeyError."""
        inst = make_instance()
        with pytest.raises(KeyError):
            inst.task(999)

    def test_immutability(self):
        inst = make_instance()
        with pytest.raises(Exception):
            inst.horizon = 720  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Schedule tests
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_end_of_task(self):
        """T1.1-07: Schedule.end_of(task) = start + duration."""
        task = make_task(id=1, duration=7)
        sched = Schedule(starts={1: 10})
        assert sched.end_of(task) == 17

    def test_is_scheduled(self):
        sched = Schedule(starts={1: 0, 2: 10})
        assert sched.is_scheduled(1) is True
        assert sched.is_scheduled(99) is False

    def test_end_of_with_int_id_and_duration(self):
        sched = Schedule(starts={5: 20})
        assert sched.end_of(5, duration=15) == 35

    def test_starts_immutable(self):
        sched = Schedule(starts={1: 0})
        with pytest.raises(Exception):
            sched.starts[1] = 99  # type: ignore[index]


# ---------------------------------------------------------------------------
# Corridor / Resource / Timetable tests
# ---------------------------------------------------------------------------


class TestCorridor:
    def test_asset_ids_coerced_to_tuple(self):
        c = Corridor(id=1, traffic_level="high", asset_ids=(10, 20, 30))
        assert isinstance(c.asset_ids, tuple)

    def test_immutability(self):
        c = Corridor(id=1, traffic_level="low", asset_ids=(1,))
        with pytest.raises(Exception):
            c.traffic_level = "high"  # type: ignore[misc]


class TestResource:
    def test_availability_coerced_to_tuple(self):
        avail = [Interval(0, 720), Interval(800, 1440)]
        r = Resource(type="crew", capacity=2, availability=tuple(avail))
        assert isinstance(r.availability, tuple)

    def test_immutability(self):
        r = Resource(type="crew", capacity=1)
        with pytest.raises(Exception):
            r.capacity = 99  # type: ignore[misc]


class TestTimetable:
    def test_intervals_stored(self):
        ti = TrainInterval(start=100, end=120)
        tt = Timetable(corridor_id=1, intervals=(ti,))
        assert tt.intervals[0].start == 100
        assert tt.intervals[0].end == 120

    def test_train_interval_property(self):
        ti = TrainInterval(start=50, end=60)
        assert ti.interval.start == 50
        assert ti.interval.end == 60
