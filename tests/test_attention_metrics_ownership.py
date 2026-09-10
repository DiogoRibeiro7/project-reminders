"""Architecture guard for attention metric synchronization ownership."""

from pathlib import Path


def test_attention_metric_writer_does_not_manage_project_views() -> None:
    source = Path("scripts/sync_attention_metrics.py").read_text(encoding="utf-8")

    assert "Attention Queue" not in source
    assert "projectsV2/" not in source
    assert "updateProjectV2View" not in source
    assert "visible_fields" not in source
    assert "sort_by" not in source
