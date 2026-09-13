"""Persistence for the derived repository-local metadata inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from project_reminders.domain.metadata import (
    MilestoneSnapshot,
    MilestoneStatus,
    PlanningHorizon,
    ProjectMetadataSnapshot,
    ProjectType,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class MetadataInventory:
    """Current repository-local metadata migration inventory."""

    migrated: dict[str, ProjectMetadataSnapshot]
    missing: frozenset[str]
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError(f"unsupported metadata inventory version: {self.version}")

    def snapshot_for(self, repository: str) -> ProjectMetadataSnapshot | None:
        """Return the migrated snapshot for one repository, when present."""

        key = repository.casefold()
        return next(
            (
                snapshot
                for name, snapshot in self.migrated.items()
                if name.casefold() == key
            ),
            None,
        )

    def migration_status(self, repository: str) -> str:
        """Return migrated, missing, or unknown for one repository."""

        if self.snapshot_for(repository) is not None:
            return "migrated"
        key = repository.casefold()
        if any(name.casefold() == key for name in self.missing):
            return "missing"
        return "unknown"


def _snapshot_record(snapshot: ProjectMetadataSnapshot) -> dict[str, object]:
    milestone: dict[str, object] | None = None
    if snapshot.milestone is not None:
        milestone = {
            "id": snapshot.milestone.id,
            "title": snapshot.milestone.title,
            "status": snapshot.milestone.status.value,
            "acceptance_done": snapshot.milestone.acceptance_done,
            "acceptance_total": snapshot.milestone.acceptance_total,
        }
    return {
        "schema_version": snapshot.schema_version,
        "project_type": snapshot.project_type.value,
        "strategic_themes": list(snapshot.strategic_themes),
        "planning_horizon": snapshot.planning_horizon.value,
        "wip": snapshot.wip,
        "milestone": milestone,
        "dependency_count": snapshot.dependency_count,
        "outcome_count": snapshot.outcome_count,
    }


def _snapshot_from_record(raw: object) -> ProjectMetadataSnapshot:
    if not isinstance(raw, dict):
        raise TypeError("metadata snapshot must be an object")
    record = cast(JsonObject, raw)
    themes_raw = record.get("strategic_themes", [])
    if not isinstance(themes_raw, list) or not all(isinstance(item, str) for item in themes_raw):
        raise TypeError("strategic_themes must be a list of strings")

    milestone_raw = record.get("milestone")
    milestone: MilestoneSnapshot | None = None
    if milestone_raw is not None:
        if not isinstance(milestone_raw, dict):
            raise TypeError("milestone must be an object or null")
        milestone_record = cast(JsonObject, milestone_raw)
        milestone = MilestoneSnapshot(
            id=str(milestone_record["id"]),
            title=str(milestone_record["title"]),
            status=MilestoneStatus(str(milestone_record["status"])),
            acceptance_done=int(milestone_record.get("acceptance_done", 0)),
            acceptance_total=int(milestone_record.get("acceptance_total", 0)),
        )

    return ProjectMetadataSnapshot(
        schema_version=int(record.get("schema_version", 1)),
        project_type=ProjectType(str(record["project_type"])),
        strategic_themes=tuple(cast(list[str], themes_raw)),
        planning_horizon=PlanningHorizon(str(record.get("planning_horizon", "later"))),
        wip=bool(record.get("wip", False)),
        milestone=milestone,
        dependency_count=int(record.get("dependency_count", 0)),
        outcome_count=int(record.get("outcome_count", 0)),
    )


def load_metadata_inventory(path: Path) -> MetadataInventory:
    """Load the derived metadata inventory, returning an empty inventory if absent."""

    if not path.exists():
        return MetadataInventory(migrated={}, missing=frozenset())
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("metadata inventory root must be an object")
    record = cast(JsonObject, raw)
    migrated_raw = record.get("migrated", {})
    missing_raw = record.get("missing", [])
    if not isinstance(migrated_raw, dict):
        raise TypeError("migrated must be an object")
    if not isinstance(missing_raw, list) or not all(isinstance(item, str) for item in missing_raw):
        raise TypeError("missing must be a list of strings")
    migrated = {
        str(repository): _snapshot_from_record(snapshot)
        for repository, snapshot in migrated_raw.items()
    }
    return MetadataInventory(
        version=int(record.get("version", 1)),
        migrated=migrated,
        missing=frozenset(cast(list[str], missing_raw)),
    )


def write_metadata_inventory(
    path: Path,
    snapshots: tuple[tuple[str, ProjectMetadataSnapshot], ...],
    missing: tuple[str, ...],
) -> None:
    """Atomically write the current migration/classification inventory."""

    payload = {
        "version": 1,
        "migrated": {
            repository: _snapshot_record(snapshot)
            for repository, snapshot in sorted(snapshots, key=lambda item: item[0].casefold())
        },
        "missing": sorted(missing, key=str.casefold),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
