"""Resource domain entity."""

from dataclasses import dataclass

from .interval import Interval


@dataclass(frozen=True, slots=True)
class Resource:
    """Immutable resource profile with total capacity and availability intervals."""

    type: str
    capacity: int
    availability: tuple[Interval, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.availability, list):
            object.__setattr__(self, "availability", tuple(self.availability))
