"""Tests for input validation (Milestone 1.2)."""


from rbp.io.input_checks import (
    E_DEMAND,
    E_DEP_CYCLE,
    E_DEP_SELF,
    E_DUP_ID,
    E_DURATION,
    E_HORIZON,
    E_RANGE,
    E_TRAIN_BAD,
    E_UNKNOWN_REF,
    E_WINDOW,
    InstanceError,
    validate_instance,
)
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_corridor(id: int = 1, asset_ids: tuple = (1,)) -> Corridor:
    return Corridor(id=id, traffic_level="low", asset_ids=asset_ids)


def _make_resource(type: str = "crew", capacity: int = 2) -> Resource:
    return Resource(type=type, capacity=capacity, availability=(Interval(0, 1440),))


def _make_task(
    id: int = 1,
    corridor_id: int = 1,
    asset_id: int = 1,
    window_start: int = 0,
    window_end: int = 100,
    duration: int = 30,
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


def _valid_instance(tasks: list[Task] | None = None) -> Instance:
    """Build a known-valid small instance."""
    return Instance(
        tasks=tuple(tasks or [_make_task()]),
        corridors=(_make_corridor(),),
        resources=(_make_resource(),),
        timetable=(),
        horizon=1440,
    )


def _codes(errors) -> list[str]:
    return [e.code for e in errors]


# ---------------------------------------------------------------------------
# T1.2-01: Valid instance
# ---------------------------------------------------------------------------


def test_valid_instance_returns_no_errors():
    """T1.2-01: A clean instance returns empty list."""
    errors = validate_instance(_valid_instance())
    assert errors == []


# ---------------------------------------------------------------------------
# T1.2-02: Zero / negative duration
# ---------------------------------------------------------------------------


def test_zero_duration():
    """T1.2-02: duration == 0 triggers E_DURATION."""
    task = _make_task(duration=0)
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_DURATION in codes


def test_negative_duration():
    """T1.2-02: negative duration triggers E_DURATION."""
    task = _make_task(duration=-5)
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_DURATION in codes


# ---------------------------------------------------------------------------
# T1.2-03: Window equals duration (edge case – no error)
# ---------------------------------------------------------------------------


def test_window_equals_duration_is_valid():
    """T1.2-03: window length == duration is OK."""
    task = _make_task(window_start=10, window_end=20, duration=10)
    inst = _valid_instance(tasks=[task])
    errors = validate_instance(inst)
    assert errors == []


# ---------------------------------------------------------------------------
# T1.2-04: Window shorter than duration
# ---------------------------------------------------------------------------


def test_window_shorter_than_duration():
    """T1.2-04: window_end - window_start < duration triggers E_WINDOW."""
    task = _make_task(window_start=10, window_end=19, duration=10)
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_WINDOW in codes


# ---------------------------------------------------------------------------
# T1.2-05: Window beyond horizon
# ---------------------------------------------------------------------------


def test_window_beyond_horizon():
    """T1.2-05: window_end > horizon triggers E_HORIZON."""
    task = _make_task(window_start=1000, window_end=1500, duration=100)
    inst = Instance(
        tasks=(task,),
        corridors=(_make_corridor(),),
        resources=(_make_resource(),),
        timetable=(),
        horizon=1440,
    )
    codes = _codes(validate_instance(inst))
    assert E_HORIZON in codes


# ---------------------------------------------------------------------------
# T1.2-06: Duplicate task ids
# ---------------------------------------------------------------------------


def test_duplicate_task_ids():
    """T1.2-06: Two tasks with same id trigger E_DUP_ID."""
    t1 = _make_task(id=4)
    t2 = _make_task(id=4, window_start=200, window_end=300)
    inst = _valid_instance(tasks=[t1, t2])
    codes = _codes(validate_instance(inst))
    assert E_DUP_ID in codes


# ---------------------------------------------------------------------------
# T1.2-07: Unknown corridor and resource references
# ---------------------------------------------------------------------------


def test_unknown_corridor_ref():
    """T1.2-07: corridor_id not in corridors triggers E_UNKNOWN_REF."""
    task = _make_task(corridor_id=99)
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_UNKNOWN_REF in codes


def test_unknown_resource_type_in_demand():
    """T1.2-07: demand for unknown resource type triggers E_UNKNOWN_REF."""
    task = _make_task(demands={"phantom_type": 1})
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_UNKNOWN_REF in codes


# ---------------------------------------------------------------------------
# T1.2-08: Demand above capacity
# ---------------------------------------------------------------------------


def test_demand_exceeds_capacity():
    """T1.2-08: demand 3 with capacity 2 triggers E_DEMAND."""
    task = _make_task(demands={"crew": 3})
    inst = Instance(
        tasks=(task,),
        corridors=(_make_corridor(),),
        resources=(_make_resource(capacity=2),),
        timetable=(),
        horizon=1440,
    )
    codes = _codes(validate_instance(inst))
    assert E_DEMAND in codes


# ---------------------------------------------------------------------------
# T1.2-09: Dependency cycle
# ---------------------------------------------------------------------------


def test_dependency_cycle():
    """T1.2-09: A->B->A cycle triggers E_DEP_CYCLE."""
    t1 = _make_task(id=1, depends_on=(2,))
    t2 = _make_task(id=2, depends_on=(1,))
    inst = _valid_instance(tasks=[t1, t2])
    codes = _codes(validate_instance(inst))
    assert E_DEP_CYCLE in codes


# ---------------------------------------------------------------------------
# T1.2-10: Self dependency
# ---------------------------------------------------------------------------


def test_self_dependency():
    """T1.2-10: Task depending on itself triggers E_DEP_SELF."""
    task = _make_task(id=1, depends_on=(1,))
    inst = _valid_instance(tasks=[task])
    codes = _codes(validate_instance(inst))
    assert E_DEP_SELF in codes


# ---------------------------------------------------------------------------
# T1.2-11: Multiple faults at once
# ---------------------------------------------------------------------------


def test_multiple_faults_at_once():
    """T1.2-11: Multiple simultaneous issues all reported."""
    t1 = _make_task(id=1, duration=0)  # E_DURATION
    t2 = _make_task(id=2, corridor_id=99)  # E_UNKNOWN_REF (corridor)
    t3 = _make_task(id=3, criticality=10)  # E_RANGE
    inst = _valid_instance(tasks=[t1, t2, t3])
    codes = _codes(validate_instance(inst))
    assert E_DURATION in codes
    assert E_UNKNOWN_REF in codes
    assert E_RANGE in codes
    assert len(set(codes)) >= 3


# ---------------------------------------------------------------------------
# Additional: criticality/urgency range
# ---------------------------------------------------------------------------


def test_criticality_out_of_range():
    task = _make_task(criticality=6)
    codes = _codes(validate_instance(_valid_instance(tasks=[task])))
    assert E_RANGE in codes


def test_urgency_out_of_range():
    task = _make_task(urgency=0)
    codes = _codes(validate_instance(_valid_instance(tasks=[task])))
    assert E_RANGE in codes


# ---------------------------------------------------------------------------
# Additional: bad train interval
# ---------------------------------------------------------------------------


def test_bad_train_interval():
    """E_TRAIN_BAD: train interval with start >= end."""
    ti = TrainInterval(start=100, end=100)
    tt = Timetable(corridor_id=1, intervals=(ti,))
    inst = Instance(
        tasks=(_make_task(),),
        corridors=(_make_corridor(),),
        resources=(_make_resource(),),
        timetable=(tt,),
        horizon=1440,
    )
    codes = _codes(validate_instance(inst))
    assert E_TRAIN_BAD in codes


# ---------------------------------------------------------------------------
# Additional: InstanceError wrapper
# ---------------------------------------------------------------------------


def test_instance_error_wraps_list():
    from rbp.io.input_checks import InputError

    errors = [InputError(E_DURATION, "bad"), InputError(E_WINDOW, "bad2")]
    exc = InstanceError(errors)
    assert exc.errors == errors
    assert E_DURATION in str(exc)
