"""Safety checks for accepting multi-repository refresh results."""

from __future__ import annotations

from dataclasses import dataclass

MIN_STAGE_COVERAGE = 0.90


@dataclass(frozen=True, slots=True)
class RefreshCoverage:
    """Success coverage for one refresh stage."""

    succeeded: int
    total: int

    def __post_init__(self) -> None:
        if self.succeeded < 0 or self.total < 0:
            raise ValueError("refresh coverage counts must be non-negative")
        if self.succeeded > self.total:
            raise ValueError("refresh successes cannot exceed total repositories")

    @property
    def ratio(self) -> float:
        """Return successful coverage, treating an empty estate as complete."""

        return 1.0 if self.total == 0 else self.succeeded / self.total

    def is_safe(self, minimum: float = MIN_STAGE_COVERAGE) -> bool:
        """Return whether this stage clears the configured safety threshold."""

        if not 0.0 <= minimum <= 1.0:
            raise ValueError("minimum refresh coverage must be between 0 and 1")
        return self.ratio >= minimum


def refresh_is_safe(
    assessment: RefreshCoverage,
    observation: RefreshCoverage,
    *,
    minimum: float = MIN_STAGE_COVERAGE,
) -> bool:
    """Require independently safe assessment and observation coverage."""

    return assessment.is_safe(minimum) and observation.is_safe(minimum)
