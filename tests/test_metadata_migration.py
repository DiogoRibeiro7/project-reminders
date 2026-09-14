"""Repository-local metadata migration queue tests."""

from datetime import UTC, datetime, timedelta

from project_reminders.application.metadata_migration import (
    MetadataMigrationWave,
    build_metadata_migration_queue,
)
from project_reminders.domain.enums import Priority, ProjectStatus
from project_reminders.domain.models import OperationalSnapshot, Portfolio, Project
from project_reminders.infrastructure.metadata_inventory import MetadataInventory


def test_queue_prioritizes_active_then_recent_then_later() -> None:
    now = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
    active = Project(
        id="active",
        name="Active",
        repository="owner/active",
        status=ProjectStatus.ACTIVE_DEVELOPMENT,
        priority=Priority.MEDIUM,
    )
    recent = Project(
        id="recent",
        name="Recent",
        repository="owner/recent",
        status=ProjectStatus.IDEA,
        priority=Priority.HIGH,
        operational=OperationalSnapshot(latest_activity_at=now - timedelta(days=5)),
    )
    later = Project(
        id="later",
        name="Later",
        repository="owner/later",
        status=ProjectStatus.PAUSED,
        priority=Priority.CRITICAL,
        operational=OperationalSnapshot(latest_activity_at=now - timedelta(days=60)),
    )
    inventory = MetadataInventory(
        migrated={},
        missing=frozenset({"owner/active", "owner/recent", "owner/later"}),
    )

    queue = build_metadata_migration_queue(
        Portfolio(projects=(later, recent, active)),
        inventory,
        now=now,
    )

    assert [candidate.project.id for candidate in queue] == ["active", "recent", "later"]
    assert [candidate.wave for candidate in queue] == [
        MetadataMigrationWave.ACTIVE,
        MetadataMigrationWave.RECENT,
        MetadataMigrationWave.LATER,
    ]


def test_queue_excludes_migrated_and_unknown_repositories() -> None:
    missing = Project(id="missing", name="Missing", repository="owner/missing")
    migrated = Project(id="migrated", name="Migrated", repository="owner/migrated")
    unknown = Project(id="unknown", name="Unknown", repository="owner/unknown")
    inventory = MetadataInventory(
        migrated={},
        missing=frozenset({"owner/missing"}),
    )

    queue = build_metadata_migration_queue(
        Portfolio(projects=(missing, migrated, unknown)),
        inventory,
    )

    assert [candidate.project.id for candidate in queue] == ["missing"]


def test_queue_uses_priority_inside_each_wave() -> None:
    high = Project(
        id="high",
        name="High",
        repository="owner/high",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    low = Project(
        id="low",
        name="Low",
        repository="owner/low",
        status=ProjectStatus.HARDENING,
        priority=Priority.LOW,
    )
    inventory = MetadataInventory(
        migrated={},
        missing=frozenset({"owner/high", "owner/low"}),
    )

    queue = build_metadata_migration_queue(
        Portfolio(projects=(low, high)),
        inventory,
    )

    assert [candidate.project.id for candidate in queue] == ["high", "low"]
