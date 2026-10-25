"""Mutable placement state tracking which tasks have been scheduled.

PlacementState is used *only* by algorithms (never by the validator).
It tracks:
  - placed starts: dict[task_id, start_minute]
  - per-asset sorted list of placed (start, end) intervals (for C3 bisect)
  - per-resource-type usage array of length `horizon` (for C4 O(duration) check)
"""

from __future__ import annotations

import bisect

from rbp.models.instance import Instance
from rbp.models.task import Task


class PlacementState:
    """Mutable state tracking which tasks have been placed and their resource usage."""

    def __init__(self, instance: Instance) -> None:
        self._instance = instance
        self._horizon = instance.horizon

        # placed_starts[task_id] = start_minute
        self._placed_starts: dict[int, int] = {}

        # per-asset: sorted list of (start, end) tuples for placed tasks
        self._asset_intervals: dict[int, list[tuple[int, int]]] = {}

        # per-resource-type: usage array of ints, length = horizon
        self._resource_usage: dict[str, list[int]] = {
            r.type: [0] * self._horizon for r in instance.resources
        }

        # Precompute merged availability arrays per resource type:
        # _avail_ok[type][minute] = True if minute is inside at least one availability interval
        self._avail_ok: dict[str, list[bool]] = {}
        for r in instance.resources:
            avail = [False] * self._horizon
            for iv in r.availability:
                for m in range(max(0, iv.start), min(self._horizon, iv.end)):
                    avail[m] = True
            self._avail_ok[r.type] = avail

    # ------------------------------------------------------------------
    # Public read accessors
    # ------------------------------------------------------------------

    @property
    def placed_starts(self) -> dict[int, int]:
        """Read-only view of placed task starts."""
        return self._placed_starts

    def is_placed(self, task_id: int) -> bool:
        return task_id in self._placed_starts

    def start_of(self, task_id: int) -> int:
        return self._placed_starts[task_id]

    def end_of(self, task: Task) -> int:
        return self._placed_starts[task.id] + task.duration

    def asset_intervals(self, asset_id: int) -> list[tuple[int, int]]:
        """Sorted list of (start, end) intervals placed on this asset."""
        return self._asset_intervals.get(asset_id, [])

    def resource_usage_at(self, res_type: str, minute: int) -> int:
        return self._resource_usage[res_type][minute]

    def avail_ok(self, res_type: str, minute: int) -> bool:
        return self._avail_ok.get(res_type, [])[minute]

    # ------------------------------------------------------------------
    # Mutation: place / unplace
    # ------------------------------------------------------------------

    def place(self, task: Task, start: int) -> None:
        """Record a placement. Does NOT check feasibility; call is_feasible first."""
        end = start + task.duration
        self._placed_starts[task.id] = start

        # Update per-asset sorted interval list
        alist = self._asset_intervals.setdefault(task.asset_id, [])
        bisect.insort(alist, (start, end))

        # Update resource usage array
        for res_type, demand in task.demands.items():
            usage = self._resource_usage[res_type]
            for m in range(start, end):
                usage[m] += demand

    def unplace(self, task: Task) -> None:
        """Remove a previously placed task, restoring all state."""
        start = self._placed_starts.pop(task.id)
        end = start + task.duration

        # Remove from per-asset sorted interval list
        alist = self._asset_intervals.get(task.asset_id, [])
        idx = bisect.bisect_left(alist, (start, end))
        if idx < len(alist) and alist[idx] == (start, end):
            alist.pop(idx)

        # Restore resource usage
        for res_type, demand in task.demands.items():
            usage = self._resource_usage[res_type]
            for m in range(start, end):
                usage[m] -= demand
