"""Interval representation with half-open [start, end) semantics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Interval:
    """Half-open integer interval [start, end).

    Touching intervals (e.g., [0, 5) and [5, 10)) do not overlap.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if not isinstance(self.start, int) or not isinstance(self.end, int):
            raise TypeError("Interval start and end must be integers")
        if self.start > self.end:
            raise ValueError(f"Interval start ({self.start}) cannot exceed end ({self.end})")

    @property
    def length(self) -> int:
        """Duration/length of the interval."""
        return self.end - self.start

    def overlaps(self, other: "Interval") -> bool:
        """Check if this interval overlaps with another half-open interval."""
        return max(self.start, other.start) < min(self.end, other.end)

    def contains(self, point: int) -> bool:
        """Check if integer point is inside half-open interval [start, end)."""
        return self.start <= point < self.end

    def contains_interval(self, other: "Interval") -> bool:
        """Check if this interval completely encloses other."""
        return self.start <= other.start and other.end <= self.end
