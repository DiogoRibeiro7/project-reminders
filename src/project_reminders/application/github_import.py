"""Repository discovery and conservative portfolio import."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from project_reminders.application.services import PortfolioService
from project_reminders.domain.enums import Priority, ProjectStatus
from project_reminders.domain.models import Project


@dataclass(frozen=True, slots=True)
class DiscoveredRepository:
    """Repository metadata observed from GitHub without portfolio judgement."""

    full_name: str
    name: str
    description: str
    private: bool
    fork: bool
    archived: bool
    default_branch: str
    pushed_at: datetime | None


class RepositoryDiscoveryGateway(Protocol):
    """External boundary for repository discovery."""

    def repositories(self) -> tuple[DiscoveredRepository, ...]:
        """Return repositories visible to the configured GitHub identity."""
        ...


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """Dry-run/result description for a conservative repository import."""

    candidates: tuple[DiscoveredRepository, ...]
    skipped_existing: tuple[DiscoveredRepository, ...]
    skipped_forks: tuple[DiscoveredRepository, ...]
    skipped_archived: tuple[DiscoveredRepository, ...]


class GitHubImportService:
    """Discover repositories and import only untracked eligible repositories."""

    def __init__(self, portfolio: PortfolioService, discovery: RepositoryDiscoveryGateway) -> None:
        self._portfolio = portfolio
        self._discovery = discovery

    def plan(self, *, include_forks: bool = False, include_archived: bool = False) -> ImportPlan:
        """Build a deterministic import plan without changing portfolio data."""

        existing = {project.repository.casefold() for project in self._portfolio.load().projects}
        candidates: list[DiscoveredRepository] = []
        skipped_existing: list[DiscoveredRepository] = []
        skipped_forks: list[DiscoveredRepository] = []
        skipped_archived: list[DiscoveredRepository] = []

        for repository in sorted(self._discovery.repositories(), key=lambda item: item.full_name.casefold()):
            if repository.full_name.casefold() in existing:
                skipped_existing.append(repository)
            elif repository.fork and not include_forks:
                skipped_forks.append(repository)
            elif repository.archived and not include_archived:
                skipped_archived.append(repository)
            else:
                candidates.append(repository)

        return ImportPlan(
            candidates=tuple(candidates),
            skipped_existing=tuple(skipped_existing),
            skipped_forks=tuple(skipped_forks),
            skipped_archived=tuple(skipped_archived),
        )

    def import_repositories(
        self,
        *,
        include_forks: bool = False,
        include_archived: bool = False,
    ) -> tuple[Project, ...]:
        """Import eligible repositories with no inferred maturity or health claims."""

        plan = self.plan(include_forks=include_forks, include_archived=include_archived)
        imported: list[Project] = []
        for repository in plan.candidates:
            project = self._portfolio.add_project(
                name=repository.name,
                repository=repository.full_name,
                status=ProjectStatus.IDEA,
                priority=Priority.MEDIUM,
                summary=repository.description,
            )
            imported.append(project)
        return tuple(imported)
