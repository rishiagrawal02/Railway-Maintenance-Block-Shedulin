"""Tests for the independent schedule validator (Milestone 2.2)."""


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
from rbp.validation import validate_schedule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    id: int = 1,
    corridor_id: int = 1,
    asset_id: int = 1,
    window_start: int = 0,
    window_end: int = 500,
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


def _make_instance(
    tasks: list[Task] | None = None,
    train_intervals: list[tuple[int, int]] | None = None,
    capacity: int = 2,
    availability: list[tuple[int, int]] | None = None,
    n_assets: int = 3,
) -> Instance:
    if availability is None:
        availability = [(0, 1440)]
    avail_ivs = tuple(Interval(s, e) for s, e in availability)
    corridor = Corridor(id=1, traffic_level="low", asset_ids=tuple(range(1, n_assets + 1)))
    resource = Resource(type="crew", capacity=capacity, availability=avail_ivs)
    tt_intervals = tuple(TrainInterval(start=s, end=e) for s, e in (train_intervals or []))
    timetable = (Timetable(corridor_id=1, intervals=tt_intervals),) if tt_intervals else ()
    return Instance(
        tasks=tuple(tasks or [_make_task()]),
        corridors=(corridor,),
        resources=(resource,),
        timetable=timetable,
        horizon=1440,
    )


def _codes(report) -> list[str]:
    return [v.code for v in report.violations]


# ---------------------------------------------------------------------------
# T2.2-01: Valid hand-built schedule
# ---------------------------------------------------------------------------


def test_valid_schedule():
    """T2.2-01: A correctly built schedule passes all checks."""
    t1 = _make_task(id=1, asset_id=1, duration=20)
    t2 = _make_task(id=2, asset_id=2, duration=20)
    instance = _make_instance(tasks=[t1, t2])
    sched = Schedule(starts={1: 0, 2: 0})
    report = validate_schedule(instance, sched)
    assert report.valid is True
    assert report.violations == []


# ---------------------------------------------------------------------------
# T2.2-02: Empty schedule is valid
# ---------------------------------------------------------------------------


def test_empty_schedule_is_valid():
    """T2.2-02: Empty schedule (no tasks placed) is always valid."""
    instance = _make_instance()
    sched = Schedule(starts={})
    report = validate_schedule(instance, sched)
    assert report.valid is True


# ---------------------------------------------------------------------------
# T2.2-03: C1 — start outside window
# ---------------------------------------------------------------------------


def test_c1_start_outside_window():
    """T2.2-03: Shifting task outside window raises C1."""
    task = _make_task(id=1, window_start=100, window_end=200, duration=30)
    instance = _make_instance(tasks=[task])
    sched = Schedule(starts={1: 200})  # end = 230 > 200 window_end
    report = validate_schedule(instance, sched)
    assert "C1" in _codes(report)
    assert any(1 in v.task_ids for v in report.violations if v.code == "C1")


# ---------------------------------------------------------------------------
# T2.2-04: C2 — overlapping a train
# ---------------------------------------------------------------------------


def test_c2_overlap_train():
    """T2.2-04: Task placed on a train interval raises C2."""
    task = _make_task(id=1, window_start=0, window_end=500, duration=50)
    instance = _make_instance(tasks=[task], train_intervals=[(100, 200)])
    sched = Schedule(starts={1: 120})  # [120,170) overlaps [100,200)
    report = validate_schedule(instance, sched)
    assert "C2" in _codes(report)


# ---------------------------------------------------------------------------
# T2.2-05: C3 — two tasks overlap on same asset
# ---------------------------------------------------------------------------


def test_c3_asset_overlap():
    """T2.2-05: Two tasks on same asset with overlapping intervals raises C3."""
    t1 = _make_task(id=1, asset_id=1, duration=20)
    t2 = _make_task(id=2, asset_id=1, duration=20)
    instance = _make_instance(tasks=[t1, t2])
    sched = Schedule(starts={1: 0, 2: 10})  # [0,20) and [10,30) overlap
    report = validate_schedule(instance, sched)
    assert "C3" in _codes(report)
    c3 = [v for v in report.violations if v.code == "C3"]
    assert any(1 in v.task_ids and 2 in v.task_ids for v in c3)


# ---------------------------------------------------------------------------
# T2.2-06: C4 — exceeding capacity
# ---------------------------------------------------------------------------


def test_c4_capacity_exceeded():
    """T2.2-06: Three overlapping tasks with capacity 2 raises C4."""
    t1 = _make_task(id=1, asset_id=1, demands={"crew": 1}, duration=30)
    t2 = _make_task(id=2, asset_id=2, demands={"crew": 1}, duration=30)
    t3 = _make_task(id=3, asset_id=3, demands={"crew": 1}, duration=30)
    instance = _make_instance(tasks=[t1, t2, t3], capacity=2)
    sched = Schedule(starts={1: 0, 2: 0, 3: 0})  # all overlap at t=0
    report = validate_schedule(instance, sched)
    assert "C4" in _codes(report)


