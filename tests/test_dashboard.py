"""Attention-ranking tests."""

from project_reminders.application.dashboard import build_dashboard
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.domain.models import EngineeringHealth, NextAction, Portfolio, Project


def test_active_project_without_next_action_needs_attention() -> None:
    project = Project(
        id="one",
        name="One",
        repository="owner/one",
        status=ProjectStatus.ACTIVE_DEVELOPMENT,
    )

    dashboard = build_dashboard(Portfolio(projects=(project,)))

    assert dashboard.attention_count == 1
    assert "no next action" in dashboard.cards[0].reasons[0].casefold()


def test_explicit_missing_health_ranks_above_unknown_health() -> None:
    healthy_unknown = Project(
        id="unknown",
        name="Unknown",
        repository="owner/unknown",
        status=ProjectStatus.HARDENING,
        priority=Priority.MEDIUM,
        next_action=NextAction("Continue"),
    )
    missing_tests = Project(
        id="missing",
        name="Missing",
        repository="owner/missing",
        status=ProjectStatus.HARDENING,
        priority=Priority.MEDIUM,
        next_action=NextAction("Continue"),
        health=EngineeringHealth({HealthDimension.TESTS: HealthState.MISSING}),
    )

    dashboard = build_dashboard(Portfolio(projects=(healthy_unknown, missing_tests)))

    assert dashboard.cards[0].project.id == "missing"
    assert dashboard.attention_count == 1
