"""Run-scoped GitHub response-cache tests."""

from project_reminders.infrastructure.github_cache import GitHubRunCache


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
