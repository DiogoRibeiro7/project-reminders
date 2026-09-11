"""Run-scoped GitHub response-cache tests."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from email.message import Message
from urllib.error import HTTPError

import pytest

from project_reminders.domain.enums import CIState
from project_reminders.infrastructure.github import GitHubApiError
from project_reminders.infrastructure.github_cache import (
    CachedGitHubRepositoryEvidence,
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


def _api_error(message: str) -> GitHubApiError:
    headers = Message()
    body = io.BytesIO(json.dumps({"message": message}).encode("utf-8"))
    error = HTTPError(
        "https://api.github.com/repos/owner/empty/git/trees/main",
        409,
        "Conflict",
        headers,
        body,
    )
    return GitHubApiError(
        endpoint="/repos/owner/empty/git/trees/main",
        status=409,
        exc=error,
    )


class _EmptyEvidenceFixture(CachedGitHubRepositoryEvidence):
    def __init__(self, tree_message: str = "Git Repository is empty.") -> None:
        super().__init__("token", GitHubRunCache())
        self.tree_message = tree_message
        self.queries: list[tuple[str, dict[str, str] | None]] = []

    def _cached_get_json(self, path, query, loader):  # type: ignore[no-untyped-def]
        self.queries.append((path, query))
        if path == "/repos/owner/empty":
            return {"default_branch": "main", "language": None}
        if path == "/repos/owner/empty/git/trees/main":
            raise _api_error(self.tree_message)
        if path == "/repos/owner/empty/releases":
            return []
        if path == "/repos/owner/empty/tags":
            return []
        raise AssertionError(f"unexpected GitHub request: {path} {query}")


def test_empty_repository_is_complete_empty_assessment_evidence() -> None:
    gateway = _EmptyEvidenceFixture()

    evidence = gateway.evidence("owner/empty")

    assert evidence.paths == frozenset()
    assert evidence.complete_tree is True
    assert evidence.primary_language is None
    assert evidence.has_release is False
    assert evidence.has_tag is False
    assert evidence.pyproject_tools == frozenset()
    assert evidence.pyproject_inspected is True
    assert ("/repos/owner/empty/releases", {"per_page": "1"}) in gateway.queries
    assert ("/repos/owner/empty/tags", {"per_page": "1"}) in gateway.queries


def test_non_empty_repository_409_is_not_swallowed() -> None:
    gateway = _EmptyEvidenceFixture("Repository is locked.")

    with pytest.raises(GitHubApiError, match="Repository is locked"):
        gateway.evidence("owner/empty")


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
