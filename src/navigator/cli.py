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
regime_app = typer.Typer(help="Regime-Erkennung nach Methode A und B.", no_args_is_help=True)
app.add_typer(regime_app, name="regime")
debt_app = typer.Typer(
    help="Langfristiger Schuldenzyklus: Score, Phasen, Overlay.", no_args_is_help=True
)
app.add_typer(debt_app, name="debt")
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


@data_app.command("inspect")
def data_inspect(
    dataset: str,
    root: RootOption = None,
    rows: Annotated[int, typer.Option(help="Anzahl Zeilen je Blatt")] = 14,
) -> None:
    """Zeigt Blätter und erste Zeilen eines statischen Datensatzes (zum Einrichten)."""
    from navigator.data.pipeline import make_providers
    from navigator.data.providers.static import StaticProvider, describe_content

    config, paths = _setup(root, demo=False)
    provider = make_providers(config, paths)["static"]
    assert isinstance(provider, StaticProvider)
    spec = provider.config.options.get("datasets", {}).get(dataset)
    if spec is None:
        typer.echo(f"Unbekannter Datensatz: {dataset}")
        raise typer.Exit(code=1)
    typer.echo(describe_content(provider.content(dataset, spec), rows))


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


@regime_app.command("run")
def regime_run(
    method: Annotated[str, typer.Option("--method", help="a, b oder both")] = "a",
    asof: Annotated[
        str | None, typer.Option("--asof", help="Stichtag JJJJ-MM-TT (Standard: heute)")
    ] = None,
    start: Annotated[str, typer.Option("--start", help="Beginn der Historie")] = "1960-01",
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Bestimmt das Regime je Monat und schreibt den Bericht nach reports/regime_a_latest.md."""
    import pandas as pd

    from navigator.regimes.method_a import current_state, load_and_run, write_report

    if method not in ("a", "b", "both"):
        typer.echo("--method muss a, b oder both sein.")
        raise typer.Exit(code=2)
    config, paths = _setup(root, demo)
    stamp = pd.Timestamp(asof) if asof else None
    result = load_and_run(config, paths, start, stamp)
    md_path, csv_path = write_report(config, paths, result, None)
    for key, value in current_state(result).items():
        shown = f"{value:+.2f}" if isinstance(value, float) else value
        typer.echo(f"{key:<22} {shown}")
    typer.echo(f"Bericht A: {md_path}; Historie: {csv_path}")
    if method in ("b", "both"):
        from navigator.data.pit import PitStore
        from navigator.regimes import method_b

        cmp = method_b.run_comparison(config, PitStore(paths.pit), result.dates, result)
        md_b, csv_b = method_b.write_report(config, paths, cmp)
        when = cmp.b.regime.last_valid_index()
        if when is not None:
            typer.echo(f"Methode B             {method_b.STATE_LABELS[cmp.b.label[when]]}")
            typer.echo(f"Überzeugung           {cmp.conviction[when]:.2f}")
            typer.echo(f"Begründung            {cmp.explanations.get(when, '')}")
        typer.echo(f"Übereinstimmung A/B   {cmp.agreement_rate:.0%}")
        typer.echo(f"Bericht B: {md_b}; Historie: {csv_b}")
    if demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte.")


@app.command()
def recommend(
    asof: Annotated[
        str | None,
        typer.Option("--asof", help="Stichtag JJJJ-MM-TT (Standard: letztes Monatsende)"),
    ] = None,
    overlay: Annotated[
        bool, typer.Option("--overlay/--no-overlay", help="Schuldenzyklus-Overlay einbeziehen")
    ] = True,
    portfolio: Annotated[
        Path | None, typer.Option("--portfolio", help="CSV mit Spalten asset,weight (aktuell)")
    ] = None,
    simulations: Annotated[
        int | None, typer.Option("--simulations", help="Resampling-Simulationen (Standard 500)")
    ] = None,
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Empfehlungen in drei Formen (Ampel, Tilts, Zielgewichte), mit und ohne Overlay."""
    import pandas as pd

    from navigator.allocation.recommend import load_and_recommend, write_report

    config, paths = _setup(root, demo)
    current = None
    if portfolio is not None:
        frame = pd.read_csv(portfolio)
        current = frame.set_index("asset")["weight"].astype(float)
        current = current / current.sum()
    stamp = pd.Timestamp(asof) if asof else None
    rec = load_and_recommend(config, paths, stamp, overlay, current, simulations)
    md, csv = write_report(config, paths, rec)
    from navigator.reporting.views import recommendation_view, snapshot_path

    recommendation_view(rec, config).save(snapshot_path(paths.reports, "recommend"))
    key = "ab+overlay" if "ab+overlay" in rec.variants else next(iter(rec.variants))
    variant = rec.variants[key]
    for asset, weight in variant.target.weights.sort_values(ascending=False).items():
        typer.echo(
            f"{asset:<24} Ziel {weight:6.1%}  Basis {rec.base.weights.get(asset, 0.0):6.1%}  "
            f"Ampel {variant.lights[asset]}"
        )
    failed = [k for k, v in variant.target.checks.items() if not v]
    typer.echo(
        "Restriktionen: " + ("alle eingehalten" if not failed else "VERLETZT: " + ", ".join(failed))
    )
    typer.echo(f"Bericht: {md}; Zielgewichte: {csv}")
    if paths.demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte.")


@app.command()
def backtest(
    asof: Annotated[str | None, typer.Option("--asof", help="Ende JJJJ-MM-TT")] = None,
    placebo: Annotated[
        int | None, typer.Option("--placebo", help="Placebo-Folgen (Standard 1000)")
    ] = None,
    simulations: Annotated[
        int | None, typer.Option("--simulations", help="Resampling je Entscheidung")
    ] = None,
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Backtest aller Vergleichsstrategien; Bericht reports/backtest_latest.html."""
    import pandas as pd

    from navigator.backtest.run import load_inputs, run_backtest, write_report

    config, paths = _setup(root, demo)
    end = pd.Timestamp(asof) if asof else pd.Timestamp.today().normalize() - pd.offsets.MonthEnd(1)
    inputs = load_inputs(config, paths, end)
    result = run_backtest(config, inputs, placebo, simulations)
    md, page = write_report(config, paths, result)
    from navigator.reporting.views import backtest_view, snapshot_path

    backtest_view(result, config).save(snapshot_path(paths.reports, "backtest"))
    typer.echo(f"Placebo-p-Wert {result.placebo_p:.3f} · Deflated Sharpe {result.deflated:.3f}")
    typer.echo(f"Bericht: {md}; HTML: {page}")
    if paths.demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte oder Strategien.")


@app.command()
def report(demo: DemoOption = False, root: RootOption = None) -> None:
    """Monatsbericht aus den vorhandenen Ergebnissen neu schreiben (ohne Neuberechnung)."""
    from navigator.monthly import write_monthly_report

    config, paths = _setup(root, demo)
    path = write_monthly_report(config, paths, None)
    typer.echo(f"Monatsbericht: {path} und {path.with_suffix('.html')}")


@app.command()
def dashboard(
    port: Annotated[int, typer.Option("--port", help="Port des Dashboards")] = 8501,
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Interaktives Dashboard (Streamlit) mit sechs Reitern; liest die Schnappschüsse."""
    import os
    import subprocess
    import sys

    _, paths = _setup(root, demo)
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    env = {**os.environ, "NAVIGATOR_ROOT": str(paths.root), "NAVIGATOR_DEMO": "1" if demo else "0"}
    command = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)]
    raise typer.Exit(subprocess.call(command, env=env))


