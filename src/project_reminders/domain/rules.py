"""Pure portfolio rules."""

from project_reminders.domain.enums import ProjectStatus
from project_reminders.domain.models import Project

ACTIVE_STATUSES: frozenset[ProjectStatus] = frozenset(
    {
        ProjectStatus.PROTOTYPE,
        ProjectStatus.ACTIVE_DEVELOPMENT,
        ProjectStatus.HARDENING,
        ProjectStatus.PORTFOLIO_READY,
        ProjectStatus.MAINTENANCE,
    }
)


def requires_next_action(project: Project) -> bool:
    """Whether this lifecycle state should expose one concrete next action."""

    return project.status in ACTIVE_STATUSES and project.blocker is None
