"""Portfolio refresh coverage safety tests."""

import pytest

from project_reminders.application.refresh_safety import (
    MIN_STAGE_COVERAGE,
    RefreshCoverage,
    refresh_is_safe,
)


def test_established_healthy_refresh_coverage_passes() -> None:
    assert refresh_is_safe(
        RefreshCoverage(501, 503),
        RefreshCoverage(503, 503),
    )


def test_catastrophic_production_outage_is_rejected() -> None:
    assessment = RefreshCoverage(318, 503)
    observation = RefreshCoverage(0, 503)

    assert assessment.ratio == pytest.approx(318 / 503)
    assert observation.ratio == 0.0
    assert refresh_is_safe(assessment, observation) is False


def test_each_stage_must_clear_minimum_independently() -> None:
    assert refresh_is_safe(RefreshCoverage(90, 100), RefreshCoverage(100, 100)) is True
    assert refresh_is_safe(RefreshCoverage(100, 100), RefreshCoverage(89, 100)) is False
    assert MIN_STAGE_COVERAGE == 0.90


def test_empty_estate_is_safe() -> None:
    coverage = RefreshCoverage(0, 0)

    assert coverage.ratio == 1.0
    assert refresh_is_safe(coverage, coverage) is True


@pytest.mark.parametrize(
    ("succeeded", "total"),
    [(-1, 1), (0, -1), (2, 1)],
)
def test_invalid_coverage_counts_are_rejected(succeeded: int, total: int) -> None:
    with pytest.raises(ValueError):
        RefreshCoverage(succeeded, total)
