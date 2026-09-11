"""Run-scoped response caching for repeated GitHub REST reads."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from project_reminders.infrastructure.github import (
    GitHubOperationalState,
    GitHubRepositoryEvidence,
)

Query = dict[str, str] | None
CacheKey = tuple[str, str, tuple[tuple[str, str], ...]]
Loader = Callable[[str, Query], object]


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
