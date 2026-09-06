"""Application-service tests."""

from datetime import datetime, timezone

import pytest

from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def test_add_and_update_project(tmp_path) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc)
    service = PortfolioService(
        JsonPortfolioRepository(tmp_path / "projects.json"),
        clock=lambda: now,
    )

    project = service.add_project(
        name="Tracker",
        repository="owner/tracker",
        status=ProjectStatus.ACTIVE_DEVELOPMENT,
        priority=Priority.HIGH,
        next_action="Add assessment",
    )
    updated = service.set_health(project.id, HealthDimension.CI, HealthState.COMPLETE)

    assert updated.health.state_for(HealthDimension.CI) is HealthState.COMPLETE
    assert service.find("owner/tracker").id == project.id


def test_duplicate_repository_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = PortfolioService(JsonPortfolioRepository(tmp_path / "projects.json"))
    service.add_project(
        name="One",
        repository="owner/repo",
        status=ProjectStatus.IDEA,
        priority=Priority.MEDIUM,
    )

    with pytest.raises(ValueError, match="already tracked"):
        service.add_project(
            name="Two",
            repository="OWNER/REPO",
            status=ProjectStatus.IDEA,
            priority=Priority.MEDIUM,
        )
