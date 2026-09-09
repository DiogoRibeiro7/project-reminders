"""Board synchronization delta tests."""

from project_reminders.application.board_delta import (
    body_with_last_activity,
    needs_card_sync,
)


def test_last_activity_participates_in_card_fingerprint() -> None:
    first = body_with_last_activity("body", "2026-09-09T10:00:00Z")
    second = body_with_last_activity("body", "2026-09-09T11:00:00Z")

    assert first != second
    assert needs_card_sync(first, second)


def test_identical_body_and_activity_skip_sync() -> None:
    desired = body_with_last_activity("body", "—")

    assert not needs_card_sync(desired, desired)
