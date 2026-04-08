"""Data models for seeder steps and results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepDefinition:
    """Defines a seeder step with its name, dependencies, and callable."""

    name: str
    deps: list[str] = field(default_factory=list)
    seed_fn: str = ""  # module path to the async seed function


@dataclass
class StepResult:
    """Result of a single seeder step."""

    name: str
    created: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None


@dataclass
class SeederResult:
    """Result of a full seeder run."""

    exit_code: int = 0
    steps: list[StepResult] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    error: str | None = None
