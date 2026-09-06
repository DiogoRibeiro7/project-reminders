"""Application-service tests."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.domain.models import EngineeringHealth
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def _service(path: Path, now: datetime | None = None) -> PortfolioService:
    timestamp = now or datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc)
    return PortfolioService(JsonPortfolioRepository(path), clock=lambda: timestamp)


def test_add_and_update_project(tmp_path: Path) -> None:
    service = _service(tmp_path / "projects.json")

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


def test_duplicate_repository_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path / "projects.json")
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


def test_apply_health_preserves_lifecycle_and_next_action(tmp_path: Path) -> None:
    service = _service(tmp_path / "projects.json")
    project = service.add_project(
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
        next_action="Ship release",
    )

    updated = service.apply_health(
        project.id,
        EngineeringHealth({HealthDimension.CI: HealthState.COMPLETE}),
    )

    assert updated.status is ProjectStatus.HARDENING
    assert updated.priority is Priority.HIGH
    assert updated.next_action is not None
    assert updated.next_action.description == "Ship release"
    assert updated.health.state_for(HealthDimension.CI) is HealthState.COMPLETE
