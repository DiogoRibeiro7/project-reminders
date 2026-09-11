"""Application-service tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import (
    CIState,
    HealthDimension,
    HealthState,
    Priority,
    ProjectStatus,
)
from project_reminders.domain.models import EngineeringHealth, OperationalSnapshot
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def _service(path: Path, now: datetime | None = None) -> PortfolioService:
    timestamp = now or datetime(2026, 9, 6, 14, 0, tzinfo=UTC)
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


def test_identical_bulk_health_does_not_advance_generated_at(tmp_path: Path) -> None:
    path = tmp_path / "projects.json"
    started = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    health = EngineeringHealth({HealthDimension.TESTS: HealthState.COMPLETE})
    service = _service(path, started)
    project = service.add_project(
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    service.apply_health_many({project.repository: health})
    before = service.load()

    later = _service(path, started + timedelta(hours=12))
    later.apply_health_many({project.repository: health})
    after = later.load()

    assert after == before
    assert after.generated_at == started


def test_unchanged_operational_observation_is_coalesced_before_heartbeat(tmp_path: Path) -> None:
    path = tmp_path / "projects.json"
    started = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    service = _service(path, started)
    project = service.add_project(
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    initial = OperationalSnapshot(ci_state=CIState.PASSING, observed_at=started)
    service.apply_operational_many({project.repository: initial})
    before = service.load()

    checked_at = started + timedelta(hours=12)
    later = _service(path, checked_at)
    later.apply_operational_many(
        {
            project.repository: OperationalSnapshot(
                ci_state=CIState.PASSING,
                observed_at=checked_at,
            )
        }
    )
    after = later.load()

    assert after == before
    assert after.projects[0].operational.observed_at == started


def test_unchanged_operational_observation_refreshes_heartbeat_before_stale(tmp_path: Path) -> None:
    path = tmp_path / "projects.json"
    started = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    service = _service(path, started)
    project = service.add_project(
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    service.apply_operational_many(
        {
            project.repository: OperationalSnapshot(
                ci_state=CIState.PASSING,
                observed_at=started,
            )
        }
    )

    checked_at = started + timedelta(hours=19)
    later = _service(path, checked_at)
    later.apply_operational_many(
        {
            project.repository: OperationalSnapshot(
                ci_state=CIState.PASSING,
                observed_at=checked_at,
            )
        }
    )
    refreshed = later.load()

    assert refreshed.generated_at == checked_at
    assert refreshed.projects[0].operational.observed_at == checked_at


def test_changed_operational_evidence_persists_immediately(tmp_path: Path) -> None:
    path = tmp_path / "projects.json"
    started = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)
    service = _service(path, started)
    project = service.add_project(
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    service.apply_operational_many(
        {
            project.repository: OperationalSnapshot(
                ci_state=CIState.PASSING,
                observed_at=started,
            )
        }
    )

    changed_at = started + timedelta(hours=1)
    later = _service(path, changed_at)
    later.apply_operational_many(
        {
            project.repository: OperationalSnapshot(
                ci_state=CIState.FAILING,
                observed_at=changed_at,
            )
        }
    )
    changed = later.load()

    assert changed.generated_at == changed_at
    assert changed.projects[0].operational.ci_state is CIState.FAILING
    assert changed.projects[0].operational.observed_at == changed_at
