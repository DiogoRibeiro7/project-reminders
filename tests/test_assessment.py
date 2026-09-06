"""Deterministic repository-assessment tests."""

from project_reminders.application.assessment import RepositoryEvidence, assess_repository
from project_reminders.domain.enums import HealthDimension, HealthState


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
    )

    health = assess_repository(evidence)

    assert health.state_for(HealthDimension.TESTS) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.CI) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.DOCUMENTATION) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.REPRODUCIBILITY) is HealthState.COMPLETE
    assert health.state_for(HealthDimension.RELEASE) is HealthState.COMPLETE


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
