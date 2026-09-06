"""JSON persistence regression tests."""

from datetime import UTC, datetime

from project_reminders.domain.enums import HealthDimension, HealthState, ProjectStatus
from project_reminders.domain.models import EngineeringHealth, Portfolio, Project
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def test_portfolio_round_trip_preserves_project_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "data" / "projects.json"
    repository = JsonPortfolioRepository(path)
    now = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)
    project = Project(
        id="abc123",
        name="Example",
        repository="owner/example",
        status=ProjectStatus.HARDENING,
        health=EngineeringHealth({HealthDimension.CI: HealthState.COMPLETE}),
        created_at=now,
        updated_at=now,
    )

    repository.save(Portfolio(projects=(project,), generated_at=now))
    loaded = repository.load()

    assert loaded == Portfolio(projects=(project,), generated_at=now)
    assert loaded.projects[0].health.state_for(HealthDimension.CI) is HealthState.COMPLETE
