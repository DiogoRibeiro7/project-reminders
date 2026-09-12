"""Validate repository-local project planning metadata."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from project_reminders.infrastructure.project_metadata import load_project_metadata


def _parser() -> argparse.ArgumentParser:
    """Build the metadata-validator command-line parser."""

    parser = argparse.ArgumentParser(prog="validate-project-metadata")
    parser.add_argument("path", type=Path, nargs="?", default=Path(".project.json"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate one metadata file and return a process exit code."""

    path = _parser().parse_args(argv).path
    try:
        metadata = load_project_metadata(path)
    except (OSError, TypeError, ValueError) as exc:
        print(f"invalid project metadata: {exc}")
        return 2

    milestone = metadata.milestone.id if metadata.milestone is not None else "—"
    print(
        "valid project metadata: "
        f"type={metadata.project_type.value}, "
        f"horizon={metadata.planning_horizon.value}, "
        f"wip={str(metadata.wip).lower()}, "
        f"milestone={milestone}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
