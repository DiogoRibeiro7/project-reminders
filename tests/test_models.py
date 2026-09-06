"""Domain-model regression tests."""

from datetime import datetime

import pytest

from project_reminders.domain.enums import HealthDimension, HealthState
from project_reminders.domain.models import EngineeringHealth, NextAction, Project


def test_unknown_health_is_not_treated_as_missing() -> None:
    health = EngineeringHealth()

    assert health.state_for(HealthDimension.TESTS) is HealthState.UNKNOWN
    assert health.missing_dimensions == ()


def test_health_update_is_immutable() -> None:
    health = EngineeringHealth()
    updated = health.with_state(HealthDimension.TESTS, HealthState.COMPLETE)

    assert health.state_for(HealthDimension.TESTS) is HealthState.UNKNOWN
    assert updated.state_for(HealthDimension.TESTS) is HealthState.COMPLETE


def test_project_requires_owner_name_repository() -> None:
    with pytest.raises(ValueError, match="owner/name"):
        Project(id="abc", name="Broken", repository="broken")


def test_next_action_rejects_naive_deadline() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        NextAction("Ship it", due_at=datetime(2026, 9, 6, 12, 0))
