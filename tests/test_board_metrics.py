"""Board metric projection tests."""

from project_reminders.application.board_metrics import activity_date, health_score


def test_health_score_counts_complete_and_not_applicable_states() -> None:
    project = {
        "health": {
            "tests": "complete",
            "typing": "missing",
            "lint": "not_applicable",
            "ci": "partial",
        }
    }

    assert health_score(project) == 2


def test_activity_date_uses_repository_activity_timestamp() -> None:
    project = {"operational": {"latest_activity_at": "2026-09-09T21:15:52+00:00"}}

    assert activity_date(project) == "2026-09-09"


def test_activity_date_is_empty_when_repository_activity_is_unobserved() -> None:
    assert activity_date({"operational": {"latest_activity_at": None}}) is None
