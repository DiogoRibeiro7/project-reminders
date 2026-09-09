"""Deterministic repository-assessment tests."""

import pytest

from project_reminders.application.assessment import (
    AssessmentService,
    RepositoryEvidence,
    assess_repository,
)
from project_reminders.domain.enums import HealthDimension, HealthState


class _Gateway:
    def evidence(self, repository: str) -> RepositoryEvidence:
        if repository.endswith("broken"):
            raise RuntimeError("not accessible")
        return RepositoryEvidence(
            paths=frozenset({"README.md", "tests/test_core.py"}),
            complete_tree=True,
        )


def test_complete_python_repository_detects_core_engineering_signals() -> None:
    evidence = RepositoryEvidence(
        paths=frozenset(
            {
                "README.md",
                "docs/design.md",
                "tests/test_core.py",
                "pyproject.toml",
                "poetry.lock",
                "Dockerfile",
                "SECURITY.md",
                ".github/workflows/ci.yml",
                "examples/basic.py",
            }
        ),
        complete_tree=True,
        primary_language="Python",
        has_release=True,
        has_tag=True,
        pyproject_tools=frozenset({"ruff", "mypy"}),
    )

    health = assess_repository(evidence)

    assert health.state_for(HealthDimension.TESTS) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.CI) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.DOCUMENTATION) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.LINT) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.TYPING) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.REPRODUCIBILITY) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.RELEASE) is HealthState.COMPLETE


def test_packaging_only_pyproject_does_not_prove_lint_or_typing() -> None:
    health = assess_repository(
        RepositoryEvidence(
            paths=frozenset({"pyproject.toml"}),
            complete_tree=True,
            primary_language="Python",
            pyproject_tools=frozenset({"poetry"}),
        )
    )

    assert health.state_for(HealthDimension.PACKAGING) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.LINT) is HealthState.MISSING
    assert health.state_for(HealthDimension.TYPING) is HealthState.MISSING


def test_unreadable_pyproject_keeps_config_health_unknown() -> None:
    health = assess_repository(
        RepositoryEvidence(
            paths=frozenset({"pyproject.toml"}),
            complete_tree=True,
            primary_language="Python",
            pyproject_inspected=False,
        )
    )

    assert health.state_for(HealthDimension.LINT) is HealthState.UNKNOWN
    assert health.state_for(HealthDimension.TYPING) is HealthState.UNKNOWN


def test_explicit_config_files_still_prove_lint_and_typing() -> None:
    health = assess_repository(
        RepositoryEvidence(
            paths=frozenset({"ruff.toml", "mypy.ini"}),
            complete_tree=True,
            primary_language="Python",
        )
    )

    assert health.state_for(HealthDimension.LINT) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.TYPING) is HealthState.COMPLETE


def test_truncated_tree_never_turns_absence_into_missing() -> None:
    evidence = RepositoryEvidence(
        paths=frozenset({"README.md"}),
        complete_tree=False,
        primary_language="Python",
    )

    health = assess_repository(evidence)

    assert health.state_for(HealthDimension.TESTS) is HealthState.UNKNOWN
    assert health.state_for(HealthDimension.CI) is HealthState.UNKNOWN
    assert health.state_for(HealthDimension.SECURITY) is HealthState.UNKNOWN
    assert health.state_for(HealthDimension.REPRODUCIBILITY) is HealthState.UNKNOWN


def test_readme_only_is_partial_documentation() -> None:
    health = assess_repository(
        RepositoryEvidence(paths=frozenset({"README.md"}), complete_tree=True)
    )

    assert health.state_for(HealthDimension.DOCUMENTATION) is HealthState.PARTIAL


def test_tag_without_release_is_partial_release() -> None:
    health = assess_repository(
        RepositoryEvidence(paths=frozenset(), complete_tree=True, has_tag=True)
    )

    assert health.state_for(HealthDimension.RELEASE) is HealthState.PARTIAL


def test_resilient_assessment_preserves_successes_when_one_repository_fails() -> None:
    result = AssessmentService(_Gateway()).assess_many_resilient(
        ("owner/one", "owner/broken", "owner/two")
    )

    assert result.updated == ("owner/one", "owner/two")
    assert result.failed == (("owner/broken", "not accessible"),)
    assert result.assessments["owner/one"].state_for(HealthDimension.TESTS) is HealthState.COMPLETE


def test_concurrent_resilient_assessment_preserves_deterministic_output() -> None:
    result = AssessmentService(_Gateway()).assess_many_resilient(
        ("owner/two", "owner/broken", "owner/one"),
        max_workers=3,
    )

    assert result.updated == ("owner/one", "owner/two")
    assert result.failed == (("owner/broken", "not accessible"),)


def test_assessment_rejects_invalid_worker_bound() -> None:
    with pytest.raises(ValueError, match="max_workers"):
        AssessmentService(_Gateway()).assess_many_resilient(("owner/one",), max_workers=0)
