"""Monatsbetrieb (M8): ein vollständiger Lauf ohne Eingriffe."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from navigator.cli import app
from navigator.monthly import MonthlyRun, previous_snapshot
from navigator.paths import ProjectPaths

runner = CliRunner()


def test_monthly_runs_end_to_end(demo_project: ProjectPaths, tmp_path: Path) -> None:
    """Abnahme M8: ``navigator monthly`` läuft ohne Eingriffe durch und schreibt den Bericht."""
    root = tmp_path / "project"
    shutil.copytree(demo_project.root, root)
    result = runner.invoke(
        app,
        ["monthly", "--demo", "--root", str(root), "--simulations", "5", "--asof", "2026-09-30"],
    )
    assert result.exit_code == 0, result.output
    for step in (
        "Datenabruf",
        "Validierung",
        "Regime",
        "Schuldenzyklus",
        "Empfehlung",
        "Monatsbericht",
    ):
        assert step in result.output
    reports = root / "reports_demo"
    text = (reports / "monthly_latest.md").read_text(encoding="utf-8")
    assert "Empfohlene Gewichtung zum Stichtag 2026-09-30" in text
    assert "DEMO-DATEN" in text
    assert (reports / "monthly_latest.html").exists()
    assert (reports / "monthly" / "2026-09-30.md").exists()
    assert (reports / "snapshot" / "archive" / "recommend_2026-09-30.json").exists()
    # zweiter Monat: Vergleich mit dem Vormonat erscheint
    second = runner.invoke(
        app,
        ["monthly", "--demo", "--root", str(root), "--simulations", "5", "--asof", "2026-10-31"],
    )
    assert second.exit_code == 0, second.output
    text = (reports / "monthly_latest.md").read_text(encoding="utf-8")
    assert "Vormonat %" in text
    assert previous_snapshot(reports, "2026-10-31") is not None
    again = runner.invoke(app, ["report", "--demo", "--root", str(root)])
    assert again.exit_code == 0, again.output


def test_failed_step_is_reported_and_dependents_skipped() -> None:
    run = MonthlyRun()

    def boom() -> str:
        raise ValueError("kaputt")

    run.run("Regime", boom)
    run.run("Empfehlung", lambda: "ok", needs=["Regime"])
    run.run("Bericht", lambda: "ok")
    status = {s.name: s.status for s in run.steps}
    assert status == {"Regime": "Fehler", "Empfehlung": "übersprungen", "Bericht": "ok"}
    assert "kaputt" in run.steps[0].message
    assert not run.ok
    assert pd.notna(run.steps[0].seconds)
