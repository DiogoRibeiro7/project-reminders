"""Persistence for the derived repository-local metadata inventory."""

from __future__ import annotations

import json
from pathlib import Path

from project_reminders.domain.metadata import ProjectMetadataSnapshot


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
