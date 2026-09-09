"""Synchronize typed Project metrics used by operational portfolio views."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from project_reminders.application.board_markers import parse_managed_marker
from project_reminders.application.board_metrics import activity_date, health_score
from scripts.sync_project_board import GraphQLClient, _load_json

JsonObject = dict[str, Any]
FIELD_SPECS = (("Health score", "NUMBER"), ("Activity date", "DATE"))


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
    project_id = str(board["id"])
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
            field = _create_field(client, project_id, name, data_type)
        if field.get("__typename") != "ProjectV2Field" or field.get("dataType") != data_type:
            raise RuntimeError(f"Project field {name!r} has the wrong type")
        managed[name] = field
    return managed


def _field_name(value: JsonObject) -> str | None:
    field = value.get("field")
    if not isinstance(field, dict):
        return None
    name = field.get("name")
    return name if isinstance(name, str) else None


def _current_metrics(item: JsonObject) -> tuple[int | None, str | None]:
    connection = item.get("fieldValues")
    raw_nodes = connection.get("nodes") if isinstance(connection, dict) else None
    nodes = raw_nodes if isinstance(raw_nodes, list) else []
    score: int | None = None
    date: str | None = None
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        name = _field_name(raw)
        if name == "Health score":
            number = raw.get("number")
            if isinstance(number, (int, float)) and not isinstance(number, bool):
                score = int(number)
        elif name == "Activity date":
            value = raw.get("date")
            if isinstance(value, str):
                date = value
    return score, date


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
              fieldValues(first: 20) {
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
        data = client.execute(
            query,
            {"login": owner, "number": number, "cursor": cursor},
        )
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


def _sync_values(
    client: GraphQLClient,
    project_id: str,
    item_id: str,
    fields: dict[str, JsonObject],
    *,
    current_score: int | None,
    desired_score: int,
    current_date: str | None,
    desired_date: str | None,
) -> bool:
    operations: list[str] = []
    variables: JsonObject = {"project": project_id, "item": item_id}
    definitions = ["$project: ID!", "$item: ID!"]

    if current_score != desired_score:
        definitions.extend(("$scoreField: ID!", "$scoreValue: ProjectV2FieldValue!"))
        variables["scoreField"] = str(fields["Health score"]["id"])
        variables["scoreValue"] = {"number": desired_score}
        operations.append(
            "score: updateProjectV2ItemFieldValue(input: {projectId: $project, "
            "itemId: $item, fieldId: $scoreField, value: $scoreValue}) "
            "{ projectV2Item { id } }"
        )

    if current_date != desired_date:
        variables["dateField"] = str(fields["Activity date"]["id"])
        definitions.append("$dateField: ID!")
        if desired_date is None:
            operations.append(
                "date: clearProjectV2ItemFieldValue(input: {projectId: $project, "
                "itemId: $item, fieldId: $dateField}) { projectV2Item { id } }"
            )
        else:
            definitions.append("$dateValue: ProjectV2FieldValue!")
            variables["dateValue"] = {"date": desired_date}
            operations.append(
                "date: updateProjectV2ItemFieldValue(input: {projectId: $project, "
                "itemId: $item, fieldId: $dateField, value: $dateValue}) "
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
    """Ensure typed metric fields and synchronize changed managed cards."""

    binding = _load_json(root / "data" / "github_project.json")
    portfolio = _load_json(root / "data" / "projects.json")
    owner = str(binding["owner"])
    number = int(binding["number"])
    raw_projects = portfolio.get("projects")
    if not isinstance(raw_projects, list):
        raise TypeError("data/projects.json must contain a projects list")
    projects = {
        str(project["id"]): project
        for project in raw_projects
        if isinstance(project, dict) and "id" in project
    }

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
        project = projects.get(marker.project_id)
        if project is None:
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        managed += 1
        current_score, current_date = _current_metrics(item)
        if _sync_values(
            client,
            project_id,
            item_id,
            fields,
            current_score=current_score,
            desired_score=health_score(project),
            current_date=current_date,
            desired_date=activity_date(project),
        ):
            changed += 1
    return managed, changed


def main() -> int:
    """Run typed Project metric synchronization from the repository root."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        managed, changed = sync(root, token)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Project view metrics: managed={managed}, changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
