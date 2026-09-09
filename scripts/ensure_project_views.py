"""Create the managed GitHub Project views that do not already exist."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from project_reminders.application.project_views import missing_view_specs

GRAPHQL_URL = "https://api.github.com/graphql"
REST_API_URL = "https://api.github.com"
API_VERSION = "2026-03-10"
JsonObject = dict[str, Any]


def _load_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _request(token: str, url: str, *, data: JsonObject | None = None) -> object:
    if not token.strip():
        raise ValueError("PROJECT_TOKEN must not be empty")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(
        url,
        data=body,
        method="POST" if body is not None else "GET",
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


def _graphql(token: str, query: str, variables: JsonObject) -> JsonObject:
    raw = _request(token, GRAPHQL_URL, data={"query": query, "variables": variables})
    if not isinstance(raw, dict):
        raise TypeError("GitHub GraphQL response must be an object")
    if raw.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {json.dumps(raw['errors'])}")
    data = raw.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub GraphQL response did not contain data")
    return data


def _board_metadata(token: str, owner: str, number: int) -> tuple[str, dict[str, int]]:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          views(first: 100) { nodes { name } }
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field { name databaseId }
              ... on ProjectV2SingleSelectField { name databaseId }
              ... on ProjectV2IterationField { name databaseId }
            }
          }
        }
      }
    }
    """
    data = _graphql(token, query, {"login": owner, "number": number})
    user = data.get("user")
    if not isinstance(user, dict):
        raise RuntimeError(f"GitHub user {owner!r} was not found")
    project = user.get("projectV2")
    if not isinstance(project, dict):
        raise RuntimeError(f"GitHub Project #{number} was not found for {owner}")

    views_connection = project.get("views")
    view_nodes = views_connection.get("nodes") if isinstance(views_connection, dict) else None
    if not isinstance(view_nodes, list):
        raise RuntimeError("GitHub Project views were not returned")
    existing_names = {
        str(view.get("name"))
        for view in view_nodes
        if isinstance(view, dict) and isinstance(view.get("name"), str)
    }

    fields_connection = project.get("fields")
    field_nodes = fields_connection.get("nodes") if isinstance(fields_connection, dict) else None
    if not isinstance(field_nodes, list):
        raise RuntimeError("GitHub Project fields were not returned")
    field_ids: dict[str, int] = {}
    for field in field_nodes:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        database_id = field.get("databaseId")
        if isinstance(name, str) and isinstance(database_id, int):
            field_ids[name] = database_id
    return "\n".join(sorted(existing_names)), field_ids


def _field_ids(names: tuple[str, ...], fields: dict[str, int]) -> list[int]:
    missing = [name for name in names if name not in fields]
    if missing:
        raise RuntimeError(f"Project fields not found: {', '.join(missing)}")
    return [fields[name] for name in names]


def _create_view(
    token: str,
    owner: str,
    project_number: int,
    spec_name: str,
    layout: str,
    filter_query: str,
    visible_fields: tuple[str, ...],
    sort_by: tuple[tuple[str, str], ...],
    group_by: tuple[str, ...],
    vertical_group_by: tuple[str, ...],
    fields: dict[str, int],
) -> None:
    payload: JsonObject = {
        "name": spec_name,
        "layout": layout,
        "filter": filter_query,
        "visible_fields": _field_ids(visible_fields, fields),
    }
    if sort_by:
        payload["sort_by"] = [[fields[name], direction] for name, direction in sort_by]
    if group_by:
        payload["group_by"] = _field_ids(group_by, fields)
    if vertical_group_by:
        payload["vertical_group_by"] = _field_ids(vertical_group_by, fields)

    endpoint = (
        f"{REST_API_URL}/users/{quote(owner, safe='')}/projectsV2/{project_number}/views"
    )
    _request(token, endpoint, data=payload)


def main() -> int:
    """Provision missing managed views without modifying existing views."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        binding = _load_json(root / "data" / "github_project.json")
        owner = str(binding["owner"])
        number = int(binding["number"])
        existing_text, fields = _board_metadata(token, owner, number)
        existing_names = set(existing_text.splitlines()) if existing_text else set()
        specs = missing_view_specs(existing_names)
        for spec in specs:
            _create_view(
                token,
                owner,
                number,
                spec.name,
                spec.layout,
                spec.filter_query,
                spec.visible_fields,
                spec.sort_by,
                spec.group_by,
                spec.vertical_group_by,
                fields,
            )
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Project views: existing={len(existing_names)}, created={len(specs)}")
    for spec in specs:
        print(f"  + {spec.name} [{spec.layout}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
