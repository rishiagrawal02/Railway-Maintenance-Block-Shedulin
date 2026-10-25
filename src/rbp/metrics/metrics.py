"""Scheduling metrics module.

Computes scheduling evaluation metrics:
  - objective_value: Sum of weights of scheduled tasks
  - scheduled_count: Number of scheduled tasks
  - weighted_coverage: Objective value over total weight of all tasks
  - count_coverage: Number of scheduled tasks over total task count
  - optimality_gap: (optimum - objective) / optimum (None if optimum invalid/missing)
  - utilization: Busy task minutes over planning horizon
  - fragmentation: Maximal contiguous busy blocks per corridor over scheduled tasks
"""

from __future__ import annotations

from rbp.models.instance import Instance
from rbp.models.schedule import Schedule


def objective_value(schedule: Schedule, instance: Instance) -> int:
    """Compute total weight of all scheduled tasks."""
    task_map = {t.id: t for t in instance.tasks}
    return sum(task_map[tid].weight for tid in schedule.starts if tid in task_map)


def scheduled_count(schedule: Schedule) -> int:
    """Compute total number of scheduled tasks."""
    return len(schedule.starts)


def weighted_coverage(schedule: Schedule, instance: Instance) -> float:
    """Compute weighted coverage: objective value over total weight of all tasks in instance.

    Returns 0.0 if total weight is 0.
    """
    total_weight = sum(t.weight for t in instance.tasks)
    if total_weight <= 0:
        return 0.0
    return objective_value(schedule, instance) / total_weight


def count_coverage(schedule: Schedule, instance: Instance) -> float:
    """Compute count coverage: scheduled tasks over total task count in instance.

    Returns 0.0 if total task count is 0.
    """
    total_tasks = len(instance.tasks)
    if total_tasks == 0:
        return 0.0
    return scheduled_count(schedule) / total_tasks


def optimality_gap(objective: float | int, optimum: float | int | None) -> float | None:
    """Compute optimality gap: (optimum - objective) / optimum.

    Returns None when optimum is missing, zero, or negative (not genuine).
    Returns a negative float if objective exceeds optimum.
    """
    if optimum is None or optimum <= 0:
        return None
    return (optimum - objective) / optimum


def utilization(schedule: Schedule, instance: Instance) -> float:
    """Compute corridor utilization proxy: total busy task minutes over horizon.

    Returns 0.0 if horizon is zero or negative.
    """
    if instance.horizon <= 0:
        return 0.0
    task_map = {t.id: t for t in instance.tasks}
    busy_minutes = sum(task_map[tid].duration for tid in schedule.starts if tid in task_map)
    return busy_minutes / instance.horizon


def fragmentation(
    schedule: Schedule,
    instance: Instance,
    per_corridor: bool = False,
) -> int | dict[int, int]:
    """Compute maximal contiguous busy blocks per corridor over scheduled tasks.

    Touching tasks ([a, b) and [b, c)) on the same corridor are merged into a single
    contiguous block. Separated tasks form distinct blocks.

    Parameters:
      schedule: Evaluated schedule.
      instance: Problem instance containing tasks and corridor definitions.
      per_corridor: If True, returns dict mapping corridor_id to block count.
                    If False, returns sum of contiguous blocks across all corridors.
    """
    task_map = {t.id: t for t in instance.tasks}

    # Group intervals by corridor_id
    corridor_intervals: dict[int, list[tuple[int, int]]] = {}
    for tid, start in schedule.starts.items():
        if tid not in task_map:
            continue
        task = task_map[tid]
        end = start + task.duration
        corridor_intervals.setdefault(task.corridor_id, []).append((start, end))

    blocks_per_corridor: dict[int, int] = {}

    # Check all corridors known to instance (or from tasks)
    known_corridors = {c.id for c in instance.corridors} | set(corridor_intervals.keys())
    if not known_corridors:
        known_corridors = {0}

    for cid in known_corridors:
        intervals = corridor_intervals.get(cid, [])
        if not intervals:
            blocks_per_corridor[cid] = 0
            continue

        # Sort intervals by start time
        intervals.sort(key=lambda iv: (iv[0], iv[1]))

        # Count contiguous merged blocks
        block_count = 0
        cur_end = -1
        for start, end in intervals:
            if cur_end == -1 or start > cur_end:
                # Disjoint interval starts a new contiguous block
                block_count += 1
                cur_end = end
            else:
                # Overlapping or touching (start <= cur_end) extends current block
                cur_end = max(cur_end, end)

        blocks_per_corridor[cid] = block_count

    if per_corridor:
        return blocks_per_corridor
    return sum(blocks_per_corridor.values())
