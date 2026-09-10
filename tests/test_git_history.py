"""Integration tests for local Git portfolio-history availability."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from project_reminders.infrastructure.git_history import (
    GitPortfolioHistory,
    HistoryAvailability,
)
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def _run(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _write_portfolio(root: Path, generated_at: str) -> None:
    path = root / "data" / "projects.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": generated_at,
                "projects": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _init_repository(root: Path) -> None:
    _run(root, "init", "-b", "main")
    _run(root, "config", "user.name", "History Test")
    _run(root, "config", "user.email", "history@example.com")


def _commit_snapshot(root: Path, generated_at: str, message: str) -> None:
    _write_portfolio(root, generated_at)
    _run(root, "add", "data/projects.json")
    _run(root, "commit", "-m", message)


def test_lookup_loads_previous_snapshot_from_full_history(tmp_path: Path) -> None:
    _init_repository(tmp_path)
    _commit_snapshot(tmp_path, "2026-09-09T00:00:00+00:00", "first")
    _commit_snapshot(tmp_path, "2026-09-10T00:00:00+00:00", "second")
    current = JsonPortfolioRepository(tmp_path / "data" / "projects.json").load()

    lookup = GitPortfolioHistory(tmp_path).lookup(current)

    assert lookup.availability is HistoryAvailability.AVAILABLE
    assert lookup.previous is not None
    assert lookup.previous.generated_at is not None
    assert lookup.previous.generated_at.isoformat() == "2026-09-09T00:00:00+00:00"


def test_lookup_reports_shallow_checkout_when_prior_snapshot_is_hidden(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _init_repository(source)
    _commit_snapshot(source, "2026-09-09T00:00:00+00:00", "first")
    _commit_snapshot(source, "2026-09-10T00:00:00+00:00", "second")

    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "--depth", "1", source.as_uri(), str(clone)],
        check=True,
        capture_output=True,
        text=True,
    )
    current = JsonPortfolioRepository(clone / "data" / "projects.json").load()

    lookup = GitPortfolioHistory(clone).lookup(current)

    assert lookup.previous is None
    assert lookup.availability is HistoryAvailability.SHALLOW_CHECKOUT
