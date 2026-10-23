"""Instance domain entity representing the complete problem input."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .corridor import Corridor
from .resource import Resource
from .task import Task
from .timetable import Timetable


@dataclass(frozen=True, slots=True)
class Instance:
    """Complete scheduling problem instance."""

    tasks: tuple[Task, ...]
    corridors: tuple[Corridor, ...] = ()
    resources: tuple[Resource, ...] = ()
    timetable: tuple[Timetable, ...] = ()
    horizon: int = 1440
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.tasks, list):
            object.__setattr__(self, "tasks", tuple(self.tasks))
        if isinstance(self.corridors, list):
            object.__setattr__(self, "corridors", tuple(self.corridors))
        if isinstance(self.resources, list):
            object.__setattr__(self, "resources", tuple(self.resources))
        if isinstance(self.timetable, list):
            object.__setattr__(self, "timetable", tuple(self.timetable))
        if isinstance(self.meta, dict):
            object.__setattr__(self, "meta", MappingProxyType(dict(self.meta)))

    def task(self, task_id: int) -> Task:
        """Look up task by integer id. Raises KeyError if not found."""
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(f"Task with id {task_id} not found in instance")

    def corridor(self, corridor_id: int) -> Corridor:
        """Look up corridor by id."""
        for c in self.corridors:
            if c.id == corridor_id:
                return c
        raise KeyError(f"Corridor with id {corridor_id} not found in instance")

    def resource(self, res_type: str) -> Resource:
        """Look up resource by type name."""
        for r in self.resources:
            if r.type == res_type:
                return r
        raise KeyError(f"Resource type '{res_type}' not found in instance")

    def timetable_for(self, corridor_id: int) -> Timetable | None:
        """Look up timetable for a specific corridor."""
        for tt in self.timetable:
            if tt.corridor_id == corridor_id:
                return tt
        return None
