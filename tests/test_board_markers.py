"""Board marker compatibility and duplicate-selection tests."""

import pytest

from project_reminders.application.board_markers import (
    MarkerGeneration,
    legacy_duplicate_item_ids,
    parse_managed_marker,
)


def _item(item_id: str, body: str) -> dict[str, object]:
    return {
        "id": item_id,
        "content": {"__typename": "DraftIssue", "body": body},
    }


def test_parse_managed_marker_accepts_current_and_legacy_formats() -> None:
    current = parse_managed_marker("<!-- project-reminders:id=alpha -->\nbody")
    legacy = parse_managed_marker("<!-- project-reminders-id:alpha -->\nbody")

    assert current is not None
    assert legacy is not None
    assert current.project_id == "alpha"
    assert legacy.project_id == "alpha"
    assert current.generation is MarkerGeneration.CURRENT
    assert legacy.generation is MarkerGeneration.LEGACY


def test_legacy_duplicate_is_selected_only_with_current_replacement() -> None:
    items: list[object] = [
        _item("current-alpha", "<!-- project-reminders:id=alpha -->"),
        _item("legacy-alpha", "<!-- project-reminders-id:alpha -->"),
        _item("legacy-beta", "<!-- project-reminders-id:beta -->"),
    ]

    duplicate_ids = legacy_duplicate_item_ids(items, frozenset({"alpha", "beta"}))

    assert duplicate_ids == ("legacy-alpha",)


def test_multiple_current_cards_fail_closed() -> None:
    items: list[object] = [
        _item("current-one", "<!-- project-reminders:id=alpha -->"),
        _item("current-two", "<!-- project-reminders:id=alpha -->"),
        _item("legacy", "<!-- project-reminders-id:alpha -->"),
    ]

    with pytest.raises(ValueError, match="multiple current-format cards"):
        legacy_duplicate_item_ids(items, frozenset({"alpha"}))
