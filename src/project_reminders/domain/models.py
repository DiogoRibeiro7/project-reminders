"""Core immutable value objects for project-reminders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from project_reminders.domain.enums import (
    CIState,
    HealthDimension,
    HealthState,
    Priority,
    ProjectStatus,
)
from project_reminders.domain.metadata import ProjectMetadataSnapshot


def _require_timezone(value: datetime | None, field_name: str) -> None:
    """Reject naive datetimes so persisted timestamps remain unambiguous."""

    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class NextAction:
    """Exactly one concrete action that can advance a project."""

    description: str
    due_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("next action description must not be empty")
        _require_timezone(self.due_at, "due_at")


@dataclass(frozen=True, slots=True)
class EngineeringHealth:
    """Known engineering-health observations for a project."""

    states: Mapping[HealthDimension, HealthState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = {
            HealthDimension(key): HealthState(value) for key, value in self.states.items()
        }
        object.__setattr__(self, "states", MappingProxyType(normalized))

    def state_for(self, dimension: HealthDimension) -> HealthState:
        """Return the observed state or UNKNOWN when no assessment exists."""

        return self.states.get(dimension, HealthState.UNKNOWN)

    def with_state(self, dimension: HealthDimension, state: HealthState) -> EngineeringHealth:
        """Return a new health value with one dimension changed."""

        updated = dict(self.states)
        updated[dimension] = state
        return EngineeringHealth(updated)

    @property
    def missing_dimensions(self) -> tuple[HealthDimension, ...]:
        """Dimensions explicitly assessed as missing."""

        return tuple(
            dimension
            for dimension in HealthDimension
            if self.state_for(dimension) is HealthState.MISSING
        )


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    """Minimal observed state for one open pull request."""

    number: int
    title: str
    draft: bool
    updated_at: datetime | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if self.number <= 0:
            raise ValueError("pull request number must be positive")
        _require_timezone(self.updated_at, "pull_request.updated_at")


@dataclass(frozen=True, slots=True)
class OperationalSnapshot:
    """Observed GitHub state, separate from declared project state."""

    open_pull_requests: tuple[PullRequestSnapshot, ...] = ()
    ci_state: CIState = CIState.UNKNOWN
    ci_url: str | None = None
    ci_updated_at: datetime | None = None
    latest_activity_at: datetime | None = None
    latest_release: str | None = None
    latest_release_at: datetime | None = None
    latest_release_url: str | None = None
    latest_tag: str | None = None
    latest_tag_url: str | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("ci_updated_at", self.ci_updated_at),
            ("latest_activity_at", self.latest_activity_at),
            ("latest_release_at", self.latest_release_at),
            ("observed_at", self.observed_at),
        ):
            _require_timezone(value, field_name)


@dataclass(frozen=True, slots=True)
class Project:
    """One code project tracked by the portfolio."""

    id: str
    name: str
    repository: str
    status: ProjectStatus = ProjectStatus.IDEA
    priority: Priority = Priority.MEDIUM
    summary: str = ""
    next_action: NextAction | None = None
    blocker: str | None = None
    tags: tuple[str, ...] = ()
    health: EngineeringHealth = field(default_factory=EngineeringHealth)
    operational: OperationalSnapshot = field(default_factory=OperationalSnapshot)
    metadata: ProjectMetadataSnapshot | None = None
    current_pr: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_repository_activity_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("project id must not be empty")
        if not self.name.strip():
            raise ValueError("project name must not be empty")
        owner, separator, repo = self.repository.partition("/")
        if not separator or not owner or not repo or "/" in repo:
            raise ValueError("repository must use owner/name form")
        if self.current_pr is not None and self.current_pr <= 0:
            raise ValueError("current_pr must be positive")
        for field_name, value in (
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
            ("last_repository_activity_at", self.last_repository_activity_at),
        ):
            _require_timezone(value, field_name)


@dataclass(frozen=True, slots=True)
class Portfolio:
    """The complete persisted portfolio."""

    projects: tuple[Project, ...] = ()
    version: int = 1
    generated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError(f"unsupported portfolio version: {self.version}")
        _require_timezone(self.generated_at, "generated_at")
        ids = [project.id for project in self.projects]
        if len(ids) != len(set(ids)):
            raise ValueError("project ids must be unique")
