"""Managed board inventory reconciliation tests."""

from project_reminders.application.board_inventory import reconcile_managed_items


def _item(item_id: str, project_id: str) -> dict[str, object]:
    return {
        "id": item_id,
        "content": {
            "__typename": "DraftIssue",
            "body": f"<!-- project-reminders:id={project_id} -->\n",
        },
    }


def test_reconcile_keeps_one_card_per_project_and_marks_extras() -> None:
    inventory = reconcile_managed_items(
        [
            _item("item-a", "alpha"),
            _item("item-b", "beta"),
            _item("item-a-duplicate", "alpha"),
        ]
    )

    assert sorted(inventory.canonical) == ["alpha", "beta"]
    assert inventory.canonical["alpha"]["id"] == "item-a"
    assert inventory.duplicate_item_ids == ("item-a-duplicate",)


def test_reconcile_ignores_unmanaged_and_non_draft_items() -> None:
    inventory = reconcile_managed_items(
        [
            {"id": "note", "content": {"__typename": "DraftIssue", "body": "manual"}},
            {"id": "issue", "content": {"__typename": "Issue", "body": ""}},
            _item("managed", "alpha"),
        ]
    )

    assert list(inventory.canonical) == ["alpha"]
    assert inventory.duplicate_item_ids == ()
