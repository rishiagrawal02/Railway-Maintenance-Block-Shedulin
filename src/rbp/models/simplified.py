"""Definition and predicate for the simplified scheduling instance (Decision D8).

D8: 'Simplified case' definition:
One corridor, one resource type with capacity 1, every task demands 1,
window length == duration (fixed interval), no trains blocking, no dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instance import Instance


def is_simplified(instance: Instance) -> bool:
    """Return True if instance satisfies the simplified case conditions (D8).

    Requirements:
      1. Exactly 1 corridor.
      2. Exactly 1 resource type, with capacity 1 and full-horizon availability.
      3. For every task:
         - window_end - window_start == duration (fixed interval)
         - demands has exactly 1 entry for that resource type with demand 1
         - depends_on is empty
         - corridor_id matches the single corridor
      4. No trains blocking: timetable has 0 train intervals across all corridors.
    """
    if len(instance.corridors) != 1:
        return False

    if len(instance.resources) != 1:
        return False

    res = instance.resources[0]
    if res.capacity != 1:
        return False

    # Check timetable has no blocking trains
    for tt in instance.timetable:
        if len(tt.intervals) > 0:
            return False

    corridor_id = instance.corridors[0].id
    res_type = res.type

    for t in instance.tasks:
        # Fixed interval: window length == duration
        if (t.window_end - t.window_start) != t.duration:
            return False
        # Single corridor
        if t.corridor_id != corridor_id:
            return False
        # Demands exactly 1 unit of the single resource
        if dict(t.demands) != {res_type: 1}:
            return False
        # No dependencies
        if len(t.depends_on) > 0:
            return False

    return True
