"""Dashboard read models and attention ranking."""

from dataclasses import dataclass

from project_reminders.domain.enums import Priority, ProjectStatus
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
    active_count: int
    attention_count: int
    status_counts: dict[ProjectStatus, int]


def _attention(project: Project) -> tuple[int, tuple[str, ...]]:
    score = _PRIORITY_WEIGHT[project.priority]
    reasons: list[str] = []

    if project.blocker:
        score += 50
        reasons.append(f"Blocked: {project.blocker}")
    if requires_next_action(project) and project.next_action is None:
        score += 40
        reasons.append("Active project has no next action")
    missing = project.health.missing_dimensions
    if missing:
        score += min(30, 5 * len(missing))
        labels = ", ".join(dimension.value for dimension in missing)
        reasons.append(f"Known missing engineering health: {labels}")

    return score, tuple(reasons)


def build_dashboard(portfolio: Portfolio) -> Dashboard:
    """Build a deterministic portfolio dashboard."""

    cards = []
    counts = {status: 0 for status in ProjectStatus}
    for project in portfolio.projects:
        counts[project.status] += 1
        score, reasons = _attention(project)
        cards.append(ProjectCard(project=project, attention_score=score, reasons=reasons))

    cards.sort(key=lambda card: (-card.attention_score, card.project.name.casefold()))
    return Dashboard(
        cards=tuple(cards),
        active_count=sum(counts[status] for status in ACTIVE_STATUSES),
        attention_count=sum(bool(card.reasons) for card in cards),
        status_counts=counts,
    )
