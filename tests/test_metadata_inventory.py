"""Derived metadata inventory persistence tests."""

from pathlib import Path

from project_reminders.domain.metadata import (
    MilestoneSnapshot,
    MilestoneStatus,
    PlanningHorizon,
    ProjectMetadataSnapshot,
    ProjectType,
)
from project_reminders.infrastructure.metadata_inventory import (
    load_metadata_inventory,
    write_metadata_inventory,
)


def test_metadata_inventory_round_trip_and_status_lookup(tmp_path: Path) -> None:
    path = tmp_path / "data" / "project_metadata.json"
    snapshot = ProjectMetadataSnapshot(
        project_type=ProjectType.RESEARCH,
        strategic_themes=("mathematical-research",),
        planning_horizon=PlanningHorizon.NOW,
        wip=True,
        milestone=MilestoneSnapshot(
            id="M01",
            title="Prove result",
            status=MilestoneStatus.WIP,
            acceptance_done=1,
            acceptance_total=2,
        ),
        dependency_count=1,
        outcome_count=2,
    )

    write_metadata_inventory(
        path,
        (("owner/migrated", snapshot),),
        ("owner/missing",),
    )
    inventory = load_metadata_inventory(path)

    assert inventory.migration_status("OWNER/MIGRATED") == "migrated"
    assert inventory.migration_status("owner/missing") == "missing"
    assert inventory.migration_status("owner/unknown") == "unknown"
    loaded = inventory.snapshot_for("owner/migrated")
    assert loaded == snapshot
    assert loaded is not None
    assert loaded.milestone is not None
    assert loaded.milestone.acceptance_done == 1


def test_missing_inventory_is_empty_and_unknown(tmp_path: Path) -> None:
    inventory = load_metadata_inventory(tmp_path / "missing.json")

    assert inventory.migrated == {}
    assert inventory.missing == frozenset()
    assert inventory.migration_status("owner/project") == "unknown"
