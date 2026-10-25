"""Constraint predicates C1-C5 used by all scheduling algorithms.

These predicates share NO code with the independent validator (rbp.validation).
Check order for first_violation is deterministic: C1 → C2 → C3 → C4 → C5.

Interval convention: half-open [start, end). Two tasks touching at a boundary
(one ends at t, the next starts at t) do NOT conflict.
"""

from __future__ import annotations

import bisect

from rbp.constraints.state import PlacementState
from rbp.models.instance import Instance
from rbp.models.task import Task

# ---------------------------------------------------------------------------
# C1: Time-window feasibility
# ---------------------------------------------------------------------------


def c1_window_ok(task: Task, start: int) -> bool:
    """C1: Task must start >= window_start and end <= window_end."""
    end = start + task.duration
    return task.window_start <= start and end <= task.window_end


# ---------------------------------------------------------------------------
# C2: Train conflict avoidance
# ---------------------------------------------------------------------------


def c2_train_ok(instance: Instance, task: Task, start: int) -> bool:
    """C2: Task interval [start, end) must not overlap any train interval on its corridor."""
    end = start + task.duration
    timetable = instance.timetable_for(task.corridor_id)
    if timetable is None:
        return True
    for ti in timetable.intervals:
        # Overlaps if max(starts) < min(ends)
        if max(start, ti.start) < min(end, ti.end):
            return False
    return True


# ---------------------------------------------------------------------------
# C3: Asset conflict avoidance (mutual exclusion)
# ---------------------------------------------------------------------------


def c3_asset_ok(state: PlacementState, task: Task, start: int) -> bool:
    """C3: No already-placed task on the same asset may overlap [start, end).

    Uses the sorted (start, end) list in PlacementState with bisect for efficiency.
    """
    end = start + task.duration
    alist = state.asset_intervals(task.asset_id)
    if not alist:
        return True

    # Find the rightmost interval whose start < end
    idx = bisect.bisect_left(alist, (end, end))
    # Check the interval just before idx (could overlap)
    if idx > 0:
        prev_start, prev_end = alist[idx - 1]
        if prev_end > start:  # overlap
            return False

    # Also check idx itself (start might be < end)
    if idx < len(alist):
        next_start, next_end = alist[idx]
        if max(start, next_start) < min(end, next_end):
            return False

    return True


# ---------------------------------------------------------------------------
# C4: Resource capacity and availability
# ---------------------------------------------------------------------------


def c4_resource_ok(state: PlacementState, instance: Instance, task: Task, start: int) -> bool:
    """C4: Resource demands must not exceed capacity AND must lie within availability.

    Checks every minute in [start, end) — O(duration) per resource type.
    """
    end = start + task.duration
    for res_type, demand in task.demands.items():
        try:
            resource = instance.resource(res_type)
        except KeyError:
            return False  # unknown resource type → infeasible

        capacity = resource.capacity
        usage = state._resource_usage[res_type]
        avail = state._avail_ok.get(res_type, [])

        for m in range(start, end):
            if m >= len(avail) or not avail[m]:
                return False  # outside availability window
            if usage[m] + demand > capacity:
                return False  # capacity exceeded

    return True


# ---------------------------------------------------------------------------
# C5: Dependency precedence
# ---------------------------------------------------------------------------


def c5_dependency_ok(state: PlacementState, task: Task, start: int) -> bool:
    """C5: All prerequisite tasks must be placed and must finish by `start`.

    D6 semantics: prerequisite end <= start (i.e., start of task >= end of prereq).
    """
    for dep_id in task.depends_on:
        if not state.is_placed(dep_id):
            return False
        dep_task_start = state.start_of(dep_id)
        # We don't have the duration here; find it from placed_starts via instance
        # instead we store end-of-prerequisite implicitly via the instance
        # We need the dep task's duration — get it from the state's instance
        try:
            dep_task = state._instance.task(dep_id)
        except KeyError:
            return False
        dep_end = dep_task_start + dep_task.duration
        if dep_end > start:
            return False
    return True


# ---------------------------------------------------------------------------
# Combined feasibility check
# ---------------------------------------------------------------------------


def is_feasible(instance: Instance, state: PlacementState, task: Task, start: int) -> bool:
    """Return True iff all constraints C1-C5 allow placing task at start."""
    return (
        c1_window_ok(task, start)
        and c2_train_ok(instance, task, start)
        and c3_asset_ok(state, task, start)
        and c4_resource_ok(state, instance, task, start)
        and c5_dependency_ok(state, task, start)
    )


def first_violation(
    instance: Instance, state: PlacementState, task: Task, start: int
) -> str | None:
    """Return the code of the first violated constraint ('C1'-'C5'), or None if feasible.

    Check order is C1 → C5 (deterministic).
    """
    if not c1_window_ok(task, start):
        return "C1"
    if not c2_train_ok(instance, task, start):
        return "C2"
    if not c3_asset_ok(state, task, start):
        return "C3"
    if not c4_resource_ok(state, instance, task, start):
        return "C4"
    if not c5_dependency_ok(state, task, start):
        return "C5"
    return None
