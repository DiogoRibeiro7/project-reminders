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
    ]
    assert len(names) == len(set(names))
    assert {spec.layout for spec in MANAGED_VIEW_SPECS} == {"table", "board"}


def test_lifecycle_board_groups_by_lifecycle() -> None:
    board = next(spec for spec in MANAGED_VIEW_SPECS if spec.name == "Lifecycle Board")

    assert board.layout == "board"
    assert board.vertical_group_by == ("Lifecycle",)
    assert "archived" in board.filter_query
    assert "abandoned" in board.filter_query


def test_missing_views_are_case_insensitive_and_ordered() -> None:
    missing = missing_view_specs({"portfolio", "CI Problems"})

    assert [spec.name for spec in missing] == [
        "Lifecycle Board",
        "Needs Classification",
        "Open PRs",
        "Portfolio Ready",
    ]
