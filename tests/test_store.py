"""JSON persistence regression tests."""

from datetime import UTC, datetime

from project_reminders.domain.enums import CIState, HealthDimension, HealthState, ProjectStatus
from project_reminders.domain.models import (
    EngineeringHealth,
    OperationalSnapshot,
    Portfolio,
    Project,
    PullRequestSnapshot,
)
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
        operational=OperationalSnapshot(
            open_pull_requests=(
                PullRequestSnapshot(
                    number=7,
                    title="Ship",
                    draft=False,
                    updated_at=now,
                    url="https://github.com/owner/example/pull/7",
                ),
            ),
            ci_state=CIState.PASSING,
            ci_url="https://github.com/owner/example/actions/runs/123",
            ci_updated_at=now,
            latest_activity_at=now,
            latest_release="v1.0.0",
            latest_release_at=now,
            latest_release_url="https://github.com/owner/example/releases/tag/v1.0.0",
            latest_tag="v1.0.0",
            latest_tag_url="https://github.com/owner/example/tree/v1.0.0",
            observed_at=now,
        ),
        created_at=now,
        updated_at=now,
    )

    repository.save(Portfolio(projects=(project,), generated_at=now))
    loaded = repository.load()

    assert loaded == Portfolio(projects=(project,), generated_at=now)
    assert loaded.projects[0].health.state_for(HealthDimension.CI) is HealthState.COMPLETE
    assert loaded.projects[0].operational.ci_url == (
        "https://github.com/owner/example/actions/runs/123"
    )
    assert loaded.projects[0].operational.open_pull_requests[0].url == (
        "https://github.com/owner/example/pull/7"
    )
