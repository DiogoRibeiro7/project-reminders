"""Architecture guards for unified Project state synchronization ownership."""

from pathlib import Path


def test_project_metric_transport_does_not_manage_project_views() -> None:
    source = Path("scripts/project_metric_fields.py").read_text(encoding="utf-8")

    assert "Attention Queue" not in source
    assert "projectsV2/" not in source
    assert "updateProjectV2View" not in source
    assert "visible_fields" not in source
    assert "sort_by" not in source


def test_board_workflow_has_one_project_state_scan() -> None:
    workflow = Path(".github/workflows/sync-code-project-board.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("python scripts/sync_project_state.py") == 1
    assert "sync_project_board_paginated.py" not in workflow
    assert "sync_project_metrics.py" not in workflow


def test_project_state_query_contains_card_and_metric_evidence() -> None:
    source = Path("scripts/sync_project_state.py").read_text(encoding="utf-8")

    assert "... on DraftIssue { id title body }" in source
    assert "... on ProjectV2ItemFieldNumberValue" in source
    assert "... on ProjectV2ItemFieldDateValue" in source
    assert source.count("items(first: 100, after: $cursor)") == 1
