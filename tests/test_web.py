"""Server-rendered dashboard tests."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from project_reminders.web import create_app


def _write_portfolio(root: Path) -> None:
    data_dir = root / "data"
    data_dir.mkdir()
    (data_dir / "projects.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-09-07T06:17:07+00:00",
                "projects": [
                    {
                        "id": "alpha",
                        "name": "Alpha",
                        "repository": "owner/alpha",
                        "status": "hardening",
                        "priority": "high",
                        "summary": "Alpha summary",
                        "health": {"tests": "complete", "lint": "missing"},
                        "operational": {
                            "ci_state": "failing",
                            "open_pull_requests": [
                                {"number": 7, "title": "Repair CI", "draft": False}
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "project_metadata.json").write_text(
        json.dumps(
            {
                "version": 1,
                "migrated": {
                    "owner/alpha": {
                        "schema_version": 1,
                        "project_type": "research",
                        "strategic_themes": ["mathematical-research"],
                        "planning_horizon": "now",
                        "wip": True,
                        "milestone": {
                            "id": "M04",
                            "title": "Complete identifiability analysis",
                            "status": "wip",
                            "acceptance_done": 1,
                            "acceptance_total": 2,
                        },
                        "dependency_count": 0,
                        "outcome_count": 1,
                    }
                },
                "missing": [],
            }
        ),
        encoding="utf-8",
    )


def test_dashboard_renders_control_plane_sections(tmp_path: Path) -> None:
    _write_portfolio(tmp_path)

    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    assert "Portfolio control plane" in response.text
    assert "Attention queue" in response.text
    assert "Engineering health matrix" in response.text
    assert "Live operations" in response.text
    assert "Alpha" in response.text
    assert "1 visible" in response.text
    assert "metadata-migrated" in response.text
    assert "research/now" in response.text
    assert 'data-ci="failing"' in response.text
    assert 'data-health="complete unknown missing' in response.text


def test_project_detail_renders_control_panel(tmp_path: Path) -> None:
    _write_portfolio(tmp_path)

    response = TestClient(create_app(tmp_path)).get("/projects/alpha")

    assert response.status_code == 200
    assert "Project control panel" in response.text
    assert "Why this needs attention" in response.text
    assert "Latest CI is failing" in response.text
    assert "Known missing engineering health: lint" in response.text
    assert "Repository-local planning metadata" in response.text
    assert "Complete identifiability analysis" in response.text
    assert "Acceptance progress" in response.text
    assert "1/2" in response.text
    assert "Engineering maturity" in response.text
    assert "https://github.com/owner/alpha" in response.text
