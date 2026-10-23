"""Schedule domain entity representing the output assignment."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .task import Task


@dataclass(frozen=True, slots=True)
class Schedule:
    """Output schedule assigning start times to a subset of tasks."""

    starts: Mapping[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.starts, dict):
            object.__setattr__(self, "starts", MappingProxyType(dict(self.starts)))

    def is_scheduled(self, task_id: int) -> bool:
        """Check if task is scheduled."""
        return task_id in self.starts

    def start_of(self, task_id: int) -> int:
        """Return start time for scheduled task id. Raises KeyError if not scheduled."""
        return self.starts[task_id]

    def end_of(self, task: Task | int, duration: int | None = None) -> int:
        """Calculate the completion time (start + duration) of a task.

        Can pass Task object directly, or task_id with duration.
        """
        if isinstance(task, Task):
            task_id = task.id
            task_dur = task.duration
        else:
            task_id = task
            if duration is None:
                raise ValueError("duration must be provided when task is an integer id")
            task_dur = duration

        return self.starts[task_id] + task_dur
