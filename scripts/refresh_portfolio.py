"""Refresh engineering health and live GitHub state for the tracked portfolio."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from project_reminders.application.assessment import AssessmentService
from project_reminders.application.operational import OperationalRefreshService
from project_reminders.bootstrap import build_service
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
    projects = tuple(
        sorted(service.load().projects, key=lambda project: project.repository.casefold())
    )
    repositories = tuple(project.repository for project in projects)
    token = _token()

    assessor = AssessmentService(GitHubRepositoryEvidence(token))
    assessment = assessor.assess_many_resilient(repositories)
    if assessment.assessments:
        service.apply_health_many(assessment.assessments)

    observer = OperationalRefreshService(service, GitHubOperationalState(token))
    operational = observer.refresh(write=True)

    failures = [
        RefreshFailure(repository, "assessment", error)
        for repository, error in assessment.failed
    ]
    failures.extend(
        RefreshFailure(repository, "observation", error)
        for repository, error in operational.failed
    )

    print(
        "Portfolio refresh: "
        f"tracked={len(projects)} "
        f"assessed={len(assessment.updated)} "
        f"observed={len(operational.updated)} "
        f"failures={len(failures)}"
    )
    for failure in failures:
        print(f"WARN {failure.repository} [{failure.stage}]: {failure.error}")

    successful_repositories = set(assessment.updated) | set(operational.updated)
    if not successful_repositories and projects:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
