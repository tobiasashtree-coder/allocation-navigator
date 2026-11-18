"""Dashboard (M7): gleiche Zahlen wie die Kommandozeile, alle Reiter ohne Fehler."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from navigator.cli import app
from navigator.paths import ProjectPaths
from navigator.reporting.views import View, snapshot_path

APP = Path(__file__).resolve().parents[1] / "src" / "navigator" / "dashboard" / "app.py"
runner = CliRunner()


@pytest.fixture(scope="module")
def cli_outputs(demo_project: ProjectPaths) -> ProjectPaths:
    root = str(demo_project.root)
    for args in (
        ["regime", "run", "--method", "both", "--demo", "--root", root],
        ["debt", "run", "--demo", "--root", root, "--no-overlay"],
        ["recommend", "--demo", "--root", root, "--simulations", "5"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    return demo_project


def test_view_roundtrip(tmp_path: Path) -> None:
    frame = pd.DataFrame({"x": [0.1234567890123, 2.0]}, index=pd.Index(["a", "b"], name="asset"))
    path = View("t", {"f": frame}, {"v": 1.5}).save(tmp_path / "s.json")
    loaded = View.load(path)
    assert loaded.values == {"v": 1.5}
    np.testing.assert_allclose(loaded.tables["f"]["x"], frame["x"], rtol=0, atol=1e-15)


def test_dashboard_shows_cli_numbers(
    cli_outputs: ProjectPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Abnahme M7: Zielgewichte im Dashboard = Zielgewichte der Kommandozeile (CSV)."""
    monkeypatch.setenv("NAVIGATOR_ROOT", str(cli_outputs.root))
    monkeypatch.setenv("NAVIGATOR_DEMO", "1")
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == [
        "Übersicht",
        "Regime",
        "Schuldenzyklus",
        "Empfehlungen",
        "Backtest",
        "Daten und Qualität",
    ]
    tables = [df.value for df in at.dataframe if "Ziel %" in df.value.columns]
    assert tables, "Tabelle der Zielgewichte fehlt"
    shown = tables[0]["Ziel %"] / 100
    cli = pd.read_csv(cli_outputs.reports / "recommend_targets.csv", index_col=0)
    np.testing.assert_allclose(
        shown.to_numpy(), cli.loc[shown.index, "ab+overlay"].to_numpy(), rtol=0, atol=1e-12
    )
    snapshot = View.load(snapshot_path(cli_outputs.reports, "recommend"))
    for key, ok in snapshot.values["checks"]["ab+overlay"].items():
        assert ok, key
    assert any("DEMO-DATEN" in e.value for e in at.error)


def test_dashboard_other_variant_matches(
    cli_outputs: ProjectPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NAVIGATOR_ROOT", str(cli_outputs.root))
    monkeypatch.setenv("NAVIGATOR_DEMO", "1")
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("a").run()
    at.sidebar.toggle[0].set_value(False).run()
    assert not at.exception
    shown = next(df.value for df in at.dataframe if "Ziel %" in df.value.columns)["Ziel %"] / 100
    cli = pd.read_csv(cli_outputs.reports / "recommend_targets.csv", index_col=0)
    np.testing.assert_allclose(shown.to_numpy(), cli.loc[shown.index, "a"].to_numpy(), atol=1e-12)
    assert not at.sidebar.warning, "keine Szenario-Warnung ohne Änderung der Einstellungen"
