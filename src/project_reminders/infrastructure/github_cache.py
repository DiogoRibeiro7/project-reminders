"""Run-scoped response caching for repeated GitHub REST reads."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from project_reminders.infrastructure.github import (
    GitHubOperationalState,
    GitHubRepositoryEvidence,
    _encoded_repository,
)

Query = dict[str, str] | None
CacheKey = tuple[str, str, tuple[tuple[str, str], ...]]
Loader = Callable[[str, Query], object]
_CONTROL_WORKFLOW_NAMES = frozenset({"Refresh Code Portfolio", "Sync Code Projects board"})
_REFRESH_COMMIT_PREFIX = "data: refresh code portfolio evidence"


class GitHubRunCache:
    """Share successful GitHub GET responses within one refresh run."""

    def __init__(self) -> None:
        self._responses: dict[CacheKey, object] = {}
        self._lock = Lock()
        self._hits = 0

    @staticmethod
    def _key(api_url: str, path: str, query: Query) -> CacheKey:
        return api_url.rstrip("/"), path, tuple(sorted((query or {}).items()))

    def lookup(self, api_url: str, path: str, query: Query) -> tuple[bool, object | None]:
        """Return a cached successful response when one exists."""

        key = self._key(api_url, path, query)
        with self._lock:
            if key not in self._responses:
                return False, None
            self._hits += 1
            return True, self._responses[key]

    def store(self, api_url: str, path: str, query: Query, value: object) -> None:
        """Store one successful response for reuse later in the same run."""

        key = self._key(api_url, path, query)
        with self._lock:
            self._responses[key] = value

    @property
    def hits(self) -> int:
        """Number of network reads avoided by cache reuse."""

        with self._lock:
            return self._hits

    @property
    def entries(self) -> int:
        """Number of distinct successful responses retained."""

        with self._lock:
            return len(self._responses)


class _RunCachedGitHubMixin:
    _cache: GitHubRunCache
    _api_url: str

    def _cached_get_json(self, path: str, query: Query, loader: Loader) -> object:
        found, cached = self._cache.lookup(self._api_url, path, query)
        if found:
            return cached
        value = loader(path, query)
        self._cache.store(self._api_url, path, query, value)
        return value


class CachedGitHubRepositoryEvidence(_RunCachedGitHubMixin, GitHubRepositoryEvidence):
    """Assessment adapter reusing successful GETs from the current refresh run."""

    def __init__(
        self,
        token: str,
        cache: GitHubRunCache,
        *,
        api_url: str = "https://api.github.com",
    ) -> None:
        super().__init__(token, api_url=api_url)
        self._cache = cache

    def _get_json(self, path: str, query: Query = None) -> object:
        return self._cached_get_json(path, query, super()._get_json)


class CachedGitHubOperationalState(_RunCachedGitHubMixin, GitHubOperationalState):
    """Operational adapter reusing successful GETs from the current refresh run."""

    def __init__(
        self,
        token: str,
        cache: GitHubRunCache,
        *,
        api_url: str = "https://api.github.com",
    ) -> None:
        super().__init__(token, api_url=api_url)
        self._cache = cache

    def _get_json(self, path: str, query: Query = None) -> object:
        return self._cached_get_json(path, query, super()._get_json)


class ControlPlaneGitHubOperationalState(CachedGitHubOperationalState):
    """Cached operational adapter that removes control-plane self-observation noise."""

    def __init__(
        self,
        token: str,
        cache: GitHubRunCache,
        control_repository: str,
        *,
        api_url: str = "https://api.github.com",
    ) -> None:
        super().__init__(token, cache, api_url=api_url)
        self._control_repository = control_repository.casefold()
        self._control_encoded = _encoded_repository(control_repository)

    def _get_json(self, path: str, query: Query = None) -> object:
        metadata_path = f"/repos/{self._control_encoded}"
        actions_path = f"{metadata_path}/actions/runs"
        if path == metadata_path:
            raw = super()._get_json(path, query)
            if not isinstance(raw, dict):
                return raw
            commits = super()._get_json(f"{metadata_path}/commits", {"per_page": "20"})
            activity = self._latest_meaningful_activity(commits)
            return raw if activity is None else {**raw, "pushed_at": activity}
        if path == actions_path:
            expanded = dict(query or {})
            expanded["per_page"] = "20"
            raw = super()._get_json(path, expanded)
            if not isinstance(raw, dict):
                return raw
            runs = raw.get("workflow_runs")
            if not isinstance(runs, list):
                return raw
            filtered = [
                run
                for run in runs
                if not isinstance(run, dict)
                or str(run.get("name") or "") not in _CONTROL_WORKFLOW_NAMES
            ]
            return {**raw, "workflow_runs": filtered[:1]}
        return super()._get_json(path, query)

    @staticmethod
    def _latest_meaningful_activity(raw: object) -> str | None:
        if not isinstance(raw, list):
            return None
        for item in raw:
            if not isinstance(item, dict):
                continue
            commit = item.get("commit")
            if not isinstance(commit, dict):
                continue
            message = str(commit.get("message") or "")
            if message.startswith(_REFRESH_COMMIT_PREFIX):
                continue
            for actor_key in ("committer", "author"):
                actor = commit.get(actor_key)
                if not isinstance(actor, dict):
                    continue
                date = actor.get("date")
                if isinstance(date, str) and date:
                    return date
        return None
