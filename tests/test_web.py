"""Server-rendered dashboard tests."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from project_reminders.web import create_app


def test_dashboard_renders_control_plane_sections(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
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

    response = TestClient(create_app(tmp_path)).get("/")

    assert response.status_code == 200
    assert "Portfolio control plane" in response.text
    assert "Attention queue" in response.text
    assert "Engineering health matrix" in response.text
    assert "Live operations" in response.text
    assert "Alpha" in response.text
    assert "1 visible" in response.text
    assert 'data-ci="failing"' in response.text
    assert 'data-health="complete unknown missing' in response.text
