"""Minimal GitHub repository-discovery adapter using the standard library."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_reminders.application.github_import import DiscoveredRepository

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


class GitHubRepositoryDiscovery:
    """List repositories accessible to the authenticated GitHub user."""

    def __init__(self, token: str, *, api_url: str = "https://api.github.com") -> None:
        if not token.strip():
            raise ValueError("GitHub token must not be empty")
        self._token = token
        self._api_url = api_url.rstrip("/")

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

    def _get_json(self, path: str, query: dict[str, str]) -> object:
        request = Request(
            f"{self._api_url}{path}?{urlencode(query)}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "project-reminders",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS API by default
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"GitHub API returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc

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
