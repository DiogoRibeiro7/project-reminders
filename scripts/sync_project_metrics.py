"""Synchronize all derived metrics on managed GitHub Project cards."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from project_reminders.application.board_markers import parse_managed_marker
from project_reminders.application.board_metrics import (
    activity_date,
    attention_metrics,
    health_score,
)
from project_reminders.infrastructure.json_store import JsonPortfolioRepository
from scripts.sync_project_board import GraphQLClient, _load_json

JsonObject = dict[str, Any]
FIELD_SPECS = (
    ("Health score", "NUMBER"),
    ("Activity date", "DATE"),
    ("Attention", "NUMBER"),
    ("Attention reasons", "NUMBER"),
)


def _board(client: GraphQLClient, owner: str, number: int) -> JsonObject:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field { id name dataType }
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
          ... on ProjectV2Field { id name dataType }
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
                  ... on ProjectV2ItemFieldDateValue {
                    date
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


def _current_values(item: JsonObject) -> dict[str, int | str | None]:
    values: dict[str, int | str | None] = {
        "Health score": None,
        "Activity date": None,
        "Attention": None,
        "Attention reasons": None,
    }
    connection = item.get("fieldValues")
    raw_nodes = connection.get("nodes") if isinstance(connection, dict) else None
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        field = raw.get("field")
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        if not isinstance(name, str) or name not in values:
            continue
        if name == "Activity date":
            date = raw.get("date")
            if isinstance(date, str):
                values[name] = date
        else:
            number = raw.get("number")
            if isinstance(number, (int, float)) and not isinstance(number, bool):
                values[name] = int(number)
    return values


def _sync_values(
    client: GraphQLClient,
    project_id: str,
    item_id: str,
    fields: dict[str, JsonObject],
    current: dict[str, int | str | None],
    desired: dict[str, int | str | None],
) -> bool:
    operations: list[str] = []
    variables: JsonObject = {"project": project_id, "item": item_id}
    definitions = ["$project: ID!", "$item: ID!"]

    for index, (name, _) in enumerate(FIELD_SPECS):
        if current[name] == desired[name]:
            continue
        field_var = f"field{index}"
        value_var = f"value{index}"
        definitions.append(f"${field_var}: ID!")
        variables[field_var] = str(fields[name]["id"])
        if name == "Activity date" and desired[name] is None:
            operations.append(
                f"metric{index}: clearProjectV2ItemFieldValue(input: {{projectId: $project, "
                f"itemId: $item, fieldId: ${field_var}}}) {{ projectV2Item {{ id }} }}"
            )
            continue
        definitions.append(f"${value_var}: ProjectV2FieldValue!")
        variables[value_var] = (
            {"date": desired[name]}
            if name == "Activity date"
            else {"number": desired[name]}
        )
        operations.append(
            f"metric{index}: updateProjectV2ItemFieldValue(input: {{projectId: $project, "
            f"itemId: $item, fieldId: ${field_var}, value: ${value_var}}}) "
            "{ projectV2Item { id } }"
        )

    if not operations:
        return False
    query = "mutation(" + ", ".join(definitions) + ") {\n"
    query += "\n".join(operations)
    query += "\n}"
    client.execute(query, variables)
    return True


def sync(root: Path, token: str) -> tuple[int, int]:
    """Ensure derived metric fields and synchronize changed managed cards."""

    binding = _load_json(root / "data" / "github_project.json")
    raw_portfolio = _load_json(root / "data" / "projects.json")
    typed_portfolio = JsonPortfolioRepository(root / "data" / "projects.json").load()
    owner = str(binding["owner"])
    number = int(binding["number"])

    raw_projects = raw_portfolio.get("projects")
    if not isinstance(raw_projects, list):
        raise TypeError("data/projects.json must contain a projects list")
    raw_by_id = {
        str(project["id"]): project
        for project in raw_projects
        if isinstance(project, dict) and "id" in project
    }
    typed_by_id = {project.id: project for project in typed_portfolio.projects}

    client = GraphQLClient(token)
    board = _board(client, owner, number)
    fields = _ensure_fields(client, board)
    project_id = str(board["id"])

    managed = 0
    changed = 0
    for item in _fetch_items(client, owner, number):
        content = item.get("content")
        if not isinstance(content, dict) or content.get("__typename") != "DraftIssue":
            continue
        marker = parse_managed_marker(str(content.get("body") or ""))
        if marker is None:
            continue
        raw_project = raw_by_id.get(marker.project_id)
        typed_project = typed_by_id.get(marker.project_id)
        item_id = item.get("id")
        if raw_project is None or typed_project is None or not isinstance(item_id, str):
            continue

        attention_score, attention_reasons = attention_metrics(typed_project)
        desired: dict[str, int | str | None] = {
            "Health score": health_score(raw_project),
            "Activity date": activity_date(raw_project),
            "Attention": attention_score,
            "Attention reasons": attention_reasons,
        }
        managed += 1
        if _sync_values(
            client,
            project_id,
            item_id,
            fields,
            _current_values(item),
            desired,
        ):
            changed += 1

    return managed, changed


def main() -> int:
    """Run combined Project metric synchronization from the repository root."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        managed, changed = sync(root, token)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Project metrics: managed={managed}, changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
