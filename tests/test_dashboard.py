"""Attention-ranking and portfolio KPI tests."""

from project_reminders.application.dashboard import build_dashboard
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


def test_active_project_without_next_action_needs_attention() -> None:
    project = Project(
        id="one",
        name="One",
        repository="owner/one",
        status=ProjectStatus.ACTIVE_DEVELOPMENT,
    )

    dashboard = build_dashboard(Portfolio(projects=(project,)))

    assert dashboard.attention_count == 1
    assert dashboard.missing_next_action_count == 1
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


def test_dashboard_aggregates_live_portfolio_metrics() -> None:
    failing = Project(
        id="failing",
        name="Failing",
        repository="owner/failing",
        status=ProjectStatus.HARDENING,
        priority=Priority.HIGH,
        next_action=NextAction("Repair CI"),
        blocker="Waiting for credentials",
        operational=OperationalSnapshot(
            ci_state=CIState.FAILING,
            open_pull_requests=(
                PullRequestSnapshot(number=1, title="One", draft=False),
                PullRequestSnapshot(number=2, title="Two", draft=True),
            ),
        ),
    )
    pending = Project(
        id="pending",
        name="Pending",
        repository="owner/pending",
        status=ProjectStatus.ACTIVE_DEVELOPMENT,
        operational=OperationalSnapshot(ci_state=CIState.PENDING),
    )

    dashboard = build_dashboard(Portfolio(projects=(failing, pending)))

    assert dashboard.total_count == 2
    assert dashboard.failing_ci_count == 1
    assert dashboard.pending_ci_count == 1
    assert dashboard.open_pr_count == 2
    assert dashboard.blocked_count == 1
    assert dashboard.missing_next_action_count == 1
    assert dashboard.attention_queue[0].project.id == "failing"
