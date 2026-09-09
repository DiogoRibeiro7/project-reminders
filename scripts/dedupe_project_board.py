"""Archive legacy duplicate draft cards from the bound GitHub Project board."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from project_reminders.application.board_markers import legacy_duplicate_item_ids

GRAPHQL_URL = "https://api.github.com/graphql"
JsonObject = dict[str, Any]


def _load_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _graphql(token: str, query: str, variables: JsonObject) -> JsonObject:
    if not token.strip():
        raise ValueError("PROJECT_TOKEN must not be empty")
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "project-reminders",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub GraphQL request failed: {exc.reason}") from exc
    if not isinstance(decoded, dict):
        raise TypeError("GitHub GraphQL response must be an object")
    if decoded.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {json.dumps(decoded['errors'])}")
    data = decoded.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub GraphQL response did not contain data")
    return data


def _board_items(token: str, owner: str, number: int) -> tuple[str, list[object]]:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          items(first: 100) {
            nodes {
              id
              content {
                __typename
                ... on DraftIssue { body }
              }
            }
            pageInfo { hasNextPage }
          }
        }
      }
    }
    """
    data = _graphql(token, query, {"login": owner, "number": number})
    user = data.get("user")
    if not isinstance(user, dict):
        raise RuntimeError(f"GitHub user {owner!r} was not found")
    board = user.get("projectV2")
    if not isinstance(board, dict):
        raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")
    items = board.get("items")
    if not isinstance(items, dict):
        raise RuntimeError("GitHub Project did not return items")
    page_info = items.get("pageInfo")
    if isinstance(page_info, dict) and page_info.get("hasNextPage") is True:
        raise RuntimeError("board cleanup refuses to operate on more than 100 active items")
    nodes = items.get("nodes")
    if not isinstance(nodes, list):
        raise RuntimeError("GitHub Project items must be a list")
    return str(board["id"]), nodes


def _archive(token: str, project_id: str, item_id: str) -> None:
    query = """
    mutation($project: ID!, $item: ID!) {
      archiveProjectV2Item(input: {projectId: $project, itemId: $item}) {
        item { id }
      }
    }
    """
    _graphql(token, query, {"project": project_id, "item": item_id})


def main() -> int:
    """Archive only legacy cards that already have a current-format replacement."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        binding = _load_json(root / "data" / "github_project.json")
        portfolio = _load_json(root / "data" / "projects.json")
        raw_projects = portfolio.get("projects")
        if not isinstance(raw_projects, list):
            raise TypeError("data/projects.json must contain a projects list")
        tracked_ids = frozenset(
            str(project["id"])
            for project in raw_projects
            if isinstance(project, dict) and project.get("id") is not None
        )
        project_id, items = _board_items(token, str(binding["owner"]), int(binding["number"]))
        duplicate_ids = legacy_duplicate_item_ids(items, tracked_ids)
        for item_id in duplicate_ids:
            _archive(token, project_id, item_id)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Legacy board cleanup complete: archived={len(duplicate_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
