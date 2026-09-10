"""Derived GitHub Project metric field transport helpers."""

from __future__ import annotations

from typing import Any

from scripts.sync_project_board import GraphQLClient

JsonObject = dict[str, Any]
FIELD_SPECS = (
    ("Health score", "NUMBER"),
    ("Activity date", "DATE"),
    ("Attention", "NUMBER"),
    ("Attention reasons", "NUMBER"),
)


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


def ensure_metric_fields(
    client: GraphQLClient,
    board: JsonObject,
) -> dict[str, JsonObject]:
    """Ensure all derived metric fields exist with the expected data types."""

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


def current_metric_values(item: JsonObject) -> dict[str, int | str | None]:
    """Read the current derived metric values from one Project item snapshot."""

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


def sync_metric_values(
    client: GraphQLClient,
    project_id: str,
    item_id: str,
    fields: dict[str, JsonObject],
    current: dict[str, int | str | None],
    desired: dict[str, int | str | None],
) -> bool:
    """Write all changed derived metrics in at most one GraphQL mutation."""

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
