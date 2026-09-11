"""Discover, assess and observe the owned GitHub repository portfolio."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from project_reminders.application.assessment import AssessmentService
from project_reminders.application.github_import import GitHubImportService
from project_reminders.application.operational import OperationalRefreshService
from project_reminders.application.refresh_safety import (
    MIN_STAGE_COVERAGE,
    RefreshCoverage,
    refresh_is_safe,
)
from project_reminders.bootstrap import build_service
from project_reminders.infrastructure.github import GitHubRepositoryDiscovery
from project_reminders.infrastructure.github_cache import (
    CachedGitHubOperationalState,
    CachedGitHubRepositoryEvidence,
    ControlPlaneGitHubOperationalState,
    GitHubRunCache,
)

DEFAULT_REFRESH_WORKERS = 8


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


def _worker_count() -> int:
    raw = os.environ.get("PROJECT_REFRESH_WORKERS", str(DEFAULT_REFRESH_WORKERS))
    try:
        workers = int(raw)
    except ValueError as exc:
        raise ValueError("PROJECT_REFRESH_WORKERS must be an integer") from exc
    if workers < 1 or workers > 32:
        raise ValueError("PROJECT_REFRESH_WORKERS must be between 1 and 32")
    return workers


def main() -> int:
    """Discover eligible owned repos, then refresh tracked evidence resiliently."""

    root = Path.cwd()
    service = build_service(root)
    token = _token()
    workers = _worker_count()

    importer = GitHubImportService(service, GitHubRepositoryDiscovery(token))
    imported = importer.import_repositories()

    projects = tuple(
        sorted(service.load().projects, key=lambda project: project.repository.casefold())
    )
    repositories = tuple(project.repository for project in projects)
    cache = GitHubRunCache()

    assessor = AssessmentService(CachedGitHubRepositoryEvidence(token, cache))
    assessment = assessor.assess_many_resilient(repositories, max_workers=workers)

    control_repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    operational_gateway = (
        ControlPlaneGitHubOperationalState(token, cache, control_repository)
        if control_repository
        else CachedGitHubOperationalState(token, cache)
    )
    observer = OperationalRefreshService(service, operational_gateway)
    operational = observer.refresh(write=False, max_workers=workers)

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
        f"imported={len(imported)} "
        f"assessed={len(assessment.updated)} "
        f"observed={len(operational.updated)} "
        f"failures={len(failures)} "
        f"workers={workers} "
        f"cache_hits={cache.hits} "
        f"cache_entries={cache.entries}"
    )
    for project in imported:
        print(f"NEW {project.repository} [unclassified]")
    for failure in failures:
        print(f"WARN {failure.repository} [{failure.stage}]: {failure.error}")

    total = len(projects)
    assessment_coverage = RefreshCoverage(len(assessment.updated), total)
    observation_coverage = RefreshCoverage(len(operational.updated), total)
    if not refresh_is_safe(assessment_coverage, observation_coverage):
        print(
            "ERROR unsafe refresh coverage: "
            f"assessment={assessment_coverage.ratio:.1%} "
            f"observation={observation_coverage.ratio:.1%} "
            f"minimum={MIN_STAGE_COVERAGE:.0%}"
        )
        return 2

    if assessment.assessments:
        service.apply_health_many(assessment.assessments)
    if operational.snapshots:
        service.apply_operational_many(dict(operational.snapshots))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
