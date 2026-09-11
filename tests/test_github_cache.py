"""Run-scoped GitHub response-cache tests."""

from datetime import UTC, datetime

from project_reminders.domain.enums import CIState
from project_reminders.infrastructure.github_cache import (
    ControlPlaneGitHubOperationalState,
    GitHubRunCache,
)


def test_run_cache_reuses_successful_response_across_callers() -> None:
    cache = GitHubRunCache()
    query = {"per_page": "1"}
    cache.store("https://api.github.com", "/repos/owner/repo/releases", query, [{"id": 1}])

    found, value = cache.lookup(
        "https://api.github.com/",
        "/repos/owner/repo/releases",
        {"per_page": "1"},
    )

    assert found is True
    assert value == [{"id": 1}]
    assert cache.hits == 1
    assert cache.entries == 1


def test_run_cache_does_not_claim_missing_or_failed_response() -> None:
    cache = GitHubRunCache()

    found, value = cache.lookup("https://api.github.com", "/repos/owner/repo", None)

    assert found is False
    assert value is None
    assert cache.hits == 0
    assert cache.entries == 0


def test_run_cache_normalizes_query_order() -> None:
    cache = GitHubRunCache()
    cache.store(
        "https://api.github.com",
        "/repos/owner/repo/pulls",
        {"state": "open", "page": "1"},
        [1],
    )

    found, value = cache.lookup(
        "https://api.github.com",
        "/repos/owner/repo/pulls",
        {"page": "1", "state": "open"},
    )

    assert found is True
    assert value == [1]


class _ControlPlaneFixture(ControlPlaneGitHubOperationalState):
    def __init__(self) -> None:
        super().__init__("token", GitHubRunCache(), "owner/control")
        self.queries: list[tuple[str, dict[str, str] | None]] = []

    def _cached_get_json(self, path, query, loader):  # type: ignore[no-untyped-def]
        self.queries.append((path, query))
        if path == "/repos/owner/control":
            return {
                "default_branch": "main",
                "pushed_at": "2026-09-11T13:00:55Z",
            }
        if path == "/repos/owner/control/commits":
            return [
                {
                    "commit": {
                        "message": "data: refresh code portfolio evidence",
                        "committer": {"date": "2026-09-11T13:00:55Z"},
                    }
                },
                {
                    "commit": {
                        "message": "fix: real code change",
                        "committer": {"date": "2026-09-11T12:58:50Z"},
                    }
                },
            ]
        if path == "/repos/owner/control/actions/runs":
            return {
                "workflow_runs": [
                    {
                        "name": "Refresh Code Portfolio",
                        "status": "in_progress",
                        "conclusion": None,
                        "html_url": "https://github.com/owner/control/actions/runs/3",
                        "updated_at": "2026-09-11T13:00:00Z",
                    },
                    {
                        "name": "Sync Code Projects board",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/owner/control/actions/runs/2",
                        "updated_at": "2026-09-11T12:59:30Z",
                    },
                    {
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/owner/control/actions/runs/1",
                        "updated_at": "2026-09-11T12:59:00Z",
                    },
                ]
            }
        if path == "/repos/owner/control/pulls":
            return []
        if path.endswith("/releases") or path.endswith("/tags"):
            return []
        raise AssertionError(f"unexpected GitHub request: {path} {query}")


def test_control_plane_observer_ignores_its_own_workflows_and_refresh_commits() -> None:
    gateway = _ControlPlaneFixture()

    snapshot = gateway.snapshot("owner/control")

    assert snapshot.ci_state is CIState.PASSING
    assert snapshot.ci_url == "https://github.com/owner/control/actions/runs/1"
    assert snapshot.ci_updated_at == datetime(2026, 9, 11, 12, 59, tzinfo=UTC)
    assert snapshot.latest_activity_at == datetime(2026, 9, 11, 12, 58, 50, tzinfo=UTC)
    actions_query = next(
        query for path, query in gateway.queries if path.endswith("/actions/runs")
    )
    assert actions_query == {"branch": "main", "per_page": "20"}
    assert ("/repos/owner/control/commits", {"per_page": "20"}) in gateway.queries
