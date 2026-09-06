"""GitHub discovery/import behaviour tests."""

from __future__ import annotations

from datetime import UTC, datetime

from project_reminders.application.github_import import DiscoveredRepository, GitHubImportService
from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


class StubDiscovery:
    """Deterministic repository gateway for import tests."""

    def __init__(self, repositories: tuple[DiscoveredRepository, ...]) -> None:
        self._repositories = repositories

    def repositories(self) -> tuple[DiscoveredRepository, ...]:
        return self._repositories


def _repository(name: str, *, fork: bool = False, archived: bool = False) -> DiscoveredRepository:
    return DiscoveredRepository(
        full_name=f"owner/{name}",
        name=name,
        description=f"Description for {name}",
        private=True,
        fork=fork,
        archived=archived,
        default_branch="main",
        pushed_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_plan_skips_existing_forks_and_archived_by_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
    portfolio = PortfolioService(JsonPortfolioRepository(tmp_path / "projects.json"))
    portfolio.add_project(
        name="existing",
        repository="owner/existing",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
    )
    importer = GitHubImportService(
        portfolio,
        StubDiscovery(
            (
                _repository("new"),
                _repository("existing"),
                _repository("fork", fork=True),
                _repository("old", archived=True),
            )
        ),
    )

    plan = importer.plan()

    assert [item.name for item in plan.candidates] == ["new"]
    assert [item.name for item in plan.skipped_existing] == ["existing"]
    assert [item.name for item in plan.skipped_forks] == ["fork"]
    assert [item.name for item in plan.skipped_archived] == ["old"]


def test_import_does_not_infer_lifecycle_or_health(tmp_path) -> None:  # type: ignore[no-untyped-def]
    portfolio = PortfolioService(JsonPortfolioRepository(tmp_path / "projects.json"))
    importer = GitHubImportService(portfolio, StubDiscovery((_repository("new"),)))

    imported = importer.import_repositories()

    assert len(imported) == 1
    project = imported[0]
    assert project.status is ProjectStatus.IDEA
    assert project.priority is Priority.MEDIUM
    assert project.health.state_for(HealthDimension.CI) is HealthState.UNKNOWN
    assert project.health.state_for(HealthDimension.TESTS) is HealthState.UNKNOWN
    assert project.next_action is None
