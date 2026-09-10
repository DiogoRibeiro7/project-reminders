"""Managed GitHub Project view specification tests."""

from project_reminders.application.project_views import MANAGED_VIEW_SPECS, missing_view_specs


def test_managed_views_cover_distinct_portfolio_questions() -> None:
    names = [spec.name for spec in MANAGED_VIEW_SPECS]

    assert names == [
        "Portfolio",
        "Lifecycle Board",
        "Needs Classification",
        "CI Problems",
        "Open PRs",
        "Portfolio Ready",
        "Active Work",
        "High Priority",
        "Maintenance",
        "Engineering Gaps",
        "Quiet 30d",
        "Attention Queue",
    ]
    assert len(names) == len(set(names))
    assert {spec.layout for spec in MANAGED_VIEW_SPECS} == {"table", "board"}


def test_lifecycle_board_groups_by_lifecycle() -> None:
    board = next(spec for spec in MANAGED_VIEW_SPECS if spec.name == "Lifecycle Board")

    assert board.layout == "board"
    assert board.vertical_group_by == ("Lifecycle",)
    assert "archived" in board.filter_query
    assert "abandoned" in board.filter_query


def test_operational_views_use_typed_metrics() -> None:
    engineering = next(spec for spec in MANAGED_VIEW_SPECS if spec.name == "Engineering Gaps")
    quiet = next(spec for spec in MANAGED_VIEW_SPECS if spec.name == "Quiet 30d")
    attention = next(spec for spec in MANAGED_VIEW_SPECS if spec.name == "Attention Queue")

    assert "health-score:<10" in engineering.filter_query
    assert "Health score" in engineering.visible_fields
    assert "activity-date:<@today-30d" in quiet.filter_query
    assert "Activity date" in quiet.visible_fields
    assert "attention-reasons:>0" in attention.filter_query
    assert attention.sort_by[0] == ("Attention", "desc")


def test_missing_views_are_case_insensitive_and_ordered() -> None:
    missing = missing_view_specs({"portfolio", "CI Problems", "attention queue"})

    assert [spec.name for spec in missing] == [
        "Lifecycle Board",
        "Needs Classification",
        "Open PRs",
        "Portfolio Ready",
        "Active Work",
        "High Priority",
        "Maintenance",
        "Engineering Gaps",
        "Quiet 30d",
    ]
