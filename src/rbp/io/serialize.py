"""JSON and CSV serialization for Instance objects.

JSON is the authoritative format. CSV exists for spreadsheet inspection.
All output is deterministic (sorted keys) for reproducible file comparisons.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from rbp.io.input_checks import InstanceError, validate_instance
from rbp.models import Corridor, Instance, Interval, Resource, Task, Timetable, TrainInterval

SCHEMA_VERSION = 1


class InstanceLoadError(Exception):
    """Raised when an instance file is unreadable, malformed, or missing fields."""

    pass


# ---------------------------------------------------------------------------
# Instance <-> dict conversion
# ---------------------------------------------------------------------------


def instance_to_dict(instance: Instance) -> dict[str, Any]:
    """Serialize an Instance to a JSON-compatible dictionary."""
    return {
        "schema_version": SCHEMA_VERSION,
        "horizon": instance.horizon,
        "meta": dict(instance.meta),
        "corridors": [
            {
                "id": c.id,
                "traffic_level": c.traffic_level,
                "asset_ids": sorted(c.asset_ids),
            }
            for c in sorted(instance.corridors, key=lambda c: c.id)
        ],
        "resources": [
            {
                "type": r.type,
                "capacity": r.capacity,
                "availability": [
                    {"start": iv.start, "end": iv.end}
                    for iv in sorted(r.availability, key=lambda x: x.start)
                ],
            }
            for r in sorted(instance.resources, key=lambda r: r.type)
        ],
        "timetable": [
            {
                "corridor_id": tt.corridor_id,
                "intervals": [
                    {"start": ti.start, "end": ti.end}
                    for ti in sorted(tt.intervals, key=lambda x: x.start)
                ],
            }
            for tt in sorted(instance.timetable, key=lambda tt: tt.corridor_id)
        ],
        "tasks": [
            {
                "id": t.id,
                "corridor_id": t.corridor_id,
                "asset_id": t.asset_id,
                "window_start": t.window_start,
                "window_end": t.window_end,
                "duration": t.duration,
                "criticality": t.criticality,
                "urgency": t.urgency,
                "demands": dict(sorted(t.demands.items())),
                "depends_on": sorted(t.depends_on),
            }
            for t in sorted(instance.tasks, key=lambda t: t.id)
        ],
    }


def instance_from_dict(data: dict[str, Any]) -> Instance:
    """Deserialize an Instance from a dictionary. Raises InstanceLoadError on problems."""
    try:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise InstanceLoadError(
                f"Unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
            )

        horizon = _require(data, "horizon", int)

        corridors = tuple(
            Corridor(
                id=_require(c, "id", int),
                traffic_level=_require(c, "traffic_level", str),
                asset_ids=tuple(_require(c, "asset_ids", list)),
            )
            for c in _require(data, "corridors", list)
        )

        resources = tuple(
            Resource(
                type=_require(r, "type", str),
                capacity=_require(r, "capacity", int),
                availability=tuple(
                    Interval(
                        start=_require(iv, "start", int),
                        end=_require(iv, "end", int),
                    )
                    for iv in _require(r, "availability", list)
                ),
            )
            for r in _require(data, "resources", list)
        )

        timetable = tuple(
            Timetable(
                corridor_id=_require(tt, "corridor_id", int),
                intervals=tuple(
                    TrainInterval(
                        start=_require(ti, "start", int),
                        end=_require(ti, "end", int),
                    )
                    for ti in _require(tt, "intervals", list)
                ),
            )
            for tt in _require(data, "timetable", list)
        )

        tasks = tuple(
            Task(
                id=_require(t, "id", int),
                corridor_id=_require(t, "corridor_id", int),
                asset_id=_require(t, "asset_id", int),
                window_start=_require(t, "window_start", int),
                window_end=_require(t, "window_end", int),
                duration=_require(t, "duration", int),
                criticality=_require(t, "criticality", int),
                urgency=_require(t, "urgency", int),
                demands=dict(_require(t, "demands", dict)),
                depends_on=tuple(_require(t, "depends_on", list)),
            )
            for t in _require(data, "tasks", list)
        )

        meta = data.get("meta", {})

        instance = Instance(
            tasks=tasks,
            corridors=corridors,
            resources=resources,
            timetable=timetable,
            horizon=horizon,
            meta=meta,
        )

    except InstanceLoadError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise InstanceLoadError(f"Malformed instance data: {exc}") from exc

    # Validate after deserialization
    errors = validate_instance(instance)
    if errors:
        raise InstanceError(errors)

    return instance


def _require(d: dict, key: str, expected_type: type) -> Any:
    """Retrieve a required field from a dict, raising InstanceLoadError on failure."""
    if key not in d:
        raise InstanceLoadError(f"Missing required field: '{key}'")
    value = d[key]
    if not isinstance(value, expected_type):
        raise InstanceLoadError(
            f"Field '{key}' expected {expected_type.__name__}, got {type(value).__name__}"
        )
    return value


# ---------------------------------------------------------------------------
# JSON save / load
# ---------------------------------------------------------------------------


def save_json(instance: Instance, path: str | Path) -> None:
    """Save instance to a JSON file with sorted keys for determinism."""
    data = instance_to_dict(instance)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True, indent=2)


def load_json(path: str | Path) -> Instance:
    """Load and validate an instance from a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise InstanceLoadError(f"JSON parse error in '{path}': {exc}") from exc
    except OSError as exc:
        raise InstanceLoadError(f"Cannot read file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise InstanceLoadError("JSON root must be an object")

    return instance_from_dict(data)


# ---------------------------------------------------------------------------
# CSV directory save / load
# ---------------------------------------------------------------------------

_TASK_FIELDS = [
    "id", "corridor_id", "asset_id", "window_start", "window_end",
    "duration", "criticality", "urgency", "demands", "depends_on",
]
_CORRIDOR_FIELDS = ["id", "traffic_level", "asset_ids"]
_RESOURCE_FIELDS = ["type", "capacity", "availability"]
_TRAIN_FIELDS = ["corridor_id", "start", "end"]


def save_csv_dir(instance: Instance, directory: str | Path) -> None:
    """Save instance to a directory of CSV files (tasks/corridors/resources/trains)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    # tasks.csv
    with open(directory / "tasks.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_TASK_FIELDS)
        writer.writeheader()
        for t in sorted(instance.tasks, key=lambda t: t.id):
            demands_str = ";".join(f"{k}:{v}" for k, v in sorted(t.demands.items()))
            deps_str = ";".join(str(d) for d in sorted(t.depends_on))
            writer.writerow({
                "id": t.id,
                "corridor_id": t.corridor_id,
                "asset_id": t.asset_id,
                "window_start": t.window_start,
                "window_end": t.window_end,
                "duration": t.duration,
                "criticality": t.criticality,
                "urgency": t.urgency,
                "demands": demands_str,
                "depends_on": deps_str,
            })

    # corridors.csv
    with open(directory / "corridors.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CORRIDOR_FIELDS)
        writer.writeheader()
        for c in sorted(instance.corridors, key=lambda c: c.id):
            writer.writerow({
                "id": c.id,
                "traffic_level": c.traffic_level,
                "asset_ids": ";".join(str(a) for a in sorted(c.asset_ids)),
            })

    # resources.csv
    with open(directory / "resources.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_RESOURCE_FIELDS)
        writer.writeheader()
        for r in sorted(instance.resources, key=lambda r: r.type):
            avail_str = ";".join(
                f"{iv.start}:{iv.end}" for iv in sorted(r.availability, key=lambda x: x.start)
            )
            writer.writerow({
                "type": r.type,
                "capacity": r.capacity,
                "availability": avail_str,
            })

    # trains.csv
    with open(directory / "trains.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_TRAIN_FIELDS)
        writer.writeheader()
        for tt in sorted(instance.timetable, key=lambda tt: tt.corridor_id):
            for ti in sorted(tt.intervals, key=lambda x: x.start):
                writer.writerow({
                    "corridor_id": tt.corridor_id,
                    "start": ti.start,
                    "end": ti.end,
                })


def load_csv_dir(directory: str | Path, horizon: int = 1440, meta: dict | None = None) -> Instance:
    """Load an instance from a directory of CSV files."""
    directory = Path(directory)

    try:
        # tasks.csv
        with open(directory / "tasks.csv", "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            tasks = []
            for row in reader:
                demands: dict[str, int] = {}
                if row["demands"].strip():
                    for pair in row["demands"].split(";"):
                        k, v = pair.split(":")
                        demands[k.strip()] = int(v.strip())
                depends_on: tuple[int, ...] = ()
                if row["depends_on"].strip():
                    depends_on = tuple(int(d) for d in row["depends_on"].split(";"))
                tasks.append(Task(
                    id=int(row["id"]),
                    corridor_id=int(row["corridor_id"]),
                    asset_id=int(row["asset_id"]),
                    window_start=int(row["window_start"]),
                    window_end=int(row["window_end"]),
                    duration=int(row["duration"]),
                    criticality=int(row["criticality"]),
                    urgency=int(row["urgency"]),
                    demands=demands,
                    depends_on=depends_on,
                ))

        # corridors.csv
        with open(directory / "corridors.csv", "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            corridors = []
            for row in reader:
                asset_ids = tuple(int(a) for a in row["asset_ids"].split(";") if a.strip())
                corridors.append(Corridor(
                    id=int(row["id"]),
                    traffic_level=row["traffic_level"],
                    asset_ids=asset_ids,
                ))

        # resources.csv
        with open(directory / "resources.csv", "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            resources = []
            for row in reader:
                availability: tuple[Interval, ...] = ()
                if row["availability"].strip():
                    availability = tuple(
                        Interval(start=int(s), end=int(e))
                        for s, e in (pair.split(":") for pair in row["availability"].split(";"))
                    )
                resources.append(Resource(
                    type=row["type"],
                    capacity=int(row["capacity"]),
                    availability=availability,
                ))

        # trains.csv
        train_map: dict[int, list[TrainInterval]] = {}
        with open(directory / "trains.csv", "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = int(row["corridor_id"])
                ti = TrainInterval(start=int(row["start"]), end=int(row["end"]))
                train_map.setdefault(cid, []).append(ti)
        timetable = tuple(
            Timetable(corridor_id=cid, intervals=tuple(intervals))
            for cid, intervals in sorted(train_map.items())
        )

    except (KeyError, ValueError, OSError) as exc:
        raise InstanceLoadError(f"CSV load error: {exc}") from exc

    instance = Instance(
        tasks=tuple(tasks),
        corridors=tuple(corridors),
        resources=tuple(resources),
        timetable=timetable,
        horizon=horizon,
        meta=meta or {},
    )

    errors = validate_instance(instance)
    if errors:
        raise InstanceError(errors)

    return instance
