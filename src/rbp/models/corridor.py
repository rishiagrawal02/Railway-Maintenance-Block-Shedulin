"""Corridor domain entity."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Corridor:
    """Immutable railway corridor containing a sequence of assets."""

    id: int
    traffic_level: str
    asset_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if isinstance(self.asset_ids, list):
            object.__setattr__(self, "asset_ids", tuple(self.asset_ids))
