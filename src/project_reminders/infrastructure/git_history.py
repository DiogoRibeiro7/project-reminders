"""Read previous portfolio snapshots from local Git history."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory

from project_reminders.domain.models import Portfolio
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


class HistoryAvailability(StrEnum):
    """Explain whether a previous portfolio snapshot can be resolved locally."""

    AVAILABLE = "available"
    NO_PRIOR_SNAPSHOT = "no_prior_snapshot"
    SHALLOW_CHECKOUT = "shallow_checkout"
    GIT_UNAVAILABLE = "git_unavailable"


@dataclass(frozen=True, slots=True)
class PortfolioHistoryLookup:
    """Result of resolving the previous committed portfolio snapshot."""

    previous: Portfolio | None
    availability: HistoryAvailability

    @property
    def available(self) -> bool:
        """Return whether a previous snapshot was successfully loaded."""

        return self.previous is not None


class GitPortfolioHistory:
    """Load the previous committed projects.json snapshot without new persistence."""

    def __init__(self, root: Path, relative_path: str = "data/projects.json") -> None:
        self.root = root
        self.relative_path = relative_path

    def previous(self, current: Portfolio) -> Portfolio | None:
        """Return the previous committed portfolio snapshot when available."""

        return self.lookup(current).previous

    def lookup(self, current: Portfolio) -> PortfolioHistoryLookup:
        """Resolve the previous snapshot and explain why it may be unavailable."""

        revisions = self._revisions()
        if revisions is None:
            return PortfolioHistoryLookup(None, HistoryAvailability.GIT_UNAVAILABLE)
        if not revisions:
            availability = (
                HistoryAvailability.SHALLOW_CHECKOUT
                if self._is_shallow_repository()
                else HistoryAvailability.NO_PRIOR_SNAPSHOT
            )
            return PortfolioHistoryLookup(None, availability)

        latest = self._load_revision(revisions[0])
        if latest.generated_at != current.generated_at:
            return PortfolioHistoryLookup(latest, HistoryAvailability.AVAILABLE)
        if len(revisions) >= 2:
            return PortfolioHistoryLookup(
                self._load_revision(revisions[1]),
                HistoryAvailability.AVAILABLE,
            )

        availability = (
            HistoryAvailability.SHALLOW_CHECKOUT
            if self._is_shallow_repository()
            else HistoryAvailability.NO_PRIOR_SNAPSHOT
        )
        return PortfolioHistoryLookup(None, availability)

    def _revisions(self) -> tuple[str, ...] | None:
        try:
            result = subprocess.run(
                ["git", "log", "-n", "2", "--format=%H", "--", self.relative_path],
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _is_shallow_repository(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return False
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _load_revision(self, revision: str) -> Portfolio:
        result = subprocess.run(
            ["git", "show", f"{revision}:{self.relative_path}"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            path.write_text(result.stdout, encoding="utf-8")
            return JsonPortfolioRepository(path).load()