@app.command()
def monthly(
    asof: Annotated[
        str | None,
        typer.Option("--asof", help="Stichtag JJJJ-MM-TT (Standard: letztes Monatsende)"),
    ] = None,
    backtest: Annotated[
        bool, typer.Option("--backtest/--no-backtest", help="Backtest mitrechnen (ca. 30 Min.)")
    ] = False,
    simulations: Annotated[
        int | None, typer.Option("--simulations", help="Resampling-Simulationen (Standard 500)")
    ] = None,
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Monatslauf ohne Eingriffe: Datenabruf, Validierung, Regime, Schuldenzyklus, Empfehlung,
    Monatsbericht (reports/monthly_latest.md und .html)."""
    import pandas as pd

    from navigator.monthly import run_monthly

    config, paths = _setup(root, demo)
    stamp = pd.Timestamp(asof) if asof else None
    run = run_monthly(config, paths, stamp, simulations, backtest)
    for step in run.steps:
        typer.echo(f"{step.name:<16} {step.status:<12} {step.seconds:6.0f} s  {step.message}")
    typer.echo(f"Monatsbericht: {paths.reports / 'monthly_latest.md'}")
    if paths.demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte.")
    if not run.ok:
        raise typer.Exit(code=1)


@debt_app.command("run")
def debt_run(
    asof: Annotated[
        str | None, typer.Option("--asof", help="Stichtag JJJJ-MM-TT (Standard: heute)")
    ] = None,
    overlay: Annotated[
        bool, typer.Option("--overlay/--no-overlay", help="Wirkung auf die Allokation zeigen")
    ] = True,
    demo: DemoOption = False,
    root: RootOption = None,
) -> None:
    """Schuldenstress-Score und Phase je Land, Kalibrierung, Overlay (reports/debt_latest.md)."""
    import pandas as pd

    from navigator.reporting.debt import run_debt, write_report

    config, paths = _setup(root, demo)
    stamp = pd.Timestamp(asof) if asof else None
    run = run_debt(config, paths, stamp, with_overlay=overlay)
    md_path, csv_path = write_report(config, paths, run, stamp)
    for country, row in run.current.iterrows():
        score = row["Score"]
        shown = "  –  " if pd.isna(score) else f"{score:5.1f}"
        typer.echo(
            f"{country}  Score {shown}  gemessen: {row['gemessene Phase']:<32} "
            f"manuell: {row['manuelle Phase']}"
        )
    thresholds = ", ".join(f"{t:.1f}" for t in run.result.thresholds)
    state = (
        "festgeschrieben" if run.result.thresholds_fixed else "kalibriert, nicht festgeschrieben"
    )
    typer.echo(f"Schwellen [{thresholds}] ({state})")
    for warning in run.warnings:
        typer.echo(f"WARNUNG: {warning}")
    typer.echo(f"Bericht: {md_path}; Historie: {csv_path}")
    if paths.demo:
        typer.echo("DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte.")


if __name__ == "__main__":
    app()
