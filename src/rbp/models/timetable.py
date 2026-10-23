"""Train timetable and blocking intervals."""

from dataclasses import dataclass

from .interval import Interval


@dataclass(frozen=True, slots=True)
class TrainInterval:
    """A train occupancy interval [start, end) on a corridor."""

    start: int
    end: int

    @property
    def interval(self) -> Interval:
        return Interval(self.start, self.end)


@dataclass(frozen=True, slots=True)
class Timetable:
    """Train schedule on a specific corridor."""

    corridor_id: int
    intervals: tuple[TrainInterval, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.intervals, list):
            object.__setattr__(self, "intervals", tuple(self.intervals))
