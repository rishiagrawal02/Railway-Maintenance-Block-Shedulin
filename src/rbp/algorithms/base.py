"""Common base classes, results, and exceptions for scheduling algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rbp.models.schedule import Schedule


class NotSimplifiedError(ValueError):
    """Raised when an algorithm requiring a simplified instance receives an extended one."""

    pass


@dataclass(frozen=True)
class AlgoResult:
    """Standard result structure returned by all scheduling algorithms.

    Attributes:
      name: Identifier of the algorithm (e.g. 'wis_dp', 'brute_force', 'naive_greedy').
      schedule: The produced Schedule instance.
      objective: Total weight of scheduled tasks (exact integer).
      meta: Additional execution statistics and metadata (runtime, iterations, etc.).
    """

    name: str
    schedule: Schedule
    objective: int
    meta: dict[str, Any] = field(default_factory=dict)
