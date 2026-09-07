"""Portfolio history and trend tests."""

from datetime import UTC, datetime

from project_reminders.application.history import ChangeDirection, compare_portfolios
from project_reminders.domain.enums import CIState, HealthDimension, HealthState
from project_reminders.domain.models import EngineeringHealth, OperationalSnapshot, Portfolio, Project


def test_history_classifies_clear_improvement_and_degradation() -> None:
    before = Project(
        id="one",
        name="One",
        repository="owner/one",
        health=EngineeringHealth({HealthDimension.LINT: HealthState.MISSING}),
        operational=OperationalSnapshot(ci_state=CIState.FAILING),
    )
    after = Project(
        id="one",
        name="One",
        repository="owner/one",
        health=EngineeringHealth({HealthDimension.LINT: HealthState.COMPLETE}),
        operational=OperationalSnapshot(ci_state=CIState.PASSING),
    )

    history = compare_portfolios(Portfolio(projects=(before,)), Portfolio(projects=(after,)))

    assert history.improved_count == 2
    assert history.degraded_count == 0
    assert {change.message for change in history.changes} == {
        "CI: failing → passing",
        "lint: missing → complete",
    }


def test_unknown_health_transition_stays_directionally_neutral() -> None:
    before = Project(id="one", name="One", repository="owner/one")
    after = Project(
        id="one",
        name="One",
        repository="owner/one",
        health=EngineeringHealth({HealthDimension.TYPING: HealthState.MISSING}),
    )

    history = compare_portfolios(Portfolio(projects=(before,)), Portfolio(projects=(after,)))

    assert history.changes[0].direction is ChangeDirection.CHANGED


def test_history_preserves_previous_snapshot_timestamp_and_project_filter() -> None:
    previous_at = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)
    before = Project(id="one", name="One", repository="owner/one")
    after = Project(
        id="one",
        name="One",
        repository="owner/one",
        operational=OperationalSnapshot(ci_state=CIState.FAILING),
    )

    history = compare_portfolios(
        Portfolio(projects=(before,), generated_at=previous_at),
        Portfolio(projects=(after,)),
    )

    assert history.previous_generated_at == previous_at
    assert history.for_project("one") == history.changes
    assert history.for_project("other") == ()
