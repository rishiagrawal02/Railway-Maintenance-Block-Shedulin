"""Task domain entity representing a maintenance block request."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .interval import Interval


@dataclass(frozen=True, slots=True)
class Task:
    """Immutable representation of a maintenance task request.

    Weight formula (D4): weight = 10 * criticality + urgency.
    """

    id: int
    corridor_id: int
    asset_id: int
    window_start: int
    window_end: int
    duration: int
    criticality: int
    urgency: int
    demands: Mapping[str, int] = field(default_factory=dict)
    depends_on: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.demands, dict):
            object.__setattr__(self, "demands", MappingProxyType(dict(self.demands)))
        if isinstance(self.depends_on, list):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))

    @property
    def weight(self) -> int:
        """Deterministic integer priority weight: 10 * criticality + urgency."""
        return 10 * self.criticality + self.urgency

    @property
    def window(self) -> Interval:
        """Allowed scheduling window [window_start, window_end)."""
        return Interval(self.window_start, self.window_end)
