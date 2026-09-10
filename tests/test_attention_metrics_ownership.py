"""Architecture guard for combined Project metric synchronization ownership."""

from pathlib import Path


def test_project_metric_writer_does_not_manage_project_views() -> None:
    source = Path("scripts/sync_project_metrics.py").read_text(encoding="utf-8")

    assert "Attention Queue" not in source
    assert "projectsV2/" not in source
    assert "updateProjectV2View" not in source
    assert "visible_fields" not in source
    assert "sort_by" not in source


def test_board_workflow_has_one_derived_metric_pass() -> None:
    workflow = Path(".github/workflows/sync-code-project-board.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("python scripts/sync_project_metrics.py") == 1
    assert "sync_portfolio_view_metrics.py" not in workflow
    assert "sync_attention_metrics.py" not in workflow