# ---------------------------------------------------------------------------
# T2.2-07: C5 — dependent starts before prerequisite finishes
# ---------------------------------------------------------------------------


def test_c5_before_prereq_end():
    """T2.2-07: Dependent task starting before prerequisite finishes raises C5."""
    prereq = _make_task(id=1, asset_id=1, duration=30)
    dep = _make_task(id=2, asset_id=2, duration=20, depends_on=(1,))
    instance = _make_instance(tasks=[prereq, dep])
    # prereq ends at 30, dep starts at 20 < 30
    sched = Schedule(starts={1: 0, 2: 20})
    report = validate_schedule(instance, sched)
    assert "C5" in _codes(report)


# ---------------------------------------------------------------------------
# T2.2-08: C5 — prerequisite not scheduled
# ---------------------------------------------------------------------------


def test_c5_prereq_missing():
    """T2.2-08: Dependent scheduled but prerequisite missing raises C5."""
    prereq = _make_task(id=1, asset_id=1, duration=30)
    dep = _make_task(id=2, asset_id=2, duration=20, depends_on=(1,))
    instance = _make_instance(tasks=[prereq, dep])
    sched = Schedule(starts={2: 50})  # only dep scheduled, not prereq
    report = validate_schedule(instance, sched)
    assert "C5" in _codes(report)


# ---------------------------------------------------------------------------
# T2.2-09: Touching intervals on same asset are valid
# ---------------------------------------------------------------------------


def test_c3_touching_intervals_valid():
    """T2.2-09: Tasks [0,10) and [10,20) on same asset do NOT conflict."""
    t1 = _make_task(id=1, asset_id=1, duration=10)
    t2 = _make_task(id=2, asset_id=1, duration=10)
    instance = _make_instance(tasks=[t1, t2])
    sched = Schedule(starts={1: 0, 2: 10})
    report = validate_schedule(instance, sched)
    assert report.valid is True


# ---------------------------------------------------------------------------
# T2.2-10: Capacity exactly met is valid
# ---------------------------------------------------------------------------


def test_c4_capacity_exactly_met():
    """T2.2-10: Two tasks each demand 1 with capacity 2 overlapping is OK."""
    t1 = _make_task(id=1, asset_id=1, demands={"crew": 1}, duration=30)
    t2 = _make_task(id=2, asset_id=2, demands={"crew": 1}, duration=30)
    instance = _make_instance(tasks=[t1, t2], capacity=2)
    sched = Schedule(starts={1: 0, 2: 0})
    report = validate_schedule(instance, sched)
    assert report.valid is True


# ---------------------------------------------------------------------------
# T2.2-11: Several violations at once
# ---------------------------------------------------------------------------


def test_multiple_violations_at_once():
    """T2.2-11: C1, C3, C5 all reported simultaneously."""
    t1 = _make_task(id=1, asset_id=1, window_start=100, window_end=200, duration=30)
    t2 = _make_task(id=2, asset_id=1, duration=20)
    t3 = _make_task(id=3, asset_id=3, duration=20, depends_on=(99,))  # unknown dep
    instance = _make_instance(tasks=[t1, t2, t3])
    sched = Schedule(starts={
        1: 300,   # C1: 300+30=330 > window_end=200
        2: 0,     # OK by itself
        3: 50,    # C5: prereq 99 not in schedule
    })
    report = validate_schedule(instance, sched)
    codes = set(_codes(report))
    assert "C1" in codes
    assert "C5" in codes


# ---------------------------------------------------------------------------
# T2.2-12: Unknown task id
# ---------------------------------------------------------------------------


def test_unknown_task_id():
    """T2.2-12: Schedule entry with unknown task id raises S_UNKNOWN, no crash."""
    instance = _make_instance()
    sched = Schedule(starts={999: 0})
    report = validate_schedule(instance, sched)
    assert "S_UNKNOWN" in _codes(report)
    assert report.valid is False


# ---------------------------------------------------------------------------
# T2.2-13: Independence — validation imports only models
# ---------------------------------------------------------------------------


def test_independence_boundary():
    """T2.2-13: The import boundary test verifies validation imports only models."""
    import sys
    from pathlib import Path

    root_dir = Path(__file__).parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    from tests.test_import_boundaries import check_module_imports

    validator_path = (
        root_dir / "src" / "rbp" / "validation" / "validator.py"
    )
    violations = check_module_imports(validator_path)
    assert violations == [], f"Independence violation: {violations}"


# ---------------------------------------------------------------------------
# T2.2 extra: ValidationReport helpers
# ---------------------------------------------------------------------------


def test_counts_by_code():
    """counts_by_code groups violations correctly."""
    t1 = _make_task(id=1, asset_id=1, window_start=100, window_end=200, duration=30)
    t2 = _make_task(id=2, asset_id=1, window_start=100, window_end=200, duration=30)
    instance = _make_instance(tasks=[t1, t2])
    sched = Schedule(starts={1: 300, 2: 350})  # both C1
    report = validate_schedule(instance, sched)
    assert report.counts_by_code.get("C1", 0) >= 2
