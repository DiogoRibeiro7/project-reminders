"""Portfolio change detection between persisted snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from project_reminders.domain.enums import CIState, HealthDimension, HealthState
from project_reminders.domain.models import Portfolio, Project


class ChangeDirection(StrEnum):
    """Conservative direction assigned only where improvement is defensible."""

    IMPROVED = "improved"
    DEGRADED = "degraded"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class ProjectChange:
    """One human-readable change for a tracked project."""

    project_id: str
    project_name: str
    direction: ChangeDirection
    message: str


@dataclass(frozen=True, slots=True)
class PortfolioHistory:
    """Changes from one previous portfolio snapshot to the current state."""

    previous_generated_at: datetime | None
    changes: tuple[ProjectChange, ...]

    @property
    def improved_count(self) -> int:
        return sum(change.direction is ChangeDirection.IMPROVED for change in self.changes)

    @property
    def degraded_count(self) -> int:
        return sum(change.direction is ChangeDirection.DEGRADED for change in self.changes)

    def for_project(self, project_id: str) -> tuple[ProjectChange, ...]:
        return tuple(change for change in self.changes if change.project_id == project_id)


_HEALTH_RANK = {
    HealthState.MISSING: 0,
    HealthState.PARTIAL: 1,
    HealthState.COMPLETE: 2,
}


def _health_direction(before: HealthState, after: HealthState) -> ChangeDirection:
    if before in _HEALTH_RANK and after in _HEALTH_RANK:
        if _HEALTH_RANK[after] > _HEALTH_RANK[before]:
            return ChangeDirection.IMPROVED
        if _HEALTH_RANK[after] < _HEALTH_RANK[before]:
            return ChangeDirection.DEGRADED
    return ChangeDirection.CHANGED


def _ci_direction(before: CIState, after: CIState) -> ChangeDirection:
    if before is CIState.FAILING and after is CIState.PASSING:
        return ChangeDirection.IMPROVED
    if before is CIState.PASSING and after is CIState.FAILING:
        return ChangeDirection.DEGRADED
    return ChangeDirection.CHANGED


def _change(project: Project, direction: ChangeDirection, message: str) -> ProjectChange:
    return ProjectChange(project.id, project.name, direction, message)


def _compare_project(before: Project, after: Project) -> list[ProjectChange]:
    changes: list[ProjectChange] = []
    if before.status != after.status:
        changes.append(
            _change(after, ChangeDirection.CHANGED, f"Lifecycle: {before.status.value} → {after.status.value}")
        )
    if before.priority != after.priority:
        changes.append(
            _change(after, ChangeDirection.CHANGED, f"Priority: {before.priority.value} → {after.priority.value}")
        )
    before_action = before.next_action.description if before.next_action else None
    after_action = after.next_action.description if after.next_action else None
    if before_action != after_action:
        changes.append(
            _change(after, ChangeDirection.CHANGED, f"Next action: {before_action or '—'} → {after_action or '—'}")
        )
    if before.blocker != after.blocker:
        changes.append(
            _change(after, ChangeDirection.CHANGED, f"Blocker: {before.blocker or '—'} → {after.blocker or '—'}")
        )
    if before.operational.ci_state != after.operational.ci_state:
        changes.append(
            _change(
                after,
                _ci_direction(before.operational.ci_state, after.operational.ci_state),
                f"CI: {before.operational.ci_state.value} → {after.operational.ci_state.value}",
            )
        )
    before_prs = len(before.operational.open_pull_requests)
    after_prs = len(after.operational.open_pull_requests)
    if before_prs != after_prs:
        changes.append(_change(after, ChangeDirection.CHANGED, f"Open PRs: {before_prs} → {after_prs}"))
    before_release = before.operational.latest_release or before.operational.latest_tag
    after_release = after.operational.latest_release or after.operational.latest_tag
    if before_release != after_release:
        changes.append(
            _change(after, ChangeDirection.CHANGED, f"Release/tag: {before_release or '—'} → {after_release or '—'}")
        )
    for dimension in HealthDimension:
        old_state = before.health.state_for(dimension)
        new_state = after.health.state_for(dimension)
        if old_state == new_state:
            continue
        changes.append(
            _change(
                after,
                _health_direction(old_state, new_state),
                f"{dimension.value}: {old_state.value} → {new_state.value}",
            )
        )
    return changes


def compare_portfolios(previous: Portfolio | None, current: Portfolio) -> PortfolioHistory:
    """Compare current state with one previous snapshot."""

    if previous is None:
        return PortfolioHistory(previous_generated_at=None, changes=())
    before = {project.id: project for project in previous.projects}
    after = {project.id: project for project in current.projects}
    changes: list[ProjectChange] = []
    for project_id in sorted(after):
        current_project = after[project_id]
        old_project = before.get(project_id)
        if old_project is None:
            changes.append(_change(current_project, ChangeDirection.CHANGED, "Project added to portfolio"))
        else:
            changes.extend(_compare_project(old_project, current_project))
    for project_id in sorted(set(before) - set(after)):
        old_project = before[project_id]
        changes.append(
            ProjectChange(project_id, old_project.name, ChangeDirection.CHANGED, "Project removed from portfolio")
        )
    return PortfolioHistory(previous_generated_at=previous.generated_at, changes=tuple(changes))
