"""Input validation for scheduling Instance objects.

Returns a collected list of InputError objects rather than raising on the
first error, so the UI can display all problems at once.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from rbp.models.instance import Instance


@dataclass(frozen=True)
class InputError:
    """Represents a single validation error with an error code and message."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class InstanceError(Exception):
    """Exception wrapping a list of InputError objects."""

    def __init__(self, errors: list[InputError]) -> None:
        self.errors = errors
        codes = ", ".join(e.code for e in errors)
        super().__init__(f"Instance validation failed: {codes}")


# Error code constants
E_DURATION = "E_DURATION"
E_WINDOW = "E_WINDOW"
E_HORIZON = "E_HORIZON"
E_DUP_ID = "E_DUP_ID"
E_UNKNOWN_REF = "E_UNKNOWN_REF"
E_DEMAND = "E_DEMAND"
E_RANGE = "E_RANGE"
E_DEP_UNKNOWN = "E_DEP_UNKNOWN"
E_DEP_SELF = "E_DEP_SELF"
E_DEP_CYCLE = "E_DEP_CYCLE"
E_TRAIN_BAD = "E_TRAIN_BAD"


def validate_instance(instance: Instance) -> list[InputError]:
    """Validate an Instance and return all InputError objects found.

    Returns an empty list if the instance is valid.
    """
    errors: list[InputError] = []

    # Collect reference sets
    corridor_ids = {c.id for c in instance.corridors}
    asset_ids_by_corridor: dict[int, set[int]] = {
        c.id: set(c.asset_ids) for c in instance.corridors
    }
    all_asset_ids: set[int] = set()
    for aids in asset_ids_by_corridor.values():
        all_asset_ids.update(aids)
    resource_types = {r.type for r in instance.resources}
    resource_capacity: dict[str, int] = {r.type: r.capacity for r in instance.resources}

    # Check for duplicate task ids
    seen_task_ids: set[int] = set()
    for task in instance.tasks:
        if task.id in seen_task_ids:
            errors.append(InputError(E_DUP_ID, f"Duplicate task id: {task.id}"))
        seen_task_ids.add(task.id)

    # Per-task validations
    for task in instance.tasks:
        # E_DURATION: duration must be positive
        if task.duration <= 0:
            errors.append(
                InputError(E_DURATION, f"Task {task.id}: duration must be > 0, got {task.duration}")
            )

        # E_WINDOW: window must be at least as long as duration
        window_len = task.window_end - task.window_start
        if window_len < task.duration:
            errors.append(
                InputError(
                    E_WINDOW,
                    f"Task {task.id}: window length {window_len} < duration {task.duration}",
                )
            )

        # E_HORIZON: window must lie within [0, horizon]
        if task.window_start < 0 or task.window_end > instance.horizon:
            errors.append(
                InputError(
                    E_HORIZON,
                    f"Task {task.id}: window [{task.window_start},{task.window_end})"
                    f" outside horizon [0,{instance.horizon}]",
                )
            )

        # E_UNKNOWN_REF: corridor reference
        if task.corridor_id not in corridor_ids:
            errors.append(
                InputError(E_UNKNOWN_REF, f"Task {task.id}: unknown corridor_id {task.corridor_id}")
            )
        else:
            # E_UNKNOWN_REF: asset reference within corridor
            if task.asset_id not in asset_ids_by_corridor.get(task.corridor_id, set()):
                errors.append(
                    InputError(
                        E_UNKNOWN_REF,
                        f"Task {task.id}: asset_id {task.asset_id}"
                        f" not in corridor {task.corridor_id}",
                    )
                )

        # E_DEMAND: demand must not exceed resource capacity
        for res_type, demand in task.demands.items():
            if res_type not in resource_types:
                errors.append(
                    InputError(E_UNKNOWN_REF, f"Task {task.id}: unknown resource type '{res_type}'")
                )
            else:
                cap = resource_capacity[res_type]
                if demand > cap:
                    errors.append(
                        InputError(
                            E_DEMAND,
                            f"Task {task.id}: demand {demand} for '{res_type}'"
                            f" exceeds capacity {cap}",
                        )
                    )

        # E_RANGE: criticality and urgency must be in 1-5
        if not (1 <= task.criticality <= 5):
            errors.append(
                InputError(E_RANGE, f"Task {task.id}: criticality {task.criticality} not in [1,5]")
            )
        if not (1 <= task.urgency <= 5):
            errors.append(
                InputError(E_RANGE, f"Task {task.id}: urgency {task.urgency} not in [1,5]")
            )

        # E_DEP_SELF: task must not depend on itself
        if task.id in task.depends_on:
            errors.append(InputError(E_DEP_SELF, f"Task {task.id}: depends on itself"))

        # E_DEP_UNKNOWN: dependency must reference a valid task id
        for dep_id in task.depends_on:
            if dep_id not in seen_task_ids:
                errors.append(
                    InputError(E_DEP_UNKNOWN, f"Task {task.id}: depends on unknown task {dep_id}")
                )

    # E_DEP_CYCLE: Kahn's topological sort to detect cycles
    cycle_errors = _check_dependency_cycles(instance)
    errors.extend(cycle_errors)

    # E_TRAIN_BAD: train intervals must have start < end
    for timetable in instance.timetable:
        for ti in timetable.intervals:
            if ti.start >= ti.end:
                errors.append(
                    InputError(
                        E_TRAIN_BAD,
                        f"Corridor {timetable.corridor_id}: train interval"
                        f" [{ti.start},{ti.end}) has start >= end",
                    )
                )

    return errors


def _check_dependency_cycles(instance: Instance) -> list[InputError]:
    """Run Kahn's topological sort on task dependency graph, return cycle errors."""
    task_ids = {t.id for t in instance.tasks}
    in_degree: dict[int, int] = {t.id: 0 for t in instance.tasks}
    graph: dict[int, list[int]] = {t.id: [] for t in instance.tasks}

    for task in instance.tasks:
        for dep_id in task.depends_on:
            # Only consider valid deps (unknown refs caught elsewhere)
            if dep_id in task_ids and dep_id != task.id:
                graph[dep_id].append(task.id)
                in_degree[task.id] += 1

    queue: deque[int] = deque(tid for tid, deg in in_degree.items() if deg == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited < len(task_ids):
        return [InputError(E_DEP_CYCLE, "Dependency graph contains a cycle")]
    return []
