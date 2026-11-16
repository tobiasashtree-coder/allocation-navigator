"""Laufprotokoll: jeder Lauf mit Zeitstempel und Konfigurations-Hash."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from navigator import __version__


def utc_now() -> datetime:
    """Aktuelle Zeit in UTC (eigene Funktion, damit Tests sie ersetzen können)."""
    return datetime.now(UTC)


def write_run(runs_dir: Path, command: str, config_hash: str, summary: dict[str, Any]) -> Path:
    """Hängt einen Eintrag an ``runs.jsonl`` an und liefert den Pfad der Datei."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": utc_now().isoformat(timespec="seconds"),
        "command": command,
        "config_hash": config_hash,
        "version": __version__,
        "summary": summary,
    }
    path = runs_dir / "runs.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return path
