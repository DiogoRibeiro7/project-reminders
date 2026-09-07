"""Dashboard read models and attention ranking."""

from dataclasses import dataclass
from datetime import datetime

from project_reminders.domain.enums import CIState, Priority, ProjectStatus
from project_reminders.domain.models import Portfolio, Project
from project_reminders.domain.rules import ACTIVE_STATUSES, requires_next_action

_PRIORITY_WEIGHT: dict[Priority, int] = {
    Priority.LOW: 0,
    Priority.MEDIUM: 10,
    Priority.HIGH: 20,
    Priority.CRITICAL: 30,
}


@dataclass(frozen=True, slots=True)
class ProjectCard:
    """One dashboard row with derived attention information."""

    project: Project
    attention_score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Dashboard:
    """Portfolio-level dashboard read model."""

    cards: tuple[ProjectCard, ...]
    total_count: int
    active_count: int
    attention_count: int
    failing_ci_count: int
    pending_ci_count: int
    open_pr_count: int
    blocked_count: int
    missing_next_action_count: int
    status_counts: dict[ProjectStatus, int]
    generated_at: datetime | None

    @property
    def attention_queue(self) -> tuple[ProjectCard, ...]:
        """Return the highest-priority projects that currently need attention."""

        return tuple(card for card in self.cards if card.reasons)[:8]


def _attention(project: Project) -> tuple[int, tuple[str, ...]]:
    score = _PRIORITY_WEIGHT[project.priority]
    reasons: list[str] = []
    if project.blocker:
        score += 50
        reasons.append(f"Blocked: {project.blocker}")
    if project.operational.ci_state is CIState.FAILING:
        score += 45
        reasons.append("Latest CI is failing")
    if requires_next_action(project) and project.next_action is None:
        score += 40
        reasons.append("Active project has no next action")
    missing = project.health.missing_dimensions
    if missing:
        score += min(30, 5 * len(missing))
        labels = ", ".join(dimension.value for dimension in missing)
        reasons.append(f"Known missing engineering health: {labels}")
    return score, tuple(reasons)


def build_project_card(project: Project) -> ProjectCard:
    """Build the shared attention read model for one project."""

    score, reasons = _attention(project)
    return ProjectCard(project=project, attention_score=score, reasons=reasons)


def build_dashboard(portfolio: Portfolio) -> Dashboard:
    """Build a deterministic portfolio dashboard."""

    cards: list[ProjectCard] = []
    counts = {status: 0 for status in ProjectStatus}
    for project in portfolio.projects:
        counts[project.status] += 1
        cards.append(build_project_card(project))
    cards.sort(key=lambda card: (-card.attention_score, card.project.name.casefold()))

    projects = portfolio.projects
    return Dashboard(
        cards=tuple(cards),
        total_count=len(projects),
        active_count=sum(counts[status] for status in ACTIVE_STATUSES),
        attention_count=sum(bool(card.reasons) for card in cards),
        failing_ci_count=sum(
            project.operational.ci_state is CIState.FAILING for project in projects
        ),
        pending_ci_count=sum(
            project.operational.ci_state is CIState.PENDING for project in projects
        ),
        open_pr_count=sum(len(project.operational.open_pull_requests) for project in projects),
        blocked_count=sum(project.blocker is not None for project in projects),
        missing_next_action_count=sum(
            requires_next_action(project) and project.next_action is None for project in projects
        ),
        status_counts=counts,
        generated_at=portfolio.generated_at,
    )
