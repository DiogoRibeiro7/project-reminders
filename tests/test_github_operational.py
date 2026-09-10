"""GitHub operational-evidence adapter tests."""

from project_reminders.domain.enums import CIState
from project_reminders.infrastructure.github import GitHubOperationalState


class _GitHubOperationalFixture(GitHubOperationalState):
    def __init__(self) -> None:
        super().__init__("token")
        self.queries: list[tuple[str, dict[str, str] | None]] = []

    def _get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        self.queries.append((path, query))
        if path.endswith("/actions/runs"):
            return {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/owner/repo/actions/runs/55",
                        "updated_at": "2026-09-07T07:00:00Z",
                    }
                ]
            }
        if path.endswith("/pulls"):
            return [
                {
                    "number": 9,
                    "title": "Ship",
                    "draft": False,
                    "updated_at": "2026-09-07T06:00:00Z",
                    "html_url": "https://github.com/owner/repo/pull/9",
                }
            ]
        if path.endswith("/releases"):
            return [
                {
                    "tag_name": "v1.0.0",
                    "published_at": "2026-09-06T12:00:00Z",
                    "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
                }
            ]
        if path.endswith("/tags"):
            return [{"name": "v1.0.0"}]
        return {
            "default_branch": "develop",
            "pushed_at": "2026-09-07T07:30:00Z",
        }


class _PaginatedPullRequestFixture(_GitHubOperationalFixture):
    def _get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        if not path.endswith("/pulls"):
            return super()._get_json(path, query)

        self.queries.append((path, query))
        assert query is not None
        page = int(query["page"])
        if page == 1:
            return [
                {
                    "number": number,
                    "title": f"PR {number}",
                    "draft": False,
                    "updated_at": "2026-09-07T06:00:00Z",
                    "html_url": f"https://github.com/owner/repo/pull/{number}",
                }
                for number in range(1, 101)
            ]
        if page == 2:
            return [
                {
                    "number": 101,
                    "title": "PR 101",
                    "draft": True,
                    "updated_at": "2026-09-06T05:00:00Z",
                    "html_url": "https://github.com/owner/repo/pull/101",
                }
            ]
        raise AssertionError(f"unexpected pull-request page {page}")


def test_operational_snapshot_uses_default_branch_and_keeps_evidence_urls() -> None:
    gateway = _GitHubOperationalFixture()

    snapshot = gateway.snapshot("owner/repo")

    actions_query = next(query for path, query in gateway.queries if path.endswith("/actions/runs"))
    pulls_query = next(query for path, query in gateway.queries if path.endswith("/pulls"))
    assert actions_query == {"branch": "develop", "per_page": "1"}
    assert pulls_query == {
        "state": "open",
        "sort": "updated",
        "direction": "desc",
        "per_page": "100",
        "page": "1",
    }
    assert snapshot.ci_state is CIState.PASSING
    assert snapshot.ci_url == "https://github.com/owner/repo/actions/runs/55"
    assert snapshot.open_pull_requests[0].url == "https://github.com/owner/repo/pull/9"
    assert snapshot.latest_release_url == "https://github.com/owner/repo/releases/tag/v1.0.0"
    assert snapshot.latest_tag_url == "https://github.com/owner/repo/tree/v1.0.0"


def test_operational_snapshot_paginates_all_open_pull_requests() -> None:
    gateway = _PaginatedPullRequestFixture()

    snapshot = gateway.snapshot("owner/repo")

    pull_queries = [query for path, query in gateway.queries if path.endswith("/pulls")]
    assert pull_queries == [
        {
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "per_page": "100",
            "page": "1",
        },
        {
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "per_page": "100",
            "page": "2",
        },
    ]
    assert len(snapshot.open_pull_requests) == 101
    assert snapshot.open_pull_requests[0].number == 1
    assert snapshot.open_pull_requests[-1].number == 101
    assert snapshot.open_pull_requests[-1].draft is True
