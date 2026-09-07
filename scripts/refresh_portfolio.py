"""Refresh engineering health and live GitHub state for the tracked portfolio."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from project_reminders.application.assessment import AssessmentService
from project_reminders.application.operational import OperationalRefreshService
from project_reminders.bootstrap import build_service
from project_reminders.domain.models import EngineeringHealth
from project_reminders.infrastructure.github import (
    GitHubOperationalState,
    GitHubRepositoryEvidence,
)


@dataclass(frozen=True, slots=True)
class RefreshFailure:
    """One isolated repository refresh failure."""

    repository: str
    stage: str
    error: str


def _token() -> str:
    token = os.environ.get("PROJECT_SCAN_TOKEN", "")
    if not token.strip():
        raise ValueError("PROJECT_SCAN_TOKEN must not be empty")
    return token


def main() -> int:
    """Refresh every tracked repository while preserving prior values on failure."""

    root = Path.cwd()
    service = build_service(root)
    projects = tuple(sorted(service.load().projects, key=lambda project: project.repository.casefold()))
    token = _token()
    assessor = AssessmentService(GitHubRepositoryEvidence(token))
    observer = OperationalRefreshService(service, GitHubOperationalState(token))

    health_updates: dict[str, EngineeringHealth] = {}
    failures: list[RefreshFailure] = []

    for project in projects:
        try:
            health_updates[project.repository] = assessor.assess(project.repository).health
        except (RuntimeError, TypeError, ValueError) as exc:
            failures.append(RefreshFailure(project.repository, "assessment", str(exc)))

    if health_updates:
        service.apply_health_many(health_updates)

    operational = observer.refresh(write=True)
    failures.extend(
        RefreshFailure(repository, "observation", error)
        for repository, error in operational.failed
    )

    print(
        "Portfolio refresh: "
        f"tracked={len(projects)} "
        f"assessed={len(health_updates)} "
        f"observed={len(operational.updated)} "
        f"failures={len(failures)}"
    )
    for failure in failures:
        print(f"WARN {failure.repository} [{failure.stage}]: {failure.error}")

    successful_repositories = set(health_updates) | set(operational.updated)
    if not successful_repositories and projects:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
