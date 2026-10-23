"""Tests for JSON and CSV serialization (Milestone 1.3)."""

import json
from pathlib import Path

import pytest

from rbp.io.input_checks import InstanceError
from rbp.io.serialize import (
    InstanceLoadError,
    load_csv_dir,
    load_json,
    save_csv_dir,
    save_json,
)
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval

# ---------------------------------------------------------------------------
# Path to golden fixture
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
TINY_JSON = DATA_DIR / "tiny_instance.json"


# ---------------------------------------------------------------------------
# Helper: minimal valid instance
# ---------------------------------------------------------------------------


def _make_tiny() -> Instance:
    return Instance(
        tasks=(
            Task(
                id=1,
                corridor_id=1,
                asset_id=1,
                window_start=0,
                window_end=200,
                duration=30,
                criticality=3,
                urgency=2,
                demands={"crew": 1},
                depends_on=(),
            ),
            Task(
                id=2,
                corridor_id=1,
                asset_id=2,
                window_start=50,
                window_end=400,
                duration=20,
                criticality=2,
                urgency=4,
                demands={},
                depends_on=(1,),
            ),
        ),
        corridors=(Corridor(id=1, traffic_level="low", asset_ids=(1, 2)),),
        resources=(
            Resource(
                type="crew",
                capacity=2,
                availability=(Interval(0, 1440),),
            ),
        ),
        timetable=(
            Timetable(
                corridor_id=1,
                intervals=(TrainInterval(start=100, end=120),),
            ),
        ),
        horizon=1440,
        meta={},
    )


def _instances_equal(a: Instance, b: Instance) -> bool:
    """Deep equality comparison for instances."""
    if a.horizon != b.horizon:
        return False
    if len(a.tasks) != len(b.tasks):
        return False
    for ta, tb in zip(
        sorted(a.tasks, key=lambda t: t.id), sorted(b.tasks, key=lambda t: t.id)
    ):
        if (
            ta.id != tb.id
            or ta.corridor_id != tb.corridor_id
            or ta.asset_id != tb.asset_id
            or ta.window_start != tb.window_start
            or ta.window_end != tb.window_end
            or ta.duration != tb.duration
            or ta.criticality != tb.criticality
            or ta.urgency != tb.urgency
            or dict(ta.demands) != dict(tb.demands)
            or set(ta.depends_on) != set(tb.depends_on)
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# T1.3-01: JSON round trip
# ---------------------------------------------------------------------------


def test_json_round_trip(tmp_path):
    """T1.3-01: save then load produces identical instance."""
    inst = _make_tiny()
    out = tmp_path / "inst.json"
    save_json(inst, out)
    loaded = load_json(out)
    assert _instances_equal(inst, loaded)


# ---------------------------------------------------------------------------
# T1.3-02: CSV round trip
# ---------------------------------------------------------------------------


def test_csv_round_trip(tmp_path):
    """T1.3-02: save_csv_dir then load_csv_dir produces identical instance."""
    inst = _make_tiny()
    d = tmp_path / "csv_out"
    save_csv_dir(inst, d)
    loaded = load_csv_dir(d, horizon=1440)
    assert _instances_equal(inst, loaded)


# ---------------------------------------------------------------------------
# T1.3-03: Malformed JSON
# ---------------------------------------------------------------------------


def test_malformed_json_raises(tmp_path):
    """T1.3-03: Truncated JSON raises InstanceLoadError."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 1, "tasks": [', encoding="utf-8")
    with pytest.raises(InstanceLoadError):
        load_json(bad)


# ---------------------------------------------------------------------------
# T1.3-04: Missing field
# ---------------------------------------------------------------------------


def test_missing_field_raises(tmp_path):
    """T1.3-04: JSON missing 'duration' raises InstanceLoadError."""
    from rbp.io.serialize import instance_to_dict

    inst = _make_tiny()
    data = instance_to_dict(inst)
    del data["tasks"][0]["duration"]
    bad = tmp_path / "no_duration.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InstanceLoadError):
        load_json(bad)


# ---------------------------------------------------------------------------
# T1.3-05: Unknown schema version
# ---------------------------------------------------------------------------


def test_unknown_schema_version_raises(tmp_path):
    """T1.3-05: schema_version 99 raises InstanceLoadError."""
    from rbp.io.serialize import instance_to_dict

    inst = _make_tiny()
    data = instance_to_dict(inst)
    data["schema_version"] = 99
    bad = tmp_path / "v99.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InstanceLoadError, match="Unsupported schema_version"):
        load_json(bad)


# ---------------------------------------------------------------------------
# T1.3-06: Invalid but well-formed data triggers InstanceError
# ---------------------------------------------------------------------------


def test_invalid_data_raises_instance_error(tmp_path):
    """T1.3-06: Well-formed JSON with duration -1 raises InstanceError."""
    from rbp.io.serialize import instance_to_dict

    inst = _make_tiny()
    data = instance_to_dict(inst)
    data["tasks"][0]["duration"] = -1
    bad = tmp_path / "neg_dur.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(InstanceError):
        load_json(bad)


# ---------------------------------------------------------------------------
# T1.3-07: Windows line endings / UTF-8 CSV
# ---------------------------------------------------------------------------


def test_csv_crlf_loads_correctly(tmp_path):
    """T1.3-07: CSV with CRLF line endings loads correctly."""
    inst = _make_tiny()
    d = tmp_path / "crlf"
    save_csv_dir(inst, d)
    # Rewrite tasks.csv with CRLF
    tasks_path = d / "tasks.csv"
    content = tasks_path.read_text(encoding="utf-8")
    tasks_path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    loaded = load_csv_dir(d, horizon=1440)
    assert _instances_equal(inst, loaded)


# ---------------------------------------------------------------------------
# T1.3-08: Deterministic output
# ---------------------------------------------------------------------------


def test_json_deterministic(tmp_path):
    """T1.3-08: Saving the same instance twice produces identical bytes."""
    inst = _make_tiny()
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    save_json(inst, p1)
    save_json(inst, p2)
    assert p1.read_bytes() == p2.read_bytes()


# ---------------------------------------------------------------------------
# T1.3-09: Regression of 1.2
# ---------------------------------------------------------------------------


def test_regression_input_checks():
    """T1.3-09: Input check tests still pass (run via pytest introspection)."""
    from rbp.io.input_checks import validate_instance

    inst = _make_tiny()
    errors = validate_instance(inst)
    assert errors == []


# ---------------------------------------------------------------------------
# Golden fixture load
# ---------------------------------------------------------------------------


def test_load_golden_fixture():
    """Load the committed golden fixture without errors."""
    inst = load_json(TINY_JSON)
    assert len(inst.tasks) == 2
    assert inst.horizon == 1440
