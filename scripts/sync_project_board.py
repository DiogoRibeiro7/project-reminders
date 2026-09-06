"""Synchronize the code portfolio into the bound GitHub Projects v2 board."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GRAPHQL_URL = "https://api.github.com/graphql"
MARKER_PREFIX = "<!-- project-reminders:id="
MARKER_SUFFIX = " -->"

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """One single-select option managed by the board synchronizer."""

    name: str
    color: str
    description: str


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One custom Project field managed by the board synchronizer."""

    name: str
    data_type: str
    options: tuple[OptionSpec, ...] = ()


FIELD_SPECS = (
    FieldSpec(
        "Lifecycle",
        "SINGLE_SELECT",
        (
            OptionSpec("idea", "GRAY", "Idea or unvalidated concept"),
            OptionSpec("prototype", "BLUE", "Working prototype"),
            OptionSpec("active_development", "GREEN", "Active development"),
            OptionSpec("hardening", "YELLOW", "Testing and production hardening"),
            OptionSpec("portfolio_ready", "PURPLE", "Portfolio-ready project"),
            OptionSpec("maintenance", "BLUE", "Maintenance mode"),
            OptionSpec("paused", "ORANGE", "Temporarily paused"),
            OptionSpec("archived", "GRAY", "Archived project"),
            OptionSpec("abandoned", "RED", "Abandoned project"),
        ),
    ),
    FieldSpec(
        "Priority",
        "SINGLE_SELECT",
        (
            OptionSpec("low", "GRAY", "Low priority"),
            OptionSpec("medium", "BLUE", "Medium priority"),
            OptionSpec("high", "ORANGE", "High priority"),
            OptionSpec("critical", "RED", "Critical priority"),
        ),
    ),
    FieldSpec(
        "CI",
        "SINGLE_SELECT",
        (
            OptionSpec("unknown", "GRAY", "CI state has not been observed"),
            OptionSpec("none", "GRAY", "No CI workflow observed"),
            OptionSpec("pending", "YELLOW", "Latest CI is pending"),
            OptionSpec("passing", "GREEN", "Latest CI is passing"),
            OptionSpec("failing", "RED", "Latest CI is failing"),
            OptionSpec("cancelled", "PURPLE", "Latest CI was cancelled"),
        ),
    ),
    FieldSpec("Repository URL", "TEXT"),
    FieldSpec("Next action", "TEXT"),
    FieldSpec("Health", "TEXT"),
    FieldSpec("Open PRs", "NUMBER"),
    FieldSpec("Last activity", "TEXT"),
)


