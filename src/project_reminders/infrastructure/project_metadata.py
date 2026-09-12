"""Load and validate repository-local `.project.json` metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from project_reminders.domain.metadata import (
    AcceptanceCriterion,
    Dependency,
    DependencyKind,
    Milestone,
    MilestoneStatus,
    Outcome,
    OutcomeStatus,
    OutcomeType,
    PlanningHorizon,
    ProjectMetadata,
    ProjectType,
)

JsonObject = dict[str, Any]


def _object(value: object, field_name: str) -> JsonObject:
    """Return a validated JSON object or raise a useful type error."""

    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    return cast(JsonObject, value)


def _list(value: object, field_name: str) -> list[object]:
    """Return a validated JSON list or raise a useful type error."""

    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be an array")
    return cast(list[object], value)


def _string(value: object, field_name: str) -> str:
    """Return a validated JSON string or raise a useful type error."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _boolean(value: object, field_name: str) -> bool:
    """Return a validated JSON boolean or raise a useful type error."""

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def _integer(value: object, field_name: str) -> int:
    """Return a JSON integer while rejecting booleans, which subclass int in Python."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _reject_unknown(record: JsonObject, allowed: set[str], field_name: str) -> None:
    """Reject misspelled or unsupported keys instead of silently ignoring them."""

    unknown = sorted(set(record) - allowed)
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(f"{field_name} contains unknown field(s): {names}")


def project_metadata_from_record(raw: object) -> ProjectMetadata:
    """Parse one JSON-compatible object into validated project metadata."""

    record = _object(raw, "project metadata")
    _reject_unknown(
        record,
        {
            "schema_version",
            "project_type",
            "strategic_themes",
            "planning",
            "milestone",
            "dependencies",
            "outcomes",
        },
        "project metadata",
    )

    planning = _object(record.get("planning", {}), "planning")
    _reject_unknown(planning, {"horizon", "wip"}, "planning")

    milestone_raw = record.get("milestone")
    milestone: Milestone | None = None
    if milestone_raw is not None:
        milestone_record = _object(milestone_raw, "milestone")
        _reject_unknown(milestone_record, {"id", "title", "status", "acceptance"}, "milestone")
        acceptance: list[AcceptanceCriterion] = []
        for index, item in enumerate(_list(milestone_record.get("acceptance", []), "acceptance")):
            criterion = _object(item, f"acceptance[{index}]")
            _reject_unknown(criterion, {"id", "text", "done"}, f"acceptance[{index}]")
            acceptance.append(
                AcceptanceCriterion(
                    id=_string(criterion.get("id"), f"acceptance[{index}].id"),
                    text=_string(criterion.get("text"), f"acceptance[{index}].text"),
                    done=_boolean(criterion.get("done", False), f"acceptance[{index}].done"),
                )
            )
        milestone = Milestone(
            id=_string(milestone_record.get("id"), "milestone.id"),
            title=_string(milestone_record.get("title"), "milestone.title"),
            status=MilestoneStatus(_string(milestone_record.get("status"), "milestone.status")),
            acceptance=tuple(acceptance),
        )

    dependencies: list[Dependency] = []
    for index, item in enumerate(_list(record.get("dependencies", []), "dependencies")):
        dependency = _object(item, f"dependencies[{index}]")
        _reject_unknown(dependency, {"kind", "target"}, f"dependencies[{index}]")
        dependencies.append(
            Dependency(
                kind=DependencyKind(
                    _string(dependency.get("kind"), f"dependencies[{index}].kind")
                ),
                target=_string(dependency.get("target"), f"dependencies[{index}].target"),
            )
        )

    outcomes: list[Outcome] = []
    for index, item in enumerate(_list(record.get("outcomes", []), "outcomes")):
        outcome = _object(item, f"outcomes[{index}]")
        _reject_unknown(outcome, {"id", "type", "status", "target"}, f"outcomes[{index}]")
        outcomes.append(
            Outcome(
                id=_string(outcome.get("id"), f"outcomes[{index}].id"),
                type=OutcomeType(_string(outcome.get("type"), f"outcomes[{index}].type")),
                status=OutcomeStatus(
                    _string(outcome.get("status"), f"outcomes[{index}].status")
                ),
                target=_string(outcome.get("target"), f"outcomes[{index}].target"),
            )
        )

    themes = tuple(
        _string(item, f"strategic_themes[{index}]")
        for index, item in enumerate(_list(record.get("strategic_themes", []), "strategic_themes"))
    )

    return ProjectMetadata(
        schema_version=_integer(record.get("schema_version", 1), "schema_version"),
        project_type=ProjectType(_string(record.get("project_type"), "project_type")),
        strategic_themes=themes,
        planning_horizon=PlanningHorizon(
            _string(planning.get("horizon", PlanningHorizon.LATER.value), "planning.horizon")
        ),
        wip=_boolean(planning.get("wip", False), "planning.wip"),
        milestone=milestone,
        dependencies=tuple(dependencies),
        outcomes=tuple(outcomes),
    )


def load_project_metadata(path: Path) -> ProjectMetadata:
    """Load and validate one `.project.json` file from disk."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return project_metadata_from_record(raw)
