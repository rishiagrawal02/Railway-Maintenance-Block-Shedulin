"""Placement engine for candidate start times and earliest feasible start (Milestone 5.1).

Scans discrete event points (the moment blocking intervals end) to find feasible
starts in O(#events) instead of scanning every integer minute.
"""

from __future__ import annotations

from rbp.constraints.predicates import is_feasible
from rbp.constraints.state import PlacementState
from rbp.models.instance import Instance
from rbp.models.task import Task


def event_starts(instance: Instance, state: PlacementState, task: Task) -> list[int]:
    """Compute sorted, unique candidate start times for task based on event endpoints.

    Event points include:
      - task.window_start
      - End of each train interval on the task's corridor
      - End of each placed task on the same asset
      - End of each placed task sharing a demanded resource type
      - End of each placed prerequisite task
      - Start of each resource availability interval for demanded types

    All candidates are clipped to [task.window_start, task.window_end - task.duration].
    """
    latest_start = task.window_end - task.duration
    if task.window_start > latest_start:
        return []

    candidates: set[int] = {task.window_start}

    # 1. End of train intervals on the corridor
    timetable = instance.timetable_for(task.corridor_id)
    if timetable:
        for ti in timetable.intervals:
            candidates.add(ti.end)

    # 2. End of placed tasks on the same asset
    for placed_start, placed_end in state.asset_intervals(task.asset_id):
        candidates.add(placed_end)

    # 3. End of placed tasks sharing a demanded resource type
    demanded_resources = set(task.demands.keys())
    for placed_tid, placed_start in state.placed_starts.items():
        try:
            placed_task = instance.task(placed_tid)
        except KeyError:
            continue
        if any(r in demanded_resources for r in placed_task.demands):
            candidates.add(placed_start + placed_task.duration)

    # 4. End of placed prerequisites
    for dep_id in task.depends_on:
        if state.is_placed(dep_id):
            dep_task = instance.task(dep_id)
            candidates.add(state.start_of(dep_id) + dep_task.duration)

    # 5. Start of resource availability intervals for demanded types
    for res_type in demanded_resources:
        try:
            res = instance.resource(res_type)
            for iv in res.availability:
                candidates.add(iv.start)
        except KeyError:
            pass

    # Filter to valid window bounds [task.window_start, latest_start]
    valid_candidates = [
        t for t in candidates
        if task.window_start <= t <= latest_start
    ]
    valid_candidates.sort()
    return valid_candidates


def earliest_feasible_start(
    instance: Instance, state: PlacementState, task: Task
) -> int | None:
    """Find the earliest feasible start time for task using discrete event points.

    Returns the first start in event_starts(instance, state, task) that satisfies
    all constraints (C1-C5), or None if no placement is feasible.
    """
    for start in event_starts(instance, state, task):
        if is_feasible(instance, state, task, start):
            return start
    return None
