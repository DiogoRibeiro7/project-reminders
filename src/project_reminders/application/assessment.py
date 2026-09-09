"""Deterministic engineering-health assessment from repository evidence."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from project_reminders.domain.enums import HealthDimension, HealthState
from project_reminders.domain.models import EngineeringHealth


@dataclass(frozen=True, slots=True)
class RepositoryEvidence:
    """Observed repository facts used by the assessment rules."""

    paths: frozenset[str]
    complete_tree: bool
    primary_language: str | None = None
    has_release: bool = False
    has_tag: bool = False
    pyproject_tools: frozenset[str] = frozenset()
    pyproject_inspected: bool = True


class RepositoryEvidenceGateway(Protocol):
    """External boundary for collecting repository evidence."""

    def evidence(self, repository: str) -> RepositoryEvidence:
        """Return observable facts for one repository."""
        ...


def _has_prefix(paths: frozenset[str], prefix: str) -> bool:
    normalized = prefix.rstrip("/") + "/"
    return any(path == prefix.rstrip("/") or path.startswith(normalized) for path in paths)


def _has_any(paths: frozenset[str], candidates: set[str]) -> bool:
    return any(candidate in paths for candidate in candidates)


def _missing_or_unknown(evidence: RepositoryEvidence) -> HealthState:
    return HealthState.MISSING if evidence.complete_tree else HealthState.UNKNOWN


def _config_absence_state(evidence: RepositoryEvidence) -> HealthState:
    if "pyproject.toml" in evidence.paths and not evidence.pyproject_inspected:
        return HealthState.UNKNOWN
    return _missing_or_unknown(evidence)


def assess_repository(evidence: RepositoryEvidence) -> EngineeringHealth:
    """Map repository evidence to deterministic engineering-health states."""

    paths = evidence.paths
    states: dict[HealthDimension, HealthState] = {}

    if _has_prefix(paths, "tests") or _has_prefix(paths, "test"):
        states[HealthDimension.TESTS] = HealthState.COMPLETE
    elif any(path.startswith("test_") or "/test_" in path for path in paths):
        states[HealthDimension.TESTS] = HealthState.PARTIAL
    else:
        states[HealthDimension.TESTS] = _missing_or_unknown(evidence)

    if _has_prefix(paths, ".github/workflows") or _has_any(
        paths, {".gitlab-ci.yml", "azure-pipelines.yml"}
    ):
        states[HealthDimension.CI] = HealthState.COMPLETE
    else:
        states[HealthDimension.CI] = _missing_or_unknown(evidence)

    has_readme = any(
        path.casefold() in {"readme.md", "readme.rst", "readme.txt"} for path in paths
    )
    has_docs = _has_prefix(paths, "docs") or _has_prefix(paths, "documentation")
    if has_readme and has_docs:
        states[HealthDimension.DOCUMENTATION] = HealthState.COMPLETE
    elif has_readme:
        states[HealthDimension.DOCUMENTATION] = HealthState.PARTIAL
    else:
        states[HealthDimension.DOCUMENTATION] = _missing_or_unknown(evidence)

    packaging_files = {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "DESCRIPTION",
    }
    states[HealthDimension.PACKAGING] = (
        HealthState.COMPLETE if _has_any(paths, packaging_files) else _missing_or_unknown(evidence)
    )

    lint_files = {
        "ruff.toml",
        ".ruff.toml",
        ".flake8",
        ".eslintrc",
        ".eslintrc.json",
        "biome.json",
    }
    has_lint_tool = bool(evidence.pyproject_tools & {"ruff", "flake8", "pylint"})
    states[HealthDimension.LINT] = (
        HealthState.COMPLETE
        if _has_any(paths, lint_files) or has_lint_tool
        else _config_absence_state(evidence)
    )

    language = (evidence.primary_language or "").casefold()
    typing_files = {"mypy.ini", "pyrightconfig.json"}
    has_typing_tool = bool(evidence.pyproject_tools & {"mypy", "pyright"})
    if _has_any(paths, typing_files) or has_typing_tool:
        states[HealthDimension.TYPING] = HealthState.COMPLETE
    elif language == "python":
        states[HealthDimension.TYPING] = _config_absence_state(evidence)
    else:
        states[HealthDimension.TYPING] = HealthState.UNKNOWN

    security_signals = {
        "SECURITY.md",
        ".github/dependabot.yml",
        ".github/dependabot.yaml",
        ".github/workflows/codeql.yml",
        ".github/workflows/codeql.yaml",
        ".github/workflows/security.yml",
        ".github/workflows/security.yaml",
    }
    states[HealthDimension.SECURITY] = (
        HealthState.COMPLETE
        if _has_any(paths, security_signals)
        else _missing_or_unknown(evidence)
    )

    lock_files = {
        "poetry.lock",
        "uv.lock",
        "requirements.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
    }
    environment_files = {
        "Dockerfile",
        "docker-compose.yml",
        "compose.yml",
        "environment.yml",
    }
    has_lock = _has_any(paths, lock_files)
    has_environment = _has_any(paths, environment_files)
    if has_lock and has_environment:
        states[HealthDimension.REPRODUCIBILITY] = HealthState.COMPLETE
    elif has_lock or has_environment:
        states[HealthDimension.REPRODUCIBILITY] = HealthState.PARTIAL
    else:
        states[HealthDimension.REPRODUCIBILITY] = _missing_or_unknown(evidence)

    if evidence.has_release:
        states[HealthDimension.RELEASE] = HealthState.COMPLETE
    elif evidence.has_tag:
        states[HealthDimension.RELEASE] = HealthState.PARTIAL
    else:
        states[HealthDimension.RELEASE] = HealthState.MISSING

    demo_paths = {"examples", "example", "demo", "notebooks"}
    states[HealthDimension.DEMO] = (
        HealthState.COMPLETE
        if any(_has_prefix(paths, candidate) for candidate in demo_paths)
        else _missing_or_unknown(evidence)
    )

    return EngineeringHealth(states)


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    """Health assessment for one tracked repository."""

    repository: str
    health: EngineeringHealth


@dataclass(frozen=True, slots=True)
class AssessmentRefreshResult:
    """Resilient multi-repository assessment result."""

    assessments: Mapping[str, EngineeringHealth]
    failed: tuple[tuple[str, str], ...]

    @property
    def updated(self) -> tuple[str, ...]:
        """Repository names successfully assessed."""

        return tuple(sorted(self.assessments, key=str.casefold))


@dataclass(frozen=True, slots=True)
class _SafeAssessment:
    repository: str
    health: EngineeringHealth | None = None
    error: str | None = None


class AssessmentService:
    """Assess tracked repositories without altering lifecycle state."""

    def __init__(self, gateway: RepositoryEvidenceGateway) -> None:
        self._gateway = gateway

    def assess(self, repository: str) -> AssessmentResult:
        """Assess one repository using only observed evidence."""

        evidence = self._gateway.evidence(repository)
        return AssessmentResult(repository=repository, health=assess_repository(evidence))

    def assess_many(self, repositories: tuple[str, ...]) -> Mapping[str, EngineeringHealth]:
        """Assess repositories in stable order, failing fast on collection errors."""

        return {
            repository: self.assess(repository).health
            for repository in sorted(repositories, key=str.casefold)
        }

    def _assess_safely(self, repository: str) -> _SafeAssessment:
        try:
            return _SafeAssessment(repository=repository, health=self.assess(repository).health)
        except (RuntimeError, TypeError, ValueError) as exc:
            return _SafeAssessment(repository=repository, error=str(exc))

    def assess_many_resilient(
        self,
        repositories: tuple[str, ...],
        *,
        max_workers: int = 1,
    ) -> AssessmentRefreshResult:
        """Assess independently with deterministic output and bounded concurrency."""

        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        ordered = tuple(sorted(repositories, key=str.casefold))
        if not ordered:
            return AssessmentRefreshResult(assessments={}, failed=())

        if max_workers == 1:
            results = tuple(self._assess_safely(repository) for repository in ordered)
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(ordered))) as executor:
                results = tuple(executor.map(self._assess_safely, ordered))

        assessments: dict[str, EngineeringHealth] = {}
        failed: list[tuple[str, str]] = []
        for result in results:
            if result.health is not None:
                assessments[result.repository] = result.health
            elif result.error is not None:
                failed.append((result.repository, result.error))
        return AssessmentRefreshResult(assessments=assessments, failed=tuple(failed))
