"""Read previous portfolio snapshots from local Git history."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from project_reminders.domain.models import Portfolio
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


class GitPortfolioHistory:
    """Load the previous committed projects.json snapshot without new persistence."""

    def __init__(self, root: Path, relative_path: str = "data/projects.json") -> None:
        self.root = root
        self.relative_path = relative_path

    def previous(self, current: Portfolio) -> Portfolio | None:
        """Return the previous committed portfolio snapshot when available."""

        revisions = self._revisions()
        if not revisions:
            return None
        latest = self._load_revision(revisions[0])
        if latest.generated_at != current.generated_at:
            return latest
        if len(revisions) < 2:
            return None
        return self._load_revision(revisions[1])

    def _revisions(self) -> tuple[str, ...]:
        result = subprocess.run(
            ["git", "log", "-n", "2", "--format=%H", "--", self.relative_path],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ()
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

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
