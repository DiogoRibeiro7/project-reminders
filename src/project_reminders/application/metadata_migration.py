"""Prioritize repositories that still need repository-local planning metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from project_reminders.domain.enums import Priority
from project_reminders.domain.models import Portfolio, Project
from project_reminders.domain.rules import ACTIVE_STATUSES
from project_reminders.infrastructure.metadata_inventory import MetadataInventory

_RECENT_ACTIVITY_WINDOW = timedelta(days=30)
_PRIORITY_ORDER: dict[Priority, int] = {
    Priority.CRITICAL: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class MetadataMigrationWave(StrEnum):
    """Manual migration waves ordered by immediate portfolio relevance."""

    ACTIVE = "active"
    RECENT = "recent"
    LATER = "later"


_WAVE_ORDER: dict[MetadataMigrationWave, int] = {
    MetadataMigrationWave.ACTIVE: 0,
    MetadataMigrationWave.RECENT: 1,
    MetadataMigrationWave.LATER: 2,
}


@dataclass(frozen=True, slots=True)
class MetadataMigrationCandidate:
    """One repository whose local planning metadata still needs classification."""

    project: Project
    wave: MetadataMigrationWave
    reason: str


def _latest_activity(project: Project) -> datetime | None:
    """Return the freshest known repository activity timestamp."""

    return project.operational.latest_activity_at or project.last_repository_activity_at


def _wave_for(project: Project, now: datetime) -> tuple[MetadataMigrationWave, str]:
    if project.status in ACTIVE_STATUSES:
        return MetadataMigrationWave.ACTIVE, "active lifecycle project"

    latest_activity = _latest_activity(project)
    if latest_activity is not None and now - latest_activity <= _RECENT_ACTIVITY_WINDOW:
        return MetadataMigrationWave.RECENT, "repository activity within 30 days"

    return MetadataMigrationWave.LATER, "not active and no repository activity within 30 days"


def build_metadata_migration_queue(
    portfolio: Portfolio,
    metadata_inventory: MetadataInventory,
    *,
    now: datetime | None = None,
) -> tuple[MetadataMigrationCandidate, ...]:
    """Return missing-metadata repositories in deterministic migration order.

    This is an informational queue only. It never writes metadata or changes project state.
    """

    current_time = now or datetime.now(UTC)
    candidates: list[MetadataMigrationCandidate] = []
    for project in portfolio.projects:
        if metadata_inventory.migration_status(project.repository) != "missing":
            continue
        wave, reason = _wave_for(project, current_time)
        candidates.append(MetadataMigrationCandidate(project=project, wave=wave, reason=reason))

    def sort_key(candidate: MetadataMigrationCandidate) -> tuple[int, int, float, str]:
        activity = _latest_activity(candidate.project)
        activity_rank = -(activity.timestamp()) if activity is not None else float("inf")
        return (
            _WAVE_ORDER[candidate.wave],
            _PRIORITY_ORDER[candidate.project.priority],
            activity_rank,
            candidate.project.name.casefold(),
        )

    return tuple(sorted(candidates, key=sort_key))
