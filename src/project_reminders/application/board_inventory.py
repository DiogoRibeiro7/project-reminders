"""Pure helpers for reconciling managed GitHub Project cards."""

from __future__ import annotations

from dataclasses import dataclass

from project_reminders.application.board_markers import parse_managed_marker


@dataclass(frozen=True, slots=True)
class ManagedBoardInventory:
    """Canonical managed cards plus duplicate item IDs to archive."""

    canonical: dict[str, dict[str, object]]
    duplicate_item_ids: tuple[str, ...]


def reconcile_managed_items(items: list[object]) -> ManagedBoardInventory:
    """Keep one active card per managed project ID and identify all extras."""

    canonical: dict[str, dict[str, object]] = {}
    duplicates: list[str] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item_id = raw_item.get("id")
        content = raw_item.get("content")
        if not isinstance(item_id, str) or not isinstance(content, dict):
            continue
        if content.get("__typename") != "DraftIssue":
            continue
        marker = parse_managed_marker(str(content.get("body") or ""))
        if marker is None:
            continue

        existing = canonical.get(marker.project_id)
        if existing is None:
            canonical[marker.project_id] = raw_item
        else:
            duplicates.append(item_id)

    return ManagedBoardInventory(
        canonical=canonical,
        duplicate_item_ids=tuple(duplicates),
    )
