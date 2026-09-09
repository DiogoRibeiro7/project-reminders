"""Observed GitHub operational state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from project_reminders.application.services import PortfolioService
from project_reminders.domain.models import OperationalSnapshot


class OperationalGateway(Protocol):
    """External boundary for observing one repository's current state."""

    def snapshot(self, repository: str) -> OperationalSnapshot:
        """Return a current GitHub operational snapshot."""
        ...


@dataclass(frozen=True, slots=True)
class OperationalRefreshResult:
    """Result of a resilient multi-repository refresh."""

    snapshots: tuple[tuple[str, OperationalSnapshot], ...]
    failed: tuple[tuple[str, str], ...]

    @property
    def updated(self) -> tuple[str, ...]:
        """Repository names successfully observed."""

        return tuple(repository for repository, _ in self.snapshots)


@dataclass(frozen=True, slots=True)
class _SafeSnapshot:
    repository: str
    snapshot: OperationalSnapshot | None = None
    error: str | None = None


class OperationalRefreshService:
    """Refresh observed GitHub state without altering declared project fields."""

    def __init__(self, portfolio: PortfolioService, gateway: OperationalGateway) -> None:
        self._portfolio = portfolio
        self._gateway = gateway

    def _snapshot_safely(self, repository: str) -> _SafeSnapshot:
        try:
            return _SafeSnapshot(repository=repository, snapshot=self._gateway.snapshot(repository))
        except (RuntimeError, TypeError, ValueError) as exc:
            return _SafeSnapshot(repository=repository, error=str(exc))

    def refresh(
        self,
        identifier: str | None = None,
        *,
        write: bool = False,
        max_workers: int = 1,
    ) -> OperationalRefreshResult:
        """Observe projects resiliently with deterministic bounded concurrency."""

        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        projects = (
            (self._portfolio.find(identifier),) if identifier else self._portfolio.load().projects
        )
        ordered = tuple(sorted(projects, key=lambda project: project.repository.casefold()))
        repositories = tuple(project.repository for project in ordered)

        if max_workers == 1 or len(repositories) < 2:
            results = tuple(self._snapshot_safely(repository) for repository in repositories)
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(repositories))) as executor:
                results = tuple(executor.map(self._snapshot_safely, repositories))

        snapshots: dict[str, OperationalSnapshot] = {}
        failed: list[tuple[str, str]] = []
        for result in results:
            if result.snapshot is not None:
                snapshots[result.repository] = result.snapshot
            elif result.error is not None:
                failed.append((result.repository, result.error))

        if write and snapshots:
            self._portfolio.apply_operational_many(snapshots)
        ordered_snapshots = tuple(sorted(snapshots.items(), key=lambda item: item[0].casefold()))
        return OperationalRefreshResult(snapshots=ordered_snapshots, failed=tuple(failed))
