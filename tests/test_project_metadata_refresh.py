"""Repository-local metadata refresh regression tests."""

from project_reminders.application.project_metadata import ProjectMetadataRefreshService
from project_reminders.domain.metadata import (
    AcceptanceCriterion,
    Milestone,
    MilestoneStatus,
    PlanningHorizon,
    ProjectMetadata,
    ProjectType,
)


class FakeMetadataGateway:
    """Deterministic metadata gateway used by refresh tests."""

    def project_metadata(self, repository: str) -> ProjectMetadata | None:
        if repository == "owner/missing":
            return None
        if repository == "owner/broken":
            raise ValueError("invalid metadata")
        return ProjectMetadata(
            project_type=ProjectType.RESEARCH,
            strategic_themes=("mathematical-research",),
            planning_horizon=PlanningHorizon.NOW,
            wip=True,
            milestone=Milestone(
                id="M01",
                title="Prove the result",
                status=MilestoneStatus.WIP,
                acceptance=(
                    AcceptanceCriterion(id="A1", text="Derive theorem", done=True),
                    AcceptanceCriterion(id="A2", text="Write proof", done=False),
                ),
            ),
        )


def test_refresh_separates_migrated_missing_and_failed() -> None:
    service = ProjectMetadataRefreshService(FakeMetadataGateway())

    result = service.refresh(
        ("owner/missing", "owner/valid", "owner/broken"),
        max_workers=2,
    )

    assert tuple(repository for repository, _ in result.snapshots) == ("owner/valid",)
    assert result.missing == ("owner/missing",)
    assert result.failed == (("owner/broken", "invalid metadata"),)
    assert result.succeeded == 2
    snapshot = result.snapshots[0][1]
    assert snapshot.milestone is not None
    assert snapshot.milestone.acceptance_done == 1
    assert snapshot.milestone.acceptance_total == 2
