"""Repository-local project metadata contract tests."""

import pytest

from project_reminders.domain.metadata import MilestoneStatus, PlanningHorizon, ProjectType
from project_reminders.infrastructure.project_metadata import project_metadata_from_record


def _valid_record() -> dict[str, object]:
    """Return one valid metadata record for focused mutation in tests."""

    return {
        "schema_version": 1,
        "project_type": "research",
        "strategic_themes": ["mathematical-research"],
        "planning": {"horizon": "now", "wip": True},
        "milestone": {
            "id": "M04",
            "title": "Complete identifiability analysis",
            "status": "wip",
            "acceptance": [
                {"id": "A1", "text": "Derive weak-identification condition", "done": True},
                {"id": "A2", "text": "Produce curvature map", "done": False},
            ],
        },
        "dependencies": [{"kind": "soft", "target": "breakinfer:M05"}],
        "outcomes": [
            {
                "id": "O1",
                "type": "paper",
                "status": "in_progress",
                "target": "submission candidate",
            }
        ],
    }


def test_metadata_parses_valid_contract() -> None:
    metadata = project_metadata_from_record(_valid_record())

    assert metadata.project_type is ProjectType.RESEARCH
    assert metadata.planning_horizon is PlanningHorizon.NOW
    assert metadata.wip is True
    assert metadata.milestone is not None
    assert metadata.milestone.status is MilestoneStatus.WIP
    assert metadata.milestone.acceptance[1].done is False


def test_now_requires_wip() -> None:
    record = _valid_record()
    record["planning"] = {"horizon": "now", "wip": False}
    record["milestone"] = {
        "id": "M04",
        "title": "Complete identifiability analysis",
        "status": "ready",
    }

    with pytest.raises(ValueError, match="now.*wip=true"):
        project_metadata_from_record(record)


def test_finishing_requires_acceptance_complete() -> None:
    record = _valid_record()
    milestone = record["milestone"]
    assert isinstance(milestone, dict)
    milestone["status"] = "finishing"

    with pytest.raises(ValueError, match="all acceptance criteria"):
        project_metadata_from_record(record)


def test_wip_requires_current_milestone() -> None:
    record = _valid_record()
    record.pop("milestone")

    with pytest.raises(ValueError, match="require a current milestone"):
        project_metadata_from_record(record)


def test_unknown_fields_are_rejected() -> None:
    record = _valid_record()
    record["mystery"] = "silently accepting this would hide schema drift"

    with pytest.raises(ValueError, match="unknown field.*mystery"):
        project_metadata_from_record(record)


def test_boolean_is_not_accepted_as_schema_version() -> None:
    record = _valid_record()
    record["schema_version"] = True

    with pytest.raises(TypeError, match="schema_version must be an integer"):
        project_metadata_from_record(record)
