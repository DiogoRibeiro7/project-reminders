from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, cast

PROJECTS_PATH = Path("data/projects.json")
BINDING_PATH = Path("data/github_project.json")
MARKER_PREFIX = "<!-- project-reminders-id:"


def graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return cast(dict[str, Any], data["data"])


def next_action_text(project: dict[str, Any]) -> str:
    value = project.get("next_action")
    if isinstance(value, str):
        return value.strip() or "—"
    if isinstance(value, dict):
        return str(value.get("description") or value.get("title") or "—")
    return "—"


def project_body(project: dict[str, Any]) -> str:
    health = project.get("health") or {}
    health_text = ", ".join(f"{key}={value}" for key, value in sorted(health.items())) or "unknown"
    operational = project.get("operational") or {}
    repository = project["repository"]
    return "\n".join(
        [
            f"{MARKER_PREFIX}{project['id']} -->",
            f"Repository: https://github.com/{repository}",
            f"Lifecycle: {project['status']}",
            f"Priority: {project['priority']}",
            f"CI: {operational.get('ci_state', 'unknown')}",
            f"Open PRs: {len(operational.get('open_pull_requests') or [])}",
            f"Next action: {next_action_text(project)}",
            f"Engineering health: {health_text}",
            "",
            str(project.get("summary") or ""),
        ]
    ).rstrip()


def get_project(token: str, owner: str, number: int) -> tuple[str, list[dict[str, Any]]]:
    query = """
    query($owner: String!, $number: Int!) {
      user(login: $owner) {
        projectV2(number: $number) {
          id
          items(first: 100) {
            nodes {
              id
              content {
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
    data = graphql(token, query, {"owner": owner, "number": number})
    project = data.get("user", {}).get("projectV2")
    if project is None:
        raise RuntimeError("Configured GitHub Project could not be found")
    return project["id"], project["items"]["nodes"]


def add_draft(token: str, project_id: str, title: str, body: str) -> None:
    mutation = """
    mutation($projectId: ID!, $title: String!, $body: String!) {
      addProjectV2DraftIssue(input: {projectId: $projectId, title: $title, body: $body}) {
        projectItem { id }
      }
    }
    """
    graphql(token, mutation, {"projectId": project_id, "title": title, "body": body})


def update_draft(token: str, draft_id: str, title: str, body: str) -> None:
    mutation = """
    mutation($draftId: ID!, $title: String!, $body: String!) {
      updateProjectV2DraftIssue(input: {draftIssueId: $draftId, title: $title, body: $body}) {
        draftIssue { id }
      }
    }
    """
    graphql(token, mutation, {"draftId": draft_id, "title": title, "body": body})


def main() -> None:
    token = os.environ.get("PROJECT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PROJECT_TOKEN must be configured")

    binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    projects = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["projects"]
    project_id, items = get_project(token, binding["owner"], int(binding["number"]))

    existing: dict[str, dict[str, Any]] = {}
    for item in items:
        content = item.get("content") or {}
        body = content.get("body") or ""
        if not body.startswith(MARKER_PREFIX):
            continue
        marker = body.split("-->", 1)[0]
        project_key = marker.removeprefix(MARKER_PREFIX).strip()
        existing[project_key] = content

    created = 0
    updated = 0
    for project in projects:
        title = project["name"]
        body = project_body(project)
        current = existing.get(project["id"])
        if current is None:
            add_draft(token, project_id, title, body)
            created += 1
        elif current.get("title") != title or current.get("body") != body:
            update_draft(token, current["id"], title, body)
            updated += 1

    print(f"Synced {len(projects)} projects: created={created}, updated={updated}")


if __name__ == "__main__":
    main()
