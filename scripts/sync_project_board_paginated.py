"""Synchronize Project #16 using complete item pagination and duplicate repair."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from project_reminders.application.board_inventory import reconcile_managed_items
from scripts.sync_project_board import (
    GraphQLClient,
    _archive_item,
    _create_item,
    _ensure_fields,
    _field_values,
    _load_json,
    _update_board_description,
    _update_draft_if_needed,
    _update_fields,
)

JsonObject = dict[str, Any]


def _fetch_board_metadata(client: GraphQLClient, owner: str, number: int) -> JsonObject:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          title
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field { id name dataType }
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name color description }
              }
            }
          }
        }
      }
    }
    """
    data = client.execute(query, {"login": owner, "number": number})
    user = data.get("user")
    if not isinstance(user, dict):
        raise RuntimeError(f"GitHub user {owner!r} was not found")
    project = user.get("projectV2")
    if not isinstance(project, dict):
        raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")
    return project


def _fetch_all_items(client: GraphQLClient, owner: str, number: int) -> list[object]:
    query = """
    query($login: String!, $number: Int!, $cursor: String) {
      user(login: $login) {
        projectV2(number: $number) {
          items(first: 100, after: $cursor) {
            nodes {
              id
              content {
                __typename
                ... on DraftIssue { id title body }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """
    cursor: str | None = None
    items: list[object] = []
    while True:
        data = client.execute(
            query,
            {"login": owner, "number": number, "cursor": cursor},
        )
        user = data.get("user")
        if not isinstance(user, dict):
            raise RuntimeError(f"GitHub user {owner!r} was not found")
        project = user.get("projectV2")
        if not isinstance(project, dict):
            raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")
        connection = project.get("items")
        if not isinstance(connection, dict):
            raise RuntimeError("GitHub Project did not return items")
        nodes = connection.get("nodes")
        if not isinstance(nodes, list):
            raise RuntimeError("GitHub Project item nodes must be a list")
        items.extend(nodes)
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise RuntimeError("GitHub Project item pagination metadata is missing")
        if page_info.get("hasNextPage") is not True:
            return items
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise RuntimeError("GitHub Project pagination cursor is missing")
        cursor = next_cursor


def sync(root: Path, token: str) -> tuple[int, int, int, int]:
    """Synchronize all tracked projects and repair duplicate managed cards."""

    binding = _load_json(root / "data" / "github_project.json")
    portfolio = _load_json(root / "data" / "projects.json")
    owner = str(binding["owner"])
    number = int(binding["number"])
    raw_projects = portfolio.get("projects")
    if not isinstance(raw_projects, list):
        raise TypeError("data/projects.json must contain a projects list")
    projects = [project for project in raw_projects if isinstance(project, dict)]

    client = GraphQLClient(token)
    board = _fetch_board_metadata(client, owner, number)
    project_id = str(board["id"])
    fields = _ensure_fields(client, board)
    inventory = reconcile_managed_items(_fetch_all_items(client, owner, number))
    existing = inventory.canonical
    _update_board_description(client, project_id)

    duplicate_archived = 0
    for item_id in inventory.duplicate_item_ids:
        _archive_item(client, project_id, item_id)
        duplicate_archived += 1

    created = 0
    updated = 0
    expected_ids: set[str] = set()
    for project in projects:
        tracked_id = str(project["id"])
        expected_ids.add(tracked_id)
        item = existing.get(tracked_id)
        if item is None:
            item_id = _create_item(client, project_id, project)
            created += 1
        else:
            item_id = str(item["id"])
            if _update_draft_if_needed(client, item, project):
                updated += 1
        _update_fields(client, project_id, item_id, _field_values(fields, project))

    stale_archived = 0
    for tracked_id, item in existing.items():
        if tracked_id not in expected_ids:
            _archive_item(client, project_id, str(item["id"]))
            stale_archived += 1

    return created, updated, stale_archived, duplicate_archived


def main() -> int:
    """Run complete board synchronization from the repository root."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        created, updated, stale_archived, duplicate_archived = sync(root, token)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        "Board sync complete: "
        f"created={created}, updated={updated}, "
        f"stale_archived={stale_archived}, duplicate_archived={duplicate_archived}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
