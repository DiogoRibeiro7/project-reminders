"""Create and reconcile declaratively managed GitHub Project views."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from project_reminders.application.project_views import MANAGED_VIEW_SPECS, ViewSpec

GRAPHQL_URL = "https://api.github.com/graphql"
REST_API_URL = "https://api.github.com"
API_VERSION = "2026-03-10"
JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class FieldRef:
    """GitHub Project field identifiers for REST and GraphQL view APIs."""

    node_id: str
    database_id: int


@dataclass(frozen=True, slots=True)
class ViewState:
    """Supported mutable state for one existing Project view."""

    node_id: str
    name: str
    layout: str
    filter_query: str
    visible_fields: tuple[str, ...]


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


def _board_metadata(
    token: str,
    owner: str,
    number: int,
) -> tuple[dict[str, ViewState], dict[str, FieldRef]]:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          views(first: 100) {
            nodes {
              id
              name
              layout
              filter
              configuration {
                visibleFields(first: 100) {
                  nodes {
                    __typename
                    ... on ProjectV2Field { id name }
                    ... on ProjectV2SingleSelectField { id name }
                    ... on ProjectV2IterationField { id name }
                  }
                }
              }
            }
          }
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field { id name databaseId }
              ... on ProjectV2SingleSelectField { id name databaseId }
              ... on ProjectV2IterationField { id name databaseId }
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
    views: dict[str, ViewState] = {}
    for raw in view_nodes:
        if not isinstance(raw, dict):
            continue
        node_id = raw.get("id")
        name = raw.get("name")
        layout = raw.get("layout")
        if not isinstance(node_id, str) or not isinstance(name, str) or not isinstance(layout, str):
            continue
        configuration = raw.get("configuration")
        visible_connection = (
            configuration.get("visibleFields") if isinstance(configuration, dict) else None
        )
        visible_nodes = (
            visible_connection.get("nodes") if isinstance(visible_connection, dict) else None
        )
        visible_fields = tuple(
            str(field["name"])
            for field in (visible_nodes if isinstance(visible_nodes, list) else [])
            if isinstance(field, dict) and isinstance(field.get("name"), str)
        )
        views[name.casefold()] = ViewState(
            node_id=node_id,
            name=name,
            layout=layout.casefold(),
            filter_query=str(raw.get("filter") or ""),
            visible_fields=visible_fields,
        )

    fields_connection = project.get("fields")
    field_nodes = fields_connection.get("nodes") if isinstance(fields_connection, dict) else None
    if not isinstance(field_nodes, list):
        raise RuntimeError("GitHub Project fields were not returned")
    fields: dict[str, FieldRef] = {}
    for field in field_nodes:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        node_id = field.get("id")
        database_id = field.get("databaseId")
        if isinstance(name, str) and isinstance(node_id, str) and isinstance(database_id, int):
            fields[name] = FieldRef(node_id=node_id, database_id=database_id)
    return views, fields


def _field_refs(names: tuple[str, ...], fields: dict[str, FieldRef]) -> tuple[FieldRef, ...]:
    missing = [name for name in names if name not in fields]
    if missing:
        raise RuntimeError(f"Project fields not found: {', '.join(missing)}")
    return tuple(fields[name] for name in names)


def _create_view(
    token: str,
    owner: str,
    project_number: int,
    spec: ViewSpec,
    fields: dict[str, FieldRef],
) -> None:
    payload: JsonObject = {
        "name": spec.name,
        "layout": spec.layout,
        "filter": spec.filter_query,
        "visible_fields": [ref.database_id for ref in _field_refs(spec.visible_fields, fields)],
    }
    if spec.sort_by:
        payload["sort_by"] = [
            [fields[name].database_id, direction] for name, direction in spec.sort_by
        ]
    if spec.group_by:
        payload["group_by"] = [ref.database_id for ref in _field_refs(spec.group_by, fields)]
    if spec.vertical_group_by:
        payload["vertical_group_by"] = [
            ref.database_id for ref in _field_refs(spec.vertical_group_by, fields)
        ]

    endpoint = (
        f"{REST_API_URL}/users/{quote(owner, safe='')}/projectsV2/{project_number}/views"
    )
    _request(token, endpoint, data=payload)


def _needs_update(state: ViewState, spec: ViewSpec) -> bool:
    return (
        state.name != spec.name
        or state.layout != spec.layout.casefold()
        or state.filter_query != spec.filter_query
        or state.visible_fields != spec.visible_fields
    )


def _update_view(
    token: str,
    state: ViewState,
    spec: ViewSpec,
    fields: dict[str, FieldRef],
) -> None:
    query = """
    mutation(
      $view: ID!,
      $name: String!,
      $layout: ProjectV2ViewLayout!,
      $filter: String!,
      $configuration: ProjectV2ViewConfigurationInput!
    ) {
      updateProjectV2View(
        input: {
          viewId: $view,
          name: $name,
          layout: $layout,
          filter: $filter,
          configuration: $configuration
        }
      ) {
        projectV2View { id }
      }
    }
    """
    _graphql(
        token,
        query,
        {
            "view": state.node_id,
            "name": spec.name,
            "layout": spec.layout.upper(),
            "filter": spec.filter_query,
            "configuration": {
                "visibleFieldIds": [
                    ref.node_id for ref in _field_refs(spec.visible_fields, fields)
                ]
            },
        },
    )


def main() -> int:
    """Provision missing views and reconcile supported state for owned views."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        binding = _load_json(root / "data" / "github_project.json")
        owner = str(binding["owner"])
        number = int(binding["number"])
        existing, fields = _board_metadata(token, owner, number)
        created: list[ViewSpec] = []
        updated: list[ViewSpec] = []
        for spec in MANAGED_VIEW_SPECS:
            state = existing.get(spec.name.casefold())
            if state is None:
                _create_view(token, owner, number, spec, fields)
                created.append(spec)
            elif _needs_update(state, spec):
                _update_view(token, state, spec, fields)
                updated.append(spec)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Project views: existing={len(existing)}, created={len(created)}, updated={len(updated)}"
    )
    for spec in created:
        print(f"  + {spec.name} [{spec.layout}]")
    for spec in updated:
        print(f"  ~ {spec.name} [{spec.layout}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
