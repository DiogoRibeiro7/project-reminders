"""Operational-state regression tests."""

from datetime import datetime, timezone

from project_reminders.application.dashboard import build_dashboard
from project_reminders.application.operational import OperationalRefreshService
from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import CIState, Priority, ProjectStatus
from project_reminders.domain.models import OperationalSnapshot, Portfolio, Project, PullRequestSnapshot
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


class _Gateway:
    def snapshot(self, repository: str) -> OperationalSnapshot:
        if repository.endswith("broken"):
            raise RuntimeError("rate limited")
        now = datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc)
        return OperationalSnapshot(
            open_pull_requests=(PullRequestSnapshot(7, "Ship feature", False, now),),
            ci_state=CIState.FAILING,
            latest_activity_at=now,
            latest_release="v1.2.0",
            latest_release_at=now,
            latest_tag="v1.2.0",
            observed_at=now,
        )


def test_refresh_isolates_repository_failures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = JsonPortfolioRepository(tmp_path / "projects.json")
    store.save(
        Portfolio(
            projects=(
                Project(id="one", name="One", repository="owner/one"),
                Project(id="broken", name="Broken", repository="owner/broken"),
            )
        )
    )
    service = PortfolioService(store)
    result = OperationalRefreshService(service, _Gateway()).refresh(write=True)

    assert result.updated == ("owner/one",)
    assert result.failed[0][0] == "owner/broken"
    assert service.find("one").operational.ci_state is CIState.FAILING
    assert service.find("broken").operational.ci_state is CIState.UNKNOWN


def test_failing_ci_raises_dashboard_attention() -> None:
    project = Project(
        id="one",
        name="One",
        repository="owner/one",
        status=ProjectStatus.HARDENING,
        priority=Priority.MEDIUM,
        operational=OperationalSnapshot(ci_state=CIState.FAILING),
    )
    dashboard = build_dashboard(Portfolio(projects=(project,)))

    assert "Latest CI is failing" in dashboard.cards[0].reasons
