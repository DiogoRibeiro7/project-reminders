"""Minimal GitHub adapters using the standard library."""

from __future__ import annotations

import base64
import json
import tomllib
from datetime import UTC, datetime
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from project_reminders.application.assessment import RepositoryEvidence
from project_reminders.application.github_import import DiscoveredRepository
from project_reminders.domain.enums import CIState
from project_reminders.domain.models import OperationalSnapshot, PullRequestSnapshot

JsonObject = dict[str, Any]


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("GitHub timestamp must be a string or null")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("GitHub timestamp must be timezone-aware")
    return parsed


class _GitHubClient:
    def __init__(self, token: str, *, api_url: str = "https://api.github.com") -> None:
        if not token.strip():
            raise ValueError("GitHub token must not be empty")
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        suffix = f"?{urlencode(query)}" if query else ""
        request = Request(
            f"{self._api_url}{path}{suffix}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "project-reminders",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"GitHub API returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc


def _encoded_repository(repository: str) -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise ValueError("repository must use owner/name form")
    return f"{quote(owner, safe='')}/{quote(name, safe='')}"


class GitHubRepositoryDiscovery(_GitHubClient):
    """List repositories accessible to the authenticated GitHub user."""

    def repositories(self) -> tuple[DiscoveredRepository, ...]:
        """Retrieve every repository for the authenticated user across pagination."""

        repositories: list[DiscoveredRepository] = []
        page = 1
        while True:
            payload = self._get_json(
                "/user/repos",
                {
                    "affiliation": "owner",
                    "per_page": "100",
                    "page": str(page),
                    "sort": "full_name",
                    "direction": "asc",
                },
            )
            if not isinstance(payload, list):
                raise TypeError("GitHub repository response must be a list")
            if not payload:
                break
            for raw in payload:
                repositories.append(self._repository_from_json(raw))
            if len(payload) < 100:
                break
            page += 1
        return tuple(repositories)

    @staticmethod
    def _repository_from_json(raw: object) -> DiscoveredRepository:
        if not isinstance(raw, dict):
            raise TypeError("GitHub repository entry must be an object")
        record = cast(JsonObject, raw)
        return DiscoveredRepository(
            full_name=str(record["full_name"]),
            name=str(record["name"]),
            description=str(record.get("description") or ""),
            private=bool(record.get("private", False)),
            fork=bool(record.get("fork", False)),
            archived=bool(record.get("archived", False)),
            default_branch=str(record.get("default_branch") or "main"),
            pushed_at=_parse_timestamp(record.get("pushed_at")),
        )


class GitHubRepositoryEvidence(_GitHubClient):
    """Collect deterministic engineering evidence from one GitHub repository."""

    def evidence(self, repository: str) -> RepositoryEvidence:
        """Read the default-branch tree, primary language, releases, tags and config."""

        encoded = _encoded_repository(repository)
        metadata_raw = self._get_json(f"/repos/{encoded}")
        if not isinstance(metadata_raw, dict):
            raise TypeError("GitHub repository metadata must be an object")
        metadata = cast(JsonObject, metadata_raw)
        default_branch = str(metadata.get("default_branch") or "main")
        language = metadata.get("language")
        tree_raw = self._get_json(
            f"/repos/{encoded}/git/trees/{quote(default_branch, safe='')}",
            {"recursive": "1"},
        )
        if not isinstance(tree_raw, dict):
            raise TypeError("GitHub tree response must be an object")
        tree_record = cast(JsonObject, tree_raw)
        entries_raw = tree_record.get("tree", [])
        if not isinstance(entries_raw, list):
            raise TypeError("GitHub tree entries must be a list")
        paths = frozenset(
            str(entry["path"])
            for entry in entries_raw
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        )
        pyproject_tools, pyproject_inspected = self._pyproject_tools(encoded, paths)
        releases_raw = self._get_json(f"/repos/{encoded}/releases", {"per_page": "1"})
        tags_raw = self._get_json(f"/repos/{encoded}/tags", {"per_page": "1"})
        if not isinstance(releases_raw, list) or not isinstance(tags_raw, list):
            raise TypeError("GitHub releases/tags response must be a list")
        return RepositoryEvidence(
            paths=paths,
            complete_tree=not bool(tree_record.get("truncated", False)),
            primary_language=str(language) if language is not None else None,
            has_release=bool(releases_raw),
            has_tag=bool(tags_raw),
            pyproject_tools=pyproject_tools,
            pyproject_inspected=pyproject_inspected,
        )

    def _pyproject_tools(
        self, encoded_repository: str, paths: frozenset[str]
    ) -> tuple[frozenset[str], bool]:
        if "pyproject.toml" not in paths:
            return frozenset(), True
        try:
            raw = self._get_json(f"/repos/{encoded_repository}/contents/pyproject.toml")
            if not isinstance(raw, dict):
                return frozenset(), False
            record = cast(JsonObject, raw)
            content = record.get("content")
            encoding = record.get("encoding")
            if not isinstance(content, str) or encoding != "base64":
                return frozenset(), False
            parsed = tomllib.loads(base64.b64decode(content).decode("utf-8"))
        except (RuntimeError, ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return frozenset(), False
        tool = parsed.get("tool", {})
        if not isinstance(tool, dict):
            return frozenset(), True
        return frozenset(str(name).casefold() for name in tool), True


class GitHubOperationalState(_GitHubClient):
    """Observe current pull-request, CI, activity, release and tag state."""

    def snapshot(self, repository: str) -> OperationalSnapshot:
        """Collect a current operational snapshot for one repository."""

        encoded = _encoded_repository(repository)
        metadata_raw = self._get_json(f"/repos/{encoded}")
        pulls_raw = self._get_json(
            f"/repos/{encoded}/pulls",
            {"state": "open", "sort": "updated", "direction": "desc", "per_page": "20"},
        )
        runs_raw = self._get_json(f"/repos/{encoded}/actions/runs", {"per_page": "1"})
        releases_raw = self._get_json(f"/repos/{encoded}/releases", {"per_page": "1"})
        tags_raw = self._get_json(f"/repos/{encoded}/tags", {"per_page": "1"})
        if not isinstance(metadata_raw, dict):
            raise TypeError("GitHub repository metadata must be an object")
        if not isinstance(pulls_raw, list):
            raise TypeError("GitHub pull request response must be a list")
        if not isinstance(runs_raw, dict):
            raise TypeError("GitHub Actions response must be an object")
        if not isinstance(releases_raw, list) or not isinstance(tags_raw, list):
            raise TypeError("GitHub releases/tags response must be a list")

        pull_requests: list[PullRequestSnapshot] = []
        for raw in pulls_raw:
            if not isinstance(raw, dict):
                continue
            record = cast(JsonObject, raw)
            pull_requests.append(
                PullRequestSnapshot(
                    number=int(record["number"]),
                    title=str(record.get("title") or ""),
                    draft=bool(record.get("draft", False)),
                    updated_at=_parse_timestamp(record.get("updated_at")),
                )
            )

        runs = runs_raw.get("workflow_runs", [])
        if not isinstance(runs, list):
            raise TypeError("workflow_runs must be a list")
        ci_state = CIState.NONE if not runs else self._ci_state(runs[0])

        release_name: str | None = None
        release_at: datetime | None = None
        if releases_raw and isinstance(releases_raw[0], dict):
            release = cast(JsonObject, releases_raw[0])
            release_name = str(release.get("tag_name") or release.get("name") or "") or None
            release_at = _parse_timestamp(release.get("published_at") or release.get("created_at"))

        latest_tag: str | None = None
        if tags_raw and isinstance(tags_raw[0], dict):
            latest_tag = str(cast(JsonObject, tags_raw[0]).get("name") or "") or None

        metadata = cast(JsonObject, metadata_raw)
        return OperationalSnapshot(
            open_pull_requests=tuple(pull_requests),
            ci_state=ci_state,
            latest_activity_at=_parse_timestamp(metadata.get("pushed_at")),
            latest_release=release_name,
            latest_release_at=release_at,
            latest_tag=latest_tag,
            observed_at=datetime.now(UTC),
        )

    @staticmethod
    def _ci_state(raw: object) -> CIState:
        if not isinstance(raw, dict):
            return CIState.UNKNOWN
        record = cast(JsonObject, raw)
        status = str(record.get("status") or "")
        conclusion = record.get("conclusion")
        if status in {"queued", "in_progress", "waiting", "requested", "pending"}:
            return CIState.PENDING
        if conclusion == "success":
            return CIState.PASSING
        if conclusion in {"failure", "timed_out", "action_required", "startup_failure"}:
            return CIState.FAILING
        if conclusion in {"cancelled", "skipped", "stale"}:
            return CIState.CANCELLED
        return CIState.UNKNOWN
