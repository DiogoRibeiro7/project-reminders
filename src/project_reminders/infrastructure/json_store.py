"""Plain JSON persistence for the project portfolio."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from project_reminders.domain.enums import (
    CIState,
    HealthDimension,
    HealthState,
    Priority,
    ProjectStatus,
)
from project_reminders.domain.models import (
    EngineeringHealth,
    NextAction,
    OperationalSnapshot,
    Portfolio,
    Project,
    PullRequestSnapshot,
)

JsonObject = dict[str, Any]


def _parse_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or null")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _operational_from_record(raw: object) -> OperationalSnapshot:
    if raw is None:
        return OperationalSnapshot()
    if not isinstance(raw, dict):
        raise TypeError("operational must be an object")
    record = cast(JsonObject, raw)
    prs_raw = record.get("open_pull_requests", [])
    if not isinstance(prs_raw, list):
        raise TypeError("open_pull_requests must be a list")
    pull_requests: list[PullRequestSnapshot] = []
    for item in prs_raw:
        if not isinstance(item, dict):
            raise TypeError("pull request entries must be objects")
        pr = cast(JsonObject, item)
        pull_requests.append(
            PullRequestSnapshot(
                number=int(pr["number"]),
                title=str(pr.get("title", "")),
                draft=bool(pr.get("draft", False)),
                updated_at=_parse_datetime(pr.get("updated_at"), "pull_request.updated_at"),
            )
        )
    return OperationalSnapshot(
        open_pull_requests=tuple(pull_requests),
        ci_state=CIState(str(record.get("ci_state", CIState.UNKNOWN.value))),
        latest_activity_at=_parse_datetime(record.get("latest_activity_at"), "latest_activity_at"),
        latest_release=str(record["latest_release"])
        if record.get("latest_release") is not None
        else None,
        latest_release_at=_parse_datetime(record.get("latest_release_at"), "latest_release_at"),
        latest_tag=str(record["latest_tag"]) if record.get("latest_tag") is not None else None,
        observed_at=_parse_datetime(record.get("observed_at"), "observed_at"),
    )


def _project_from_record(raw: object) -> Project:
    if not isinstance(raw, dict):
        raise TypeError("project entries must be objects")
    record = cast(JsonObject, raw)
    action_raw = record.get("next_action")
    action: NextAction | None = None
    if action_raw is not None:
        if not isinstance(action_raw, dict):
            raise TypeError("next_action must be an object or null")
        action_record = cast(JsonObject, action_raw)
        action = NextAction(
            description=str(action_record["description"]),
            due_at=_parse_datetime(action_record.get("due_at"), "next_action.due_at"),
        )
    health_raw = record.get("health", {})
    if not isinstance(health_raw, dict):
        raise TypeError("health must be an object")
    health_record = cast(JsonObject, health_raw)
    health = EngineeringHealth(
        {HealthDimension(str(key)): HealthState(str(value)) for key, value in health_record.items()}
    )
    tags_raw = record.get("tags", [])
    if not isinstance(tags_raw, list) or not all(isinstance(tag, str) for tag in tags_raw):
        raise TypeError("tags must be a list of strings")
    current_pr_raw = record.get("current_pr")
    if current_pr_raw is not None and not isinstance(current_pr_raw, int):
        raise TypeError("current_pr must be an integer or null")
    return Project(
        id=str(record["id"]),
        name=str(record["name"]),
        repository=str(record["repository"]),
        status=ProjectStatus(str(record.get("status", ProjectStatus.IDEA.value))),
        priority=Priority(str(record.get("priority", Priority.MEDIUM.value))),
        summary=str(record.get("summary", "")),
        next_action=action,
        blocker=str(record["blocker"]) if record.get("blocker") is not None else None,
        tags=tuple(cast(list[str], tags_raw)),
        health=health,
        operational=_operational_from_record(record.get("operational")),
        current_pr=current_pr_raw,
        created_at=_parse_datetime(record.get("created_at"), "created_at"),
        updated_at=_parse_datetime(record.get("updated_at"), "updated_at"),
        last_repository_activity_at=_parse_datetime(
            record.get("last_repository_activity_at"), "last_repository_activity_at"
        ),
    )


def _operational_to_record(snapshot: OperationalSnapshot) -> JsonObject:
    return {
        "open_pull_requests": [
            {
                "number": pr.number,
                "title": pr.title,
                "draft": pr.draft,
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
            }
            for pr in snapshot.open_pull_requests
        ],
        "ci_state": snapshot.ci_state.value,
        "latest_activity_at": snapshot.latest_activity_at.isoformat()
        if snapshot.latest_activity_at
        else None,
        "latest_release": snapshot.latest_release,
        "latest_release_at": snapshot.latest_release_at.isoformat()
        if snapshot.latest_release_at
        else None,
        "latest_tag": snapshot.latest_tag,
        "observed_at": snapshot.observed_at.isoformat() if snapshot.observed_at else None,
    }


def _project_to_record(project: Project) -> JsonObject:
    action = None
    if project.next_action is not None:
        action = {
            "description": project.next_action.description,
            "due_at": project.next_action.due_at.isoformat()
            if project.next_action.due_at
            else None,
        }
    return {
        "id": project.id,
        "name": project.name,
        "repository": project.repository,
        "status": project.status.value,
        "priority": project.priority.value,
        "summary": project.summary,
        "next_action": action,
        "blocker": project.blocker,
        "tags": list(project.tags),
        "health": {
            dimension.value: state.value for dimension, state in project.health.states.items()
        },
        "operational": _operational_to_record(project.operational),
        "current_pr": project.current_pr,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "last_repository_activity_at": project.last_repository_activity_at.isoformat()
        if project.last_repository_activity_at
        else None,
    }


class JsonPortfolioRepository:
    """Atomically persist the portfolio in one readable JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Portfolio:
        if not self.path.exists():
            return Portfolio()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("portfolio root must be an object")
        record = cast(JsonObject, raw)
        projects_raw = record.get("projects", [])
        if not isinstance(projects_raw, list):
            raise TypeError("projects must be a list")
        return Portfolio(
            projects=tuple(_project_from_record(project) for project in projects_raw),
            version=int(record.get("version", 1)),
            generated_at=_parse_datetime(record.get("generated_at"), "generated_at"),
        )

    def save(self, portfolio: Portfolio) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: JsonObject = {
            "version": portfolio.version,
            "generated_at": portfolio.generated_at.isoformat() if portfolio.generated_at else None,
            "projects": [
                _project_to_record(project)
                for project in sorted(portfolio.projects, key=lambda item: item.name.casefold())
            ],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
