"""Classify failures at the local JSON file boundary."""

from __future__ import annotations

import json
from pathlib import Path

from dataexcept import DataLoadingError, FileReadError, FileWriteError, wrap


def read_json(path: Path) -> object:
    """Read JSON while keeping filesystem and decoding failures distinct."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise wrap(exc, FileReadError, path=str(path)) from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise wrap(exc, DataLoadingError, source=str(path)) from exc


def write_json_atomically(path: Path, payload: object) -> None:
    """Replace a JSON document only after its temporary file is complete."""

    document = json.dumps(payload, indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(document, encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise wrap(exc, FileWriteError, path=str(path)) from exc
