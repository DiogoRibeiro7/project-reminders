"""Dashboard read models and attention ranking."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from project_reminders.domain.enums import CIState, Priority, ProjectStatus
from project_reminders.domain.models import Portfolio, Project
from project_reminders.domain.rules import ACTIVE_STATUSES, requires_next_action

_PRIORITY_WEIGHT: dict[Priority, int] = {
    Priority.LOW: 0,
    Priority.MEDIUM: 10,
    Priority.HIGH: 20,
    Priority.CRITICAL: 30,
}
_OPERATIONAL_STALE_AFTER = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class ProjectCard:
    """One dashboard row with derived attention information."""

    project: Project
    attention_score: int
    reasons: tuple[str, ...]
    operational_stale: bool = False
    operational_unobserved: bool = False


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
    stale_operational_count: int
    unobserved_operational_count: int
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


def _freshness(project: Project, now: datetime) -> tuple[bool, bool]:
    observed_at = project.operational.observed_at
    if observed_at is None:
        return False, True
    return now - observed_at > _OPERATIONAL_STALE_AFTER, False


def build_project_card(project: Project, now: datetime | None = None) -> ProjectCard:
    """Build the shared attention and freshness read model for one project."""

    current_time = now or datetime.now(UTC)
    score, reasons = _attention(project)
    stale, unobserved = _freshness(project, current_time)
    return ProjectCard(
        project=project,
        attention_score=score,
        reasons=reasons,
        operational_stale=stale,
        operational_unobserved=unobserved,
    )


def build_dashboard(portfolio: Portfolio, now: datetime | None = None) -> Dashboard:
    """Build a deterministic portfolio dashboard."""

    current_time = now or datetime.now(UTC)
    cards: list[ProjectCard] = []
    counts = {status: 0 for status in ProjectStatus}
    for project in portfolio.projects:
        counts[project.status] += 1
        cards.append(build_project_card(project, current_time))
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
        stale_operational_count=sum(card.operational_stale for card in cards),
        unobserved_operational_count=sum(card.operational_unobserved for card in cards),
        status_counts=counts,
        generated_at=portfolio.generated_at,
    )
