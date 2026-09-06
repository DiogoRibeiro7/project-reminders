"""State-changing portfolio application service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from project_reminders.application.ports import PortfolioRepository
from project_reminders.domain.enums import HealthDimension, HealthState, Priority, ProjectStatus
from project_reminders.domain.models import EngineeringHealth, NextAction, Portfolio, Project

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


class PortfolioService:
    """Single entry point for portfolio mutations."""

    def __init__(self, repository: PortfolioRepository, clock: Clock = utc_now) -> None:
        self._repository = repository
        self._clock = clock

    def load(self) -> Portfolio:
        """Load the current portfolio."""

        return self._repository.load()

    def find(self, identifier: str) -> Project:
        """Find by stable id, exact name, or owner/name repository."""

        normalized = identifier.casefold()
        for project in self.load().projects:
            if normalized in {
                project.id.casefold(),
                project.name.casefold(),
                project.repository.casefold(),
            }:
                return project
        raise KeyError(f"unknown project: {identifier}")

    def add_project(
        self,
        *,
        name: str,
        repository: str,
        status: ProjectStatus,
        priority: Priority,
        next_action: str | None = None,
        summary: str = "",
    ) -> Project:
        """Create and persist a new project."""

        portfolio = self.load()
        repository_key = repository.casefold()
        if any(project.repository.casefold() == repository_key for project in portfolio.projects):
            raise ValueError(f"repository is already tracked: {repository}")

        now = self._clock()
        project = Project(
            id=uuid4().hex[:12],
            name=name,
            repository=repository,
            status=status,
            priority=priority,
            summary=summary,
            next_action=NextAction(next_action) if next_action else None,
            health=EngineeringHealth(),
            created_at=now,
            updated_at=now,
        )
        self._save_projects((*portfolio.projects, project), now)
        return project

    def set_status(self, identifier: str, status: ProjectStatus) -> Project:
        """Change lifecycle state without changing engineering health."""

        return self._replace(identifier, lambda project, now: replace(project, status=status, updated_at=now))

    def set_next_action(self, identifier: str, description: str | None) -> Project:
        """Set or clear the project's single next action."""

        action = NextAction(description) if description else None
        return self._replace(
            identifier,
            lambda project, now: replace(project, next_action=action, updated_at=now),
        )

    def set_health(
        self,
        identifier: str,
        dimension: HealthDimension,
        state: HealthState,
    ) -> Project:
        """Record one explicit engineering-health observation."""

        return self._replace(
            identifier,
            lambda project, now: replace(
                project,
                health=project.health.with_state(dimension, state),
                updated_at=now,
            ),
        )

    def _replace(self, identifier: str, transform: Callable[[Project, datetime], Project]) -> Project:
        portfolio = self.load()
        current = self.find(identifier)
        now = self._clock()
        updated = transform(current, now)
        projects = tuple(updated if project.id == current.id else project for project in portfolio.projects)
        self._save_projects(projects, now)
        return updated

    def _save_projects(self, projects: tuple[Project, ...], now: datetime) -> None:
        self._repository.save(Portfolio(projects=projects, generated_at=now))
