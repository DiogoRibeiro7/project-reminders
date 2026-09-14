"""Print the manual migration queue for repositories missing `.project.json`."""

from __future__ import annotations

from pathlib import Path

from project_reminders.application.metadata_migration import (
    build_metadata_migration_queue,
    MetadataMigrationWave,
)
from project_reminders.bootstrap import build_service
from project_reminders.infrastructure.metadata_inventory import load_metadata_inventory


DEFAULT_LIMIT = 30


def main() -> int:
    """Print the highest-value repositories to classify next."""

    root = Path.cwd()
    portfolio = build_service(root).load()
    inventory = load_metadata_inventory(root / "data" / "project_metadata.json")
    queue = build_metadata_migration_queue(portfolio, inventory)

    counts = {
        wave: sum(candidate.wave is wave for candidate in queue) for wave in MetadataMigrationWave
    }
    print(
        "Metadata migration queue: "
        f"active={counts[MetadataMigrationWave.ACTIVE]} "
        f"recent={counts[MetadataMigrationWave.RECENT]} "
        f"later={counts[MetadataMigrationWave.LATER]} "
        f"total={len(queue)}"
    )
    for index, candidate in enumerate(queue[:DEFAULT_LIMIT], start=1):
        activity = (
            candidate.project.operational.latest_activity_at
            or candidate.project.last_repository_activity_at
        )
        activity_text = activity.date().isoformat() if activity is not None else "—"
        print(
            f"{index:2}. [{candidate.wave.value:6}] "
            f"{candidate.project.repository} "
            f"priority={candidate.project.priority.value} "
            f"lifecycle={candidate.project.status.value} "
            f"activity={activity_text}"
        )
        print(f"    {candidate.reason}")
    if len(queue) > DEFAULT_LIMIT:
        print(f"... {len(queue) - DEFAULT_LIMIT} additional later candidates omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
