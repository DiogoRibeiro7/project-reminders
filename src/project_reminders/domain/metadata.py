"""Repository-local planning metadata for managed projects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProjectType(StrEnum):
    """Primary role a repository plays in the portfolio."""

    RESEARCH = "research"
    PACKAGE = "package"
    DATA = "data"
    TEACHING = "teaching"
    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    OTHER = "other"


class PlanningHorizon(StrEnum):
    """Nearest planning horizon in which the project may receive attention."""

    NOW = "now"
    WEEK = "week"
    MONTH = "month"
    LATER = "later"


class MilestoneStatus(StrEnum):
    """Execution state of the repository's current milestone."""

    READY = "ready"
    WIP = "wip"
    FINISHING = "finishing"
    BLOCKED = "blocked"
    DONE = "done"
    STOPPED = "stopped"


class DependencyKind(StrEnum):
    """Strength and ownership of a milestone dependency."""

    HARD = "hard"
    SOFT = "soft"
    EXTERNAL = "external"


class OutcomeType(StrEnum):
    """Material portfolio outcomes produced by a project."""

    PAPER = "paper"
    SOFTWARE_RELEASE = "software_release"
    DATASET = "dataset"
    DELIVERABLE = "deliverable"
    REUSABLE_ASSET = "reusable_asset"
    PROFESSIONAL_ARTIFACT = "professional_artifact"
    RESEARCH_RESULT = "research_result"


class OutcomeStatus(StrEnum):
    """Lifecycle state of a target portfolio outcome."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STOPPED = "stopped"


def _require_text(value: str, field_name: str) -> None:
    """Reject empty human-entered identifiers and descriptions."""

    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    """One verifiable condition required to complete a milestone."""

    id: str
    text: str
    done: bool = False

    def __post_init__(self) -> None:
        _require_text(self.id, "acceptance criterion id")
        _require_text(self.text, "acceptance criterion text")


@dataclass(frozen=True, slots=True)
class Milestone:
    """The single current milestone declared by a repository."""

    id: str
    title: str
    status: MilestoneStatus
    acceptance: tuple[AcceptanceCriterion, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "milestone id")
        _require_text(self.title, "milestone title")
        criterion_ids = [criterion.id for criterion in self.acceptance]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("acceptance criterion ids must be unique within a milestone")
        if self.status is MilestoneStatus.FINISHING and any(
            not criterion.done for criterion in self.acceptance
        ):
            raise ValueError("finishing milestones require all acceptance criteria to be complete")


@dataclass(frozen=True, slots=True)
class Dependency:
    """One declared dependency relevant to the current milestone."""

    kind: DependencyKind
    target: str

    def __post_init__(self) -> None:
        _require_text(self.target, "dependency target")


@dataclass(frozen=True, slots=True)
class Outcome:
    """One material result the project is expected to produce."""

    id: str
    type: OutcomeType
    status: OutcomeStatus
    target: str

    def __post_init__(self) -> None:
        _require_text(self.id, "outcome id")
        _require_text(self.target, "outcome target")


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Validated repository-local planning metadata.

    Existing lifecycle, priority, next-action, health, and observed GitHub state remain in the
    central portfolio model. This value adds the planning concepts that are not already represented
    there, avoiding two competing sources of truth during the migration.
    """

    project_type: ProjectType
    strategic_themes: tuple[str, ...] = ()
    planning_horizon: PlanningHorizon = PlanningHorizon.LATER
    wip: bool = False
    milestone: Milestone | None = None
    dependencies: tuple[Dependency, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported project metadata version: {self.schema_version}")
        normalized_themes = tuple(theme.strip() for theme in self.strategic_themes)
        if any(not theme for theme in normalized_themes):
            raise ValueError("strategic themes must not contain empty values")
        if len(normalized_themes) != len(set(normalized_themes)):
            raise ValueError("strategic themes must be unique")
        object.__setattr__(self, "strategic_themes", normalized_themes)

        if self.planning_horizon is PlanningHorizon.NOW and not self.wip:
            raise ValueError("planning horizon 'now' requires wip=true")
        if self.wip and self.milestone is None:
            raise ValueError("wip projects require a current milestone")
        if self.milestone is not None:
            terminal = {MilestoneStatus.DONE, MilestoneStatus.STOPPED}
            if self.milestone.status in terminal:
                raise ValueError("current milestone cannot be done or stopped")
            active = {MilestoneStatus.WIP, MilestoneStatus.FINISHING}
            if self.wip and self.milestone.status not in active:
                raise ValueError("wip projects require milestone status wip or finishing")
            if not self.wip and self.milestone.status in active:
                raise ValueError("milestone status wip or finishing requires wip=true")

        dependency_keys = [(dependency.kind, dependency.target) for dependency in self.dependencies]
        if len(dependency_keys) != len(set(dependency_keys)):
            raise ValueError("dependencies must be unique")

        outcome_ids = [outcome.id for outcome in self.outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("outcome ids must be unique")
