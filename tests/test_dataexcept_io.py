"""Local JSON failures retain a useful DataExcept type and original cause."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from dataexcept import DataLoadingError, FileReadError, FileWriteError

from project_reminders.domain.models import Portfolio
from project_reminders.infrastructure.json_store import JsonPortfolioRepository
from project_reminders.infrastructure.metadata_inventory import (
    load_metadata_inventory,
    write_metadata_inventory,
)
from project_reminders.infrastructure.project_metadata import load_project_metadata


@pytest.mark.parametrize("loader", ["portfolio", "inventory", "project_metadata"])
def test_malformed_json_identifies_source_and_decode_cause(tmp_path: Path, loader: str) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"broken":', encoding="utf-8")

    with pytest.raises(DataLoadingError) as caught:
        if loader == "portfolio":
            JsonPortfolioRepository(path).load()
        elif loader == "inventory":
            load_metadata_inventory(path)
        else:
            load_project_metadata(path)

    assert caught.value.source == str(path)
    assert isinstance(caught.value.original, json.JSONDecodeError)
    assert caught.value.__cause__ is caught.value.original


def test_portfolio_read_permission_failure_preserves_os_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "projects.json"
    path.write_text("{}", encoding="utf-8")
    original = PermissionError("read denied")

    def fail_read(self: Path, *, encoding: str) -> str:
        raise original

    monkeypatch.setattr(Path, "read_text", fail_read)
    with pytest.raises(FileReadError) as caught:
        JsonPortfolioRepository(path).load()

    assert caught.value.path == str(path)
    assert caught.value.original is original
    assert caught.value.__cause__ is original


@pytest.mark.parametrize("writer", ["portfolio", "inventory"])
def test_failed_replace_keeps_existing_document_and_identifies_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    path = tmp_path / "existing.json"
    path.write_text("original\n", encoding="utf-8")
    original = PermissionError("replace denied")

    def fail_replace(self: Path, target: Path) -> Path:
        raise original

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(FileWriteError) as caught:
        if writer == "portfolio":
            JsonPortfolioRepository(path).save(Portfolio())
        else:
            write_metadata_inventory(path, (), ())

    assert path.read_text(encoding="utf-8") == "original\n"
    assert caught.value.path == str(path)
    assert caught.value.original is original
    assert caught.value.__cause__ is original


def test_validator_handles_malformed_json_as_invalid_metadata(tmp_path: Path) -> None:
    path = tmp_path / ".project.json"
    path.write_text("{", encoding="utf-8")
    script = Path(__file__).resolve().parent.parent / "scripts" / "validate_project_metadata.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "line 1 column 2" in result.stdout
