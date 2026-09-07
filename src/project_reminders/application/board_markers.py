"""Compatibility helpers for managed GitHub Project card markers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

CURRENT_MARKER_PREFIX = "<!-- project-reminders:id="
LEGACY_MARKER_PREFIX = "<!-- project-reminders-id:"
MARKER_SUFFIX = " -->"


class MarkerGeneration(StrEnum):
    """Known managed-card marker generations."""

    CURRENT = "current"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True)
class ManagedMarker:
    """Parsed stable project identity from one managed draft card."""

    project_id: str
    generation: MarkerGeneration


def parse_managed_marker(body: str) -> ManagedMarker | None:
    """Read either the current or legacy marker from a draft-card body."""

    prefixes = (
        (CURRENT_MARKER_PREFIX, MarkerGeneration.CURRENT),
        (LEGACY_MARKER_PREFIX, MarkerGeneration.LEGACY),
    )
    for line in body.splitlines():
        stripped = line.strip()
        for prefix, generation in prefixes:
            if not stripped.startswith(prefix) or not stripped.endswith(MARKER_SUFFIX):
                continue
            project_id = stripped[len(prefix) : -len(MARKER_SUFFIX)].strip()
            if project_id:
                return ManagedMarker(project_id=project_id, generation=generation)
    return None


def legacy_duplicate_item_ids(
    items: list[object], tracked_ids: frozenset[str]
) -> tuple[str, ...]:
    """Return legacy item IDs that have an unambiguous current-format replacement."""

    current: dict[str, list[str]] = {}
    legacy: dict[str, list[str]] = {}
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
        if marker is None or marker.project_id not in tracked_ids:
            continue
        target = current if marker.generation is MarkerGeneration.CURRENT else legacy
        target.setdefault(marker.project_id, []).append(item_id)

    duplicates: list[str] = []
    for project_id in sorted(tracked_ids):
        current_items = current.get(project_id, [])
        if len(current_items) > 1:
            raise ValueError(f"multiple current-format cards found for {project_id}")
        if len(current_items) == 1:
            duplicates.extend(legacy.get(project_id, []))
    return tuple(duplicates)
