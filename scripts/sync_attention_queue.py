"""Synchronize exact dashboard attention metrics and ensure an Attention Queue view."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from project_reminders.application.board_markers import parse_managed_marker
from project_reminders.application.dashboard import build_project_card
from project_reminders.infrastructure.json_store import JsonPortfolioRepository
from scripts.sync_project_board import GraphQLClient, _load_json

JsonObject = dict[str, Any]
REST_API_URL = "https://api.github.com"
API_VERSION = "2026-03-10"
FIELD_SPECS = (("Attention", "NUMBER"), ("Attention reasons", "NUMBER"))
VIEW_NAME = "Attention Queue"


def _board(client: GraphQLClient, owner: str, number: int) -> JsonObject:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          views(first: 100) { nodes { name } }
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field { id name dataType databaseId }
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
    board = user.get("projectV2")
    if not isinstance(board, dict):
        raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")
    return board


def _create_field(
    client: GraphQLClient,
    project_id: str,
    name: str,
    data_type: str,
) -> JsonObject:
    query = """
    mutation($project: ID!, $name: String!, $type: ProjectV2CustomFieldType!) {
      createProjectV2Field(input: {projectId: $project, name: $name, dataType: $type}) {
        projectV2Field {
          __typename
          ... on ProjectV2Field { id name dataType databaseId }
        }
      }
    }
    """
    data = client.execute(
        query,
        {"project": project_id, "name": name, "type": data_type},
    )
    result = data.get("createProjectV2Field")
    if not isinstance(result, dict):
        raise RuntimeError(f"GitHub did not return created field {name!r}")
    field = result.get("projectV2Field")
    if not isinstance(field, dict):
        raise RuntimeError(f"GitHub did not return created field {name!r}")
    return field


def _ensure_fields(client: GraphQLClient, board: JsonObject) -> dict[str, JsonObject]:
    connection = board.get("fields")
    raw_nodes = connection.get("nodes") if isinstance(connection, dict) else None
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    existing = {
        str(field.get("name")): field
        for field in nodes
        if isinstance(field, dict) and isinstance(field.get("name"), str)
    }
    managed: dict[str, JsonObject] = {}
    for name, data_type in FIELD_SPECS:
        field = existing.get(name)
        if field is None:
            field = _create_field(client, str(board["id"]), name, data_type)
        if field.get("__typename") != "ProjectV2Field" or field.get("dataType") != data_type:
            raise RuntimeError(f"Project field {name!r} has the wrong type")
        managed[name] = field
    return managed


def _fetch_items(client: GraphQLClient, owner: str, number: int) -> list[JsonObject]:
    query = """
    query($login: String!, $number: Int!, $cursor: String) {
      user(login: $login) {
        projectV2(number: $number) {
          items(first: 100, after: $cursor) {
            nodes {
              id
              content {
                __typename
                ... on DraftIssue { body }
              }
              fieldValues(first: 30) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { ... on ProjectV2Field { name } }
                  }
                }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """
    cursor: str | None = None
    items: list[JsonObject] = []
    while True:
        data = client.execute(query, {"login": owner, "number": number, "cursor": cursor})
        user = data.get("user")
        if not isinstance(user, dict):
            raise RuntimeError(f"GitHub user {owner!r} was not found")
        board = user.get("projectV2")
        if not isinstance(board, dict):
            raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")
        connection = board.get("items")
        if not isinstance(connection, dict):
            raise RuntimeError("GitHub Project did not return items")
        nodes = connection.get("nodes")
        if not isinstance(nodes, list):
            raise RuntimeError("GitHub Project item nodes must be a list")
        items.extend(node for node in nodes if isinstance(node, dict))
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            raise RuntimeError("GitHub Project item pagination metadata is missing")
        if page_info.get("hasNextPage") is not True:
            return items
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise RuntimeError("GitHub Project pagination cursor is missing")
        cursor = next_cursor


def _current_values(item: JsonObject) -> tuple[int | None, int | None]:
    connection = item.get("fieldValues")
    raw_nodes = connection.get("nodes") if isinstance(connection, dict) else None
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    values: dict[str, int] = {}
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        field = raw.get("field")
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        number = raw.get("number")
        if (
            isinstance(name, str)
            and name in {"Attention", "Attention reasons"}
            and isinstance(number, (int, float))
            and not isinstance(number, bool)
        ):
            values[name] = int(number)
    return values.get("Attention"), values.get("Attention reasons")


def _update_values(
    client: GraphQLClient,
    project_id: str,
    item_id: str,
    fields: dict[str, JsonObject],
    score: int,
    reasons: int,
) -> None:
    query = """
    mutation(
      $project: ID!, $item: ID!,
      $scoreField: ID!, $scoreValue: ProjectV2FieldValue!,
      $reasonField: ID!, $reasonValue: ProjectV2FieldValue!
    ) {
      score: updateProjectV2ItemFieldValue(
        input: {projectId: $project, itemId: $item, fieldId: $scoreField, value: $scoreValue}
      ) { projectV2Item { id } }
      reasons: updateProjectV2ItemFieldValue(
        input: {projectId: $project, itemId: $item, fieldId: $reasonField, value: $reasonValue}
      ) { projectV2Item { id } }
    }
    """
    client.execute(
        query,
        {
            "project": project_id,
            "item": item_id,
            "scoreField": str(fields["Attention"]["id"]),
            "scoreValue": {"number": score},
            "reasonField": str(fields["Attention reasons"]["id"]),
            "reasonValue": {"number": reasons},
        },
    )


def _request(token: str, url: str, *, data: JsonObject) -> object:
    body = json.dumps(data).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "project-reminders",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc


def _ensure_view(token: str, owner: str, number: int, board: JsonObject) -> bool:
    views = board.get("views")
    raw_nodes = views.get("nodes") if isinstance(views, dict) else None
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    existing = {
        str(view.get("name")).casefold()
        for view in nodes
        if isinstance(view, dict) and isinstance(view.get("name"), str)
    }
    if VIEW_NAME.casefold() in existing:
        return False

    fields = board.get("fields")
    raw_fields = fields.get("nodes") if isinstance(fields, dict) else None
    field_nodes = raw_fields if isinstance(raw_fields, list) else []
    database_ids = {
        str(field.get("name")): field.get("databaseId")
        for field in field_nodes
        if isinstance(field, dict) and isinstance(field.get("databaseId"), int)
    }
    required = (
        "Title",
        "Lifecycle",
        "Priority",
        "CI",
        "Open PRs",
        "Next action",
        "Attention",
        "Attention reasons",
        "Repository URL",
    )
    missing = [name for name in required if name not in database_ids]
    if missing:
        raise RuntimeError(f"Project fields not found: {', '.join(missing)}")
    payload: JsonObject = {
        "name": VIEW_NAME,
        "layout": "table",
        "filter": "attention-reasons:>0 -Lifecycle:archived,abandoned",
        "visible_fields": [database_ids[name] for name in required],
        "sort_by": [
            [database_ids["Attention"], "desc"],
            [database_ids["Priority"], "desc"],
        ],
    }
    endpoint = f"{REST_API_URL}/users/{quote(owner, safe='')}/projectsV2/{number}/views"
    _request(token, endpoint, data=payload)
    return True


def sync(root: Path, token: str) -> tuple[int, int, bool]:
    """Synchronize exact attention metrics and ensure the queue view."""

    binding = _load_json(root / "data" / "github_project.json")
    owner = str(binding["owner"])
    number = int(binding["number"])
    portfolio = JsonPortfolioRepository(root / "data" / "projects.json").load()
    cards = {
        card.project.id: card
        for card in (build_project_card(project) for project in portfolio.projects)
    }

    client = GraphQLClient(token)
    board = _board(client, owner, number)
    fields = _ensure_fields(client, board)
    managed = 0
    changed = 0
    for item in _fetch_items(client, owner, number):
        content = item.get("content")
        if not isinstance(content, dict) or content.get("__typename") != "DraftIssue":
            continue
        marker = parse_managed_marker(str(content.get("body") or ""))
        if marker is None:
            continue
        card = cards.get(marker.project_id)
        item_id = item.get("id")
        if card is None or not isinstance(item_id, str):
            continue
        managed += 1
        desired = (card.attention_score, len(card.reasons))
        if _current_values(item) != desired:
            _update_values(client, str(board["id"]), item_id, fields, *desired)
            changed += 1

    refreshed_board = _board(client, owner, number)
    created_view = _ensure_view(token, owner, number, refreshed_board)
    return managed, changed, created_view


def main() -> int:
    """Run attention synchronization from the repository root."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        managed, changed, created_view = sync(root, token)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        "Attention queue: "
        f"managed={managed}, changed={changed}, view_created={str(created_view).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
