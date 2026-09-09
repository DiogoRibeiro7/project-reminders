"""Ensure Project #16 can represent the unclassified lifecycle state."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def main() -> int:
    """Add the unclassified option if the Lifecycle field does not have it."""

    root = Path(os.environ.get("PROJECT_REMINDERS_ROOT", Path.cwd()))
    token = os.environ.get("PROJECT_TOKEN", "")
    try:
        binding = _load_json(root / "data" / "github_project.json")
        query = """
        query($login: String!, $number: Int!) {
          user(login: $login) {
            projectV2(number: $number) {
              fields(first: 100) {
                nodes {
                  __typename
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
        data = _graphql(
            token,
            query,
            {"login": str(binding["owner"]), "number": int(binding["number"])},
        )
        user = data.get("user")
        if not isinstance(user, dict):
            raise RuntimeError("GitHub user was not found")
        project = user.get("projectV2")
        if not isinstance(project, dict):
            raise RuntimeError("configured GitHub Project was not found")
        fields_connection = project.get("fields")
        nodes = fields_connection.get("nodes") if isinstance(fields_connection, dict) else None
        if not isinstance(nodes, list):
            raise RuntimeError("GitHub Project fields were not returned")
        lifecycle = next(
            (
                field
                for field in nodes
                if isinstance(field, dict)
                and field.get("__typename") == "ProjectV2SingleSelectField"
                and field.get("name") == "Lifecycle"
            ),
            None,
        )
        if not isinstance(lifecycle, dict):
            raise RuntimeError("Lifecycle field was not found")
        raw_options = lifecycle.get("options")
        options = [option for option in raw_options if isinstance(option, dict)] if isinstance(raw_options, list) else []
        if any(option.get("name") == "unclassified" for option in options):
            print("Lifecycle option unclassified already exists")
            return 0
        updated_options: list[JsonObject] = [
            {
                "id": option.get("id"),
                "name": str(option.get("name", "")),
                "color": str(option.get("color", "GRAY")),
                "description": str(option.get("description") or ""),
            }
            for option in options
        ]
        updated_options.insert(
            0,
            {
                "name": "unclassified",
                "color": "GRAY",
                "description": "Discovered repository awaiting lifecycle classification",
            },
        )
        mutation = """
        mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
          updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) {
            projectV2Field { ... on ProjectV2SingleSelectField { id name } }
          }
        }
        """
        _graphql(token, mutation, {"field": lifecycle["id"], "options": updated_options})
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("Added Lifecycle option: unclassified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
