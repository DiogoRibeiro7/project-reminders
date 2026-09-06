"""Observed GitHub operational state."""

from __future__ import annotations

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


class OperationalRefreshService:
    """Refresh observed GitHub state without altering declared project fields."""

    def __init__(self, portfolio: PortfolioService, gateway: OperationalGateway) -> None:
        self._portfolio = portfolio
        self._gateway = gateway

    def refresh(self, identifier: str | None = None, *, write: bool = False) -> OperationalRefreshResult:
        """Observe one or all projects; failures are isolated per repository."""

        projects = (self._portfolio.find(identifier),) if identifier else self._portfolio.load().projects
        snapshots: dict[str, OperationalSnapshot] = {}
        failed: list[tuple[str, str]] = []
        for project in projects:
            try:
                snapshots[project.repository] = self._gateway.snapshot(project.repository)
            except (RuntimeError, TypeError, ValueError) as exc:
                failed.append((project.repository, str(exc)))
        if write and snapshots:
            self._portfolio.apply_operational_many(snapshots)
        ordered = tuple(sorted(snapshots.items(), key=lambda item: item[0].casefold()))
        return OperationalRefreshResult(snapshots=ordered, failed=tuple(failed))
