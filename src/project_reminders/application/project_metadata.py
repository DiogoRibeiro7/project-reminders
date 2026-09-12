"""Repository-local project metadata refresh orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from project_reminders.domain.metadata import ProjectMetadata, ProjectMetadataSnapshot, summarize_project_metadata


class ProjectMetadataGateway(Protocol):
    """Boundary for reading repository-local project metadata."""

    def project_metadata(self, repository: str) -> ProjectMetadata | None:
        """Return validated metadata, or None when the repository has not migrated yet."""
        ...


@dataclass(frozen=True, slots=True)
class MetadataRefreshResult:
    """Validated metadata snapshots plus missing and failed repositories."""

    snapshots: tuple[tuple[str, ProjectMetadataSnapshot], ...]
    missing: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]

    @property
    def succeeded(self) -> int:
        """Repositories successfully classified as migrated or not yet migrated."""

        return len(self.snapshots) + len(self.missing)


@dataclass(frozen=True, slots=True)
class _SafeMetadata:
    repository: str
    snapshot: ProjectMetadataSnapshot | None = None
    missing: bool = False
    error: str | None = None


class ProjectMetadataRefreshService:
    """Read project metadata without changing declared portfolio state."""

    def __init__(self, gateway: ProjectMetadataGateway) -> None:
        self._gateway = gateway

    def _read_safely(self, repository: str) -> _SafeMetadata:
        try:
            metadata = self._gateway.project_metadata(repository)
            if metadata is None:
                return _SafeMetadata(repository=repository, missing=True)
            return _SafeMetadata(
                repository=repository,
                snapshot=summarize_project_metadata(metadata),
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            return _SafeMetadata(repository=repository, error=str(exc))

    def refresh(
        self,
        repositories: tuple[str, ...],
        *,
        max_workers: int = 1,
    ) -> MetadataRefreshResult:
        """Read repositories independently with deterministic output ordering."""

        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        ordered = tuple(sorted(repositories, key=str.casefold))
        if max_workers == 1 or len(ordered) < 2:
            results = tuple(self._read_safely(repository) for repository in ordered)
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(ordered))) as executor:
                results = tuple(executor.map(self._read_safely, ordered))

        snapshots: list[tuple[str, ProjectMetadataSnapshot]] = []
        missing: list[str] = []
        failed: list[tuple[str, str]] = []
        for result in results:
            if result.snapshot is not None:
                snapshots.append((result.repository, result.snapshot))
            elif result.missing:
                missing.append(result.repository)
            elif result.error is not None:
                failed.append((result.repository, result.error))
        return MetadataRefreshResult(
            snapshots=tuple(snapshots),
            missing=tuple(missing),
            failed=tuple(failed),
        )