class GraphQLClient:
    """Minimal authenticated GitHub GraphQL client."""

    def __init__(self, token: str) -> None:
        if not token.strip():
            raise ValueError("PROJECT_TOKEN must not be empty")
        self._token = token

    def execute(self, query: str, variables: JsonObject) -> JsonObject:
        """Execute one GraphQL operation and return its data object."""

        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = Request(
            GRAPHQL_URL,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "project-reminders",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub GraphQL request failed: {exc.reason}") from exc

        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise TypeError("GitHub GraphQL response must be an object")
        errors = decoded.get("errors")
        if errors:
            raise RuntimeError(f"GitHub GraphQL error: {json.dumps(errors)}")
        data = decoded.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("GitHub GraphQL response did not contain data")
        return data


def _load_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _marker(project_id: str) -> str:
    return f"{MARKER_PREFIX}{project_id}{MARKER_SUFFIX}"


def _managed_id(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(MARKER_PREFIX) and stripped.endswith(MARKER_SUFFIX):
            return stripped[len(MARKER_PREFIX) : -len(MARKER_SUFFIX)]
    return None


def _next_action(project: JsonObject) -> str:
    action = project.get("next_action")
    if isinstance(action, dict):
        description = action.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
    return "—"


def _health_summary(project: JsonObject) -> str:
    health = project.get("health")
    if not isinstance(health, dict) or not health:
        return "unknown"

    satisfied = {"complete", "not_applicable"}
    complete = sum(1 for state in health.values() if state in satisfied)
    gaps = [
        f"{dimension}={state}"
        for dimension, state in sorted(health.items())
        if state not in satisfied
    ]
    summary = f"{complete}/{len(health)} satisfied"
    return summary if not gaps else f"{summary}; " + ", ".join(gaps)


def _operational(project: JsonObject) -> JsonObject:
    value = project.get("operational")
    return value if isinstance(value, dict) else {}


def _ci_state(project: JsonObject) -> str:
    value = _operational(project).get("ci_state")
    return value if isinstance(value, str) else "unknown"


def _open_pr_count(project: JsonObject) -> int:
    value = _operational(project).get("open_pull_requests")
    return len(value) if isinstance(value, list) else 0


def _last_activity(project: JsonObject) -> str:
    value = _operational(project).get("latest_activity_at")
    return value if isinstance(value, str) and value else "—"


def _body(project: JsonObject) -> str:
    repository = str(project["repository"])
    summary = str(project.get("summary", "")).strip() or "—"
    blocker = str(project.get("blocker") or "—")
    return "\n".join(
        (
            _marker(str(project["id"])),
            "",
            f"Repository: https://github.com/{repository}",
            f"Lifecycle: {project['status']}",
            f"Priority: {project['priority']}",
            f"CI: {_ci_state(project)}",
            f"Open PRs: {_open_pr_count(project)}",
            f"Next action: {_next_action(project)}",
            f"Blocker: {blocker}",
            f"Health: {_health_summary(project)}",
            "",
            summary,
            "",
            "Synced from `project-reminders/data/projects.json`.",
        )
    )


def _fetch_board(client: GraphQLClient, owner: str, number: int) -> JsonObject:
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
          title
          fields(first: 100) {
            nodes {
              __typename
              ... on ProjectV2Field {
                id
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                  color
                  description
                }
              }
            }
          }
          items(first: 100) {
            nodes {
              id
              content {
                __typename
                ... on DraftIssue {
                  id
                  title
                  body
                }
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


def _create_field(
    client: GraphQLClient,
    project_id: str,
    spec: FieldSpec,
) -> JsonObject:
    if spec.options:
        query = """
        mutation(
          $project: ID!,
          $name: String!,
          $type: ProjectV2CustomFieldType!,
          $options: [ProjectV2SingleSelectFieldOptionInput!]
        ) {
          createProjectV2Field(
            input: {
              projectId: $project,
              name: $name,
              dataType: $type,
              singleSelectOptions: $options
            }
          ) {
            projectV2Field {
              __typename
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name color description }
              }
            }
          }
        }
        """
        options = [
            {
                "name": option.name,
                "color": option.color,
                "description": option.description,
            }
            for option in spec.options
        ]
        variables: JsonObject = {
            "project": project_id,
            "name": spec.name,
            "type": spec.data_type,
            "options": options,
        }
    else:
        query = """
        mutation($project: ID!, $name: String!, $type: ProjectV2CustomFieldType!) {
          createProjectV2Field(
            input: {projectId: $project, name: $name, dataType: $type}
          ) {
            projectV2Field {
              __typename
              ... on ProjectV2Field { id name dataType }
            }
          }
        }
        """
        variables = {
            "project": project_id,
            "name": spec.name,
            "type": spec.data_type,
        }

    data = client.execute(query, variables)
    result = data.get("createProjectV2Field")
    if not isinstance(result, dict) or not isinstance(result.get("projectV2Field"), dict):
        raise RuntimeError(f"GitHub did not return created field {spec.name!r}")
    return result["projectV2Field"]


def _ensure_select_options(
    client: GraphQLClient,
    field: JsonObject,
    spec: FieldSpec,
) -> JsonObject:
    raw_options = field.get("options")
    existing = raw_options if isinstance(raw_options, list) else []
    names = {option.get("name") for option in existing if isinstance(option, dict)}
    missing = [option for option in spec.options if option.name not in names]
    if not missing:
        return field

    combined: list[JsonObject] = []
    for option in existing:
        if not isinstance(option, dict):
            continue
        combined.append(
            {
                "id": option.get("id"),
                "name": str(option.get("name", "")),
                "color": str(option.get("color", "GRAY")),
                "description": str(option.get("description") or ""),
            }
        )
    combined.extend(
        {
            "name": option.name,
            "color": option.color,
            "description": option.description,
        }
        for option in missing
    )

    query = """
    mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
      updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
        projectV2Field {
          __typename
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name color description }
          }
        }
      }
    }
    """
    data = client.execute(query, {"field": field["id"], "options": combined})
    result = data.get("updateProjectV2Field")
    if not isinstance(result, dict) or not isinstance(result.get("projectV2Field"), dict):
        raise RuntimeError(f"GitHub did not return updated field {spec.name!r}")
    return result["projectV2Field"]


def _ensure_fields(
    client: GraphQLClient,
    board: JsonObject,
) -> dict[str, JsonObject]:
    project_id = str(board["id"])
    fields_connection = board.get("fields")
    raw_fields = fields_connection.get("nodes") if isinstance(fields_connection, dict) else []
    fields = [field for field in raw_fields if isinstance(field, dict)]
    by_name = {str(field.get("name")): field for field in fields if field.get("name")}

    managed: dict[str, JsonObject] = {}
    for spec in FIELD_SPECS:
        field = by_name.get(spec.name)
        if field is None:
            field = _create_field(client, project_id, spec)
        if spec.options:
            if field.get("__typename") != "ProjectV2SingleSelectField":
                raise RuntimeError(f"Project field {spec.name!r} has the wrong type")
            field = _ensure_select_options(client, field, spec)
        elif field.get("__typename") != "ProjectV2Field":
            raise RuntimeError(f"Project field {spec.name!r} has the wrong type")
        managed[spec.name] = field
    return managed


def _existing_items(board: JsonObject) -> dict[str, JsonObject]:
    items_connection = board.get("items")
    raw_items = items_connection.get("nodes") if isinstance(items_connection, dict) else []
    managed: dict[str, JsonObject] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, dict) or content.get("__typename") != "DraftIssue":
            continue
        project_id = _managed_id(str(content.get("body") or ""))
        if project_id:
            managed[project_id] = item
    return managed


def _create_item(
    client: GraphQLClient,
    project_id: str,
    project: JsonObject,
) -> str:
    query = """
    mutation($project: ID!, $title: String!, $body: String!) {
      addProjectV2DraftIssue(
        input: {projectId: $project, title: $title, body: $body}
      ) {
        projectItem { id }
      }
    }
    """
    data = client.execute(
        query,
        {
            "project": project_id,
            "title": str(project["name"]),
            "body": _body(project),
        },
    )
    result = data.get("addProjectV2DraftIssue")
    if not isinstance(result, dict):
        raise RuntimeError(f"Could not add board item for {project['name']}")
    item = result.get("projectItem")
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise RuntimeError(f"Could not read board item ID for {project['name']}")
    return item["id"]


def _update_draft_if_needed(
    client: GraphQLClient,
    item: JsonObject,
    project: JsonObject,
) -> bool:
    content = item.get("content")
    if not isinstance(content, dict):
        return False
    title = str(project["name"])
    body = _body(project)
    if content.get("title") == title and content.get("body") == body:
        return False
    draft_id = content.get("id")
    if not isinstance(draft_id, str):
        raise RuntimeError(f"Managed item for {project['name']} has no draft issue ID")

    query = """
    mutation($draft: ID!, $title: String!, $body: String!) {
      updateProjectV2DraftIssue(
        input: {draftIssueId: $draft, title: $title, body: $body}
      ) {
        draftIssue { id }
      }
    }
    """
    client.execute(query, {"draft": draft_id, "title": title, "body": body})
    return True


def _option_id(field: JsonObject, value: str) -> str:
    options = field.get("options")
    if not isinstance(options, list):
        raise RuntimeError(f"Field {field.get('name')} has no options")
    for option in options:
        if isinstance(option, dict) and option.get("name") == value:
            option_id = option.get("id")
            if isinstance(option_id, str):
                return option_id
    raise RuntimeError(f"Field {field.get('name')} has no option {value!r}")


def _field_values(
    fields: dict[str, JsonObject],
    project: JsonObject,
) -> list[tuple[str, JsonObject]]:
    repository = str(project["repository"])
    return [
        (
            str(fields["Lifecycle"]["id"]),
            {"singleSelectOptionId": _option_id(fields["Lifecycle"], str(project["status"]))},
        ),
        (
            str(fields["Priority"]["id"]),
            {"singleSelectOptionId": _option_id(fields["Priority"], str(project["priority"]))},
        ),
        (
            str(fields["CI"]["id"]),
            {"singleSelectOptionId": _option_id(fields["CI"], _ci_state(project))},
        ),
        (str(fields["Repository URL"]["id"]), {"text": f"https://github.com/{repository}"}),
        (str(fields["Next action"]["id"]), {"text": _next_action(project)}),
        (str(fields["Health"]["id"]), {"text": _health_summary(project)}),
        (str(fields["Open PRs"]["id"]), {"number": _open_pr_count(project)}),
        (str(fields["Last activity"]["id"]), {"text": _last_activity(project)}),
    ]


def _update_fields(
    client: GraphQLClient,
    project_id: str,
    item_id: str,
    values: list[tuple[str, JsonObject]],
) -> None:
    definitions = ["$project: ID!", "$item: ID!"]
    selections: list[str] = []
    variables: JsonObject = {"project": project_id, "item": item_id}
    for index, (field_id, value) in enumerate(values):
        field_variable = f"field{index}"
        value_variable = f"value{index}"
        definitions.extend(
            (f"${field_variable}: ID!", f"${value_variable}: ProjectV2FieldValue!")
        )
        variables[field_variable] = field_id
        variables[value_variable] = value
        selections.append(
            f"f{index}: updateProjectV2ItemFieldValue("
            f"input: {{projectId: $project, itemId: $item, "
            f"fieldId: ${field_variable}, value: ${value_variable}}}) "
            "{ projectV2Item { id } }"
        )

    query = "mutation(" + ", ".join(definitions) + ") {\n"
    query += "\n".join(selections)
    query += "\n}"
    client.execute(query, variables)


def _archive_item(client: GraphQLClient, project_id: str, item_id: str) -> None:
    query = """
    mutation($project: ID!, $item: ID!) {
      archiveProjectV2Item(input: {projectId: $project, itemId: $item}) {
        item { id }
      }
    }
    """
    client.execute(query, {"project": project_id, "item": item_id})


def _update_board_description(client: GraphQLClient, project_id: str) -> None:
    query = """
    mutation($project: ID!, $short: String!, $readme: String!) {
      updateProjectV2(
        input: {projectId: $project, shortDescription: $short, readme: $readme}
      ) {
        projectV2 { id }
      }
    }
    """
    client.execute(
        query,
        {
            "project": project_id,
            "short": "Live code-portfolio state synchronized by project-reminders.",
            "readme": (
                "# Code Projects\n\n"
                "This board is synchronized from `project-reminders/data/projects.json`. "
                "Lifecycle is declared state; CI and engineering health are observed evidence."
            ),
        },
    )


def sync(root: Path, token: str) -> tuple[int, int, int]:
    """Synchronize all tracked projects and return created, updated, archived counts."""

    binding = _load_json(root / "data" / "github_project.json")
    portfolio = _load_json(root / "data" / "projects.json")
    owner = str(binding["owner"])
    number = int(binding["number"])
    raw_projects = portfolio.get("projects")
    if not isinstance(raw_projects, list):
        raise TypeError("data/projects.json must contain a projects list")
    projects = [project for project in raw_projects if isinstance(project, dict)]

    client = GraphQLClient(token)
    board = _fetch_board(client, owner, number)
    project_id = str(board["id"])
    fields = _ensure_fields(client, board)
    existing = _existing_items(board)
    _update_board_description(client, project_id)

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

    archived = 0
    for tracked_id, item in existing.items():
        if tracked_id not in expected_ids:
            _archive_item(client, project_id, str(item["id"]))
            archived += 1

    return created, updated, archived


def main() -> int:
    """Run the board synchronization from the repository root."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        created, updated, archived = sync(root, token)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Board sync complete: created={created}, updated={updated}, archived={archived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
