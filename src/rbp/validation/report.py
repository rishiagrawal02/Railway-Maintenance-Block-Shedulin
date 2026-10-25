"""Validation report dataclass for schedule validation results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Violation:
    """A single constraint violation in a schedule."""

    code: str
    task_ids: tuple[int, ...]
    detail: str

    def __str__(self) -> str:
        ids = ", ".join(str(i) for i in self.task_ids)
        return f"[{self.code}] tasks={ids}: {self.detail}"


@dataclass
class ValidationReport:
    """Result of validating a schedule against an instance."""

    valid: bool
    violations: list[Violation] = field(default_factory=list)

    @property
    def counts_by_code(self) -> dict[str, int]:
        """Number of violations per constraint code."""
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.code] = counts.get(v.code, 0) + 1
        return counts

    @property
    def total_violations(self) -> int:
        return len(self.violations)
