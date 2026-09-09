"""Derived values exposed as GitHub Project fields."""

from __future__ import annotations

from typing import Any

from project_reminders.application.dashboard import build_project_card
from project_reminders.domain.models import Project

JsonObject = dict[str, Any]


def health_score(project: JsonObject) -> int:
    """Count engineering dimensions satisfied by complete or not-applicable state."""

    health = project.get("health")
    if not isinstance(health, dict):
        return 0
    satisfied = {"complete", "not_applicable"}
    return sum(1 for state in health.values() if state in satisfied)


def activity_date(project: JsonObject) -> str | None:
    """Return the observed repository activity date in ISO calendar form."""

    operational = project.get("operational")
    if not isinstance(operational, dict):
        return None
    value = operational.get("latest_activity_at")
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def attention_metrics(project: Project) -> tuple[int, int]:
    """Return the dashboard's exact attention score and reason count."""

    card = build_project_card(project)
    return card.attention_score, len(card.reasons)
