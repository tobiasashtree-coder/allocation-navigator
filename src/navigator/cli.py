"""Kommandozeile des Allokations-Navigators.

Die Kommandozeile enthält keine eigene Logik; sie ruft nur das Paket ``navigator`` auf.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from navigator import __version__
from navigator.config import AppConfig, load_config
from navigator.paths import ProjectPaths, project_paths

app = typer.Typer(
    help="Strategischer Asset-Allocation-Navigator nach Dalio-Zyklen.",
    no_args_is_help=True,
    add_completion=False,
)
data_app = typer.Typer(help="Datenschicht: abrufen, prüfen, Quellen ansehen.", no_args_is_help=True)
infra_app = typer.Typer(
    help="Eckwerte privater Infrastruktur: importieren, bestätigen, erfassen.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Konfiguration prüfen.", no_args_is_help=True)
app.add_typer(data_app, name="data")
app.add_typer(config_app, name="config")
data_app.add_typer(infra_app, name="infra")

DemoOption = Annotated[
    bool,
    typer.Option(
        "--demo", help="Synthetische Demo-Daten ohne Netzzugriff (eigener Ordner data_demo)."
    ),
]
RootOption = Annotated[
    Path | None,
    typer.Option("--root", help="Projektwurzel (Standard: automatisch bzw. NAVIGATOR_HOME)."),
]

LATER = {
    "regime": "M2/M3",
    "recommend": "M5",
    "backtest": "M6",
    "report": "M6/M8",
    "dashboard": "M7",
    "monthly": "M8",
}


def _setup(root: Path | None, demo: bool) -> tuple[AppConfig, ProjectPaths]:
    paths = project_paths(root, demo=demo)
    load_dotenv(paths.root / ".env")
    paths.ensure()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(paths.runs / "navigator.log", encoding="utf-8"),
        ],
        force=True,
    )
    return load_config(paths.config), paths


@app.command()
def version() -> None:
    """Zeigt die Version."""
    typer.echo(f"allocation-navigator {__version__}")


@config_app.command("check")
def config_check(root: RootOption = None) -> None:
    """Validiert alle YAML-Dateien und zeigt den Konfigurations-Hash."""
    config, paths = _setup(root, demo=False)
    assets = config.universe.enabled_assets()
    typer.echo(f"Konfiguration in {paths.config} ist gültig.")
    typer.echo(f"Hash: {config.config_hash}")
    typer.echo(f"Assetklassen: {len(assets)} eingeschaltet von {len(config.universe.assets)}")
    supported = ", ".join(config.currency.supported)
    typer.echo(f"Basiswährung: {config.currency.base} (unterstützt: {supported})")
    typer.echo(f"Indikatoren: {len(config.indicators.indicators)}")


@data_app.command("update")
def data_update(
    demo: DemoOption = False,
    root: RootOption = None,
    only: Annotated[
        str | None, typer.Option("--only", help="Nur Reihen, deren Name diesen Text enthält.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Cache ignorieren, alles neu laden.")
    ] = False,
) -> None:
    """Lädt alle Reihen, pflegt den Point-in-Time-Speicher und legt einen Snapshot an."""
    from navigator.data.pipeline import results_frame, update_data

    config, paths = _setup(root, demo)
    results = update_data(config, paths, only=only, force=force)
    frame = results_frame(results)
    counts = frame["status"].value_counts().to_dict()
    typer.echo("")
    typer.echo("Abruf beendet: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    failed = [r for r in results if r.status == "fehlgeschlagen" and not r.optional]
    for result in failed:
        typer.echo(f"  FEHLT  {result.key}: {result.message}")
    if demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine echten Marktdaten.")
    if failed:
        raise typer.Exit(code=1)


@data_app.command("validate")
def data_validate(demo: DemoOption = False, root: RootOption = None) -> None:
    """Prüft die gespeicherten Daten und schreibt den Validierungsbericht."""
    from navigator.data.pipeline import run_validation

    config, paths = _setup(root, demo)
    report = run_validation(config, paths)
    markdown_path, html_path = report.write(paths.reports)
    typer.echo(
        f"{report.count('Fehler')} Fehler, {report.count('Warnung')} Warnungen, "
        f"{report.count('Hinweis')} Hinweise."
    )
    for note in report.notes:
        typer.echo(note)
    typer.echo(f"Bericht: {markdown_path} und {html_path}")
    if report.count("Fehler"):
        raise typer.Exit(code=1)


@data_app.command("sources")
def data_sources(
    demo: DemoOption = False,
    root: RootOption = None,
    probe: Annotated[
        bool,
        typer.Option(
            "--probe",
            help="Jede Reihe bei JEDER nutzbaren Quelle abrufen (prüft Ticker, IDs, Startdaten).",
        ),
    ] = False,
) -> None:
    """Zeigt Quellen und Reihen; mit --probe werden alle Ticker und Reihen-IDs live geprüft."""
    from navigator.data.pipeline import (
        make_cache,
        make_providers,
        series_table,
        sources_table,
        update_data,
    )
    from navigator.data.validate import markdown_table

    config, paths = _setup(root, demo)
    providers = make_providers(config, paths)
    if probe:
        update_data(config, paths, providers=providers, all_sources=True, snapshot=False)
    sources = sources_table(config, providers)
    series = series_table(config, make_cache(config, paths))
    text = "\n".join(
        [
            "# Quellen und Reihen",
            "",
            "## Quellen",
            "",
            markdown_table(sources),
            "## Rohreihen je Quelle",
            "",
            markdown_table(series),
        ]
    )
    paths.reports.mkdir(parents=True, exist_ok=True)
    target = paths.reports / "sources_latest.md"
    target.write_text(text, encoding="utf-8")
    typer.echo(markdown_table(sources))
    missing = series[series["vorhanden"] == "NEIN"] if len(series) else series
    typer.echo(f"{len(series)} Reihen-Quellen-Paare, davon {len(missing)} ohne Daten.")
    if not probe and len(missing):
        typer.echo("Hinweis: Ersatzquellen werden nur mit --probe vollständig abgerufen.")
    for row in missing.itertuples(index=False):
        typer.echo(f"  FEHLT  {row.Reihe}  [{row.Quelle}: {row.Symbol}]")
    typer.echo(f"Tabelle: {target}")


def _infra_provider(root: Path | None, demo: bool):  # type: ignore[no-untyped-def]
    from navigator.data.providers.private_infra import PrivateInfraProvider

    config, paths = _setup(root, demo)
    cfg = config.sources.sources["private_infra"]
    return PrivateInfraProvider(cfg, store_path=paths.processed / "private_infra.json")


@infra_app.command("import")
def infra_import(root: RootOption = None) -> None:
    """Ruft die konfigurierten Seiten ab; neue Werte warten danach auf Bestätigung."""
    for message in _infra_provider(root, False).import_published():
        typer.echo(message)


@infra_app.command("list")
def infra_list(root: RootOption = None) -> None:
    """Zeigt alle Eckwerte mit Status."""
    values = _infra_provider(root, False).store.load()
    if not values:
        typer.echo("Noch keine Einträge.")
    for v in values:
        head = f"{v.id}  {v.status:<9}  {v.series:<24} {v.period:<8} {v.value:>8} {v.unit:<10}"
        typer.echo(f"{head} {v.source_url}")


@infra_app.command("confirm")
def infra_confirm(entry_id: str, root: RootOption = None) -> None:
    """Bestätigt einen Eintrag; erst danach wird er verwendet."""
    entry = _infra_provider(root, False).store.set_status(entry_id, "confirmed")
    typer.echo(f"Bestätigt: {entry.series} {entry.period} = {entry.value} {entry.unit}")


@infra_app.command("reject")
def infra_reject(entry_id: str, root: RootOption = None) -> None:
    """Verwirft einen Eintrag."""
    entry = _infra_provider(root, False).store.set_status(entry_id, "rejected")
    typer.echo(f"Verworfen: {entry.series} {entry.period}")


@infra_app.command("add")
def infra_add(
    series: str,
    period: str,
    value: float,
    unit: Annotated[
        str, typer.Option(help="pct_12m, pct_quarter, pct_month oder pence")
    ] = "pct_12m",
    source: Annotated[str, typer.Option(help="Quelle (URL)")] = "manuell",
    root: RootOption = None,
) -> None:
    """Erfasst einen Eckwert von Hand (direkt bestätigt). Periode z. B. 2026-Q1 oder 2026-09."""
    store = _infra_provider(root, False).store
    entry = store.add(
        series, period, value, unit, source, status="confirmed", note="manuell erfasst"
    )
    typer.echo("Bereits vorhanden." if entry is None else f"Erfasst als {entry.id}.")


def _not_yet(name: str) -> None:
    typer.echo(
        f"'navigator {name}' ist noch nicht implementiert (Meilenstein {LATER[name]}). "
        "Stand: M0 und M1 (Datenschicht). Siehe docs/checkpoints/M1.md."
    )
    raise typer.Exit(code=2)


@app.command()
def regime() -> None:
    """Regime-Erkennung nach Methode A, B oder beiden (folgt in M2/M3)."""
    _not_yet("regime")


@app.command()
def recommend() -> None:
    """Empfehlungen in drei Formen, mit und ohne Overlay (folgt in M5)."""
    _not_yet("recommend")


@app.command()
def backtest() -> None:
    """Walk-Forward-Backtest mit Vergleichsstrategien (folgt in M6)."""
    _not_yet("backtest")


@app.command()
def report() -> None:
    """Monatsbericht als HTML (folgt in M6/M8)."""
    _not_yet("report")


@app.command()
def dashboard() -> None:
    """Interaktives Dashboard (folgt in M7)."""
    _not_yet("dashboard")


@app.command()
def monthly() -> None:
    """Monatslauf: Update, Regime, Empfehlung, Bericht (folgt in M8)."""
    _not_yet("monthly")


if __name__ == "__main__":
    app()
