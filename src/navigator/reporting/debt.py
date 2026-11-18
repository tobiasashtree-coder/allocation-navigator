"""Bericht zum langfristigen Schuldenzyklus (Spezifikation 6): Score, Phasen, Overlay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from navigator.allocation.overlay import (
    OverlayResult,
    apply_overlay,
    provisional_base,
    usd_share,
)
from navigator.config import AppConfig
from navigator.data.pipeline import make_cache, make_providers
from navigator.data.pit import PitStore
from navigator.data.universe import SeriesLoader, UniverseBuilder
from navigator.data.validate import markdown_table
from navigator.features.debt_stress import (
    DebtStressResult,
    episode_check,
    phase_distance,
    run_debt_stress,
)
from navigator.paths import ProjectPaths
from navigator.runlog import utc_now, write_run

COUNTRY_NAMES = {
    "US": "USA",
    "DE": "Deutschland",
    "FR": "Frankreich",
    "IT": "Italien",
    "JP": "Japan",
    "GB": "Vereinigtes Königreich",
    "CN": "China",
}


@dataclass
class DebtRun:
    """Ergebnis eines Laufs: Score, Phasen und Overlay."""

    result: DebtStressResult
    overlay: OverlayResult | None
    current: pd.DataFrame
    warnings: list[str]


def _fmt(value: object, pattern: str = "{:.1f}") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "–"
    if isinstance(value, (int, float, np.floating)):
        return pattern.format(float(value)).replace(".", ",")
    return str(value)


def current_table(
    config: AppConfig, result: DebtStressResult, asof: pd.Timestamp | None
) -> pd.DataFrame:
    """Stand je Land: Score, gemessene und manuelle Phase, Abstand."""
    current = result.current(asof)
    rows = []
    for country in config.debt_cycle.score.countries:
        manual = config.debt_cycle.assessments.get(country, {}).get("phase")
        row = current.loc[country] if country in current.index else pd.Series(dtype="object")
        measured = row.get("phase") if not row.empty else None
        measured = (
            None
            if measured is None or (isinstance(measured, float) and np.isnan(measured))
            else measured
        )
        years = (
            [v for k, v in row.items() if str(k).endswith(":year") and pd.notna(v)]
            if not row.empty
            else []
        )
        rows.append(
            {
                "Land": country,
                "Score": float(row.get("score", np.nan)) if not row.empty else np.nan,
                "gemessene Phase": measured or "–",
                "manuelle Phase": manual or "–",
                "Abstand": phase_distance(measured, manual),
                "Bestandteile": int(row.get("components", 0))
                if not row.empty and pd.notna(row.get("components"))
                else 0,
                "jüngstes Datenjahr": int(max(years)) if years else None,
            }
        )
    return pd.DataFrame(rows).set_index("Land")


def run_debt(
    config: AppConfig,
    paths: ProjectPaths,
    asof: pd.Timestamp | None = None,
    with_overlay: bool = True,
) -> DebtRun:
    """Score, Phasen und Overlay für den Stichtag."""
    store = PitStore(paths.pit)
    result = run_debt_stress(config, store, asof)
    table = current_table(config, result, asof)
    warnings = []
    limit = config.debt_cycle.score.warn_if_phases_apart
    for country, row in table.iterrows():
        distance = row["Abstand"]
        if distance is not None and pd.notna(distance) and int(distance) > limit:
            warnings.append(
                f"{COUNTRY_NAMES.get(str(country), country)}: gemessene Phase "
                f"„{row['gemessene Phase']}“ weicht um {int(distance)} Phasen von der manuellen "
                f"Einschätzung „{row['manuelle Phase']}“ ab."
            )
    warnings += [f"Daten: {issue}" for issue in result.issues]
    if not result.thresholds_fixed:
        warnings.append(
            "Phasenschwellen sind noch nicht in config/debt_cycle.yaml festgeschrieben; "
            "verwendet werden die gerade kalibrierten Werte."
        )
    overlay = None
    if with_overlay:
        loader = SeriesLoader(make_cache(config, paths), make_providers(config, paths))
        universe = UniverseBuilder(config, loader).build(config.currency.base, asof)
        returns = universe.returns
        if asof is not None:
            returns = returns[returns.index <= asof]
        base = provisional_base(returns, config)
        measured = {
            c: (None if r["gemessene Phase"] == "–" else str(r["gemessene Phase"]))
            for c, r in table.iterrows()
        }
        scores = {str(c): float(r["Score"]) for c, r in table.iterrows()}
        overlay = apply_overlay(base, config, measured, scores)
    return DebtRun(result, overlay, table, warnings)


def _history_table(result: DebtStressResult, countries: list[str]) -> pd.DataFrame:
    years = [*range(1950, 2021, 10), 2022, 2024, 2025]
    rows = {}
    for country in countries:
        frame = result.year_end.get(country, pd.DataFrame())
        cells = {}
        for year in years:
            stamp = pd.Timestamp(year, 12, 31)
            if frame.empty or stamp not in frame.index:
                cells[str(year)] = ""
                continue
            phase = frame.at[stamp, "phase"] if "phase" in frame.columns else None
            score = frame.at[stamp, "score"] if "score" in frame.columns else np.nan
            cells[str(year)] = (
                ""
                if phase is None or pd.isna(score)
                else f"{_fmt(score, '{:.0f}')} {str(phase).split(' ')[0]}"
            )
        rows[country] = cells
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("Land")


def _components_table(
    config: AppConfig, result: DebtStressResult, asof: pd.Timestamp | None
) -> pd.DataFrame:
    current = result.current(asof)
    rows = {}
    for name, component in config.debt_cycle.score.components.items():
        cells = {}
        for country in config.debt_cycle.score.countries:
            if country not in current.index:
                cells[country] = ""
                continue
            row = current.loc[country]
            value, pct, year = row.get(name), row.get(f"p:{name}"), row.get(f"{name}:year")
            if value is None or pd.isna(value):
                cells[country] = ""
                continue
            shown = f"{_fmt(value)} ({_fmt(pct * 100 if pd.notna(pct) else np.nan, '{:.0f}')})"
            if pd.notna(year):
                shown += f" {int(year)}"
            cells[country] = shown
        rows[component.label] = cells
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("Bestandteil")


def _coverage_table(
    result: DebtStressResult, countries: list[str], panel: list[str]
) -> pd.DataFrame:
    coverage = result.coverage
    if coverage.empty:
        return coverage
    rows: dict[str, dict[str, str]] = {}
    for _, row in coverage.iterrows():
        owner = str(row["owner"])
        if owner not in countries and owner not in ("USA", "DEU"):
            continue
        cell = f"{row['first']}–{row['last']} ({_fmt(row['median'])}; {_fmt(row['last_value'])})"
        rows.setdefault(str(row["input"]), {})[owner] = cell
    order = [c for c in countries] + [c for c in ("USA", "DEU") if c in panel]
    frame = (
        pd.DataFrame.from_dict(rows, orient="index")
        .reindex(columns=order)
        .astype(object)
        .fillna("")
    )
    return frame.sort_index().rename_axis("Rohreihe")


def write_report(
    config: AppConfig, paths: ProjectPaths, run: DebtRun, asof: pd.Timestamp | None
) -> tuple[Path, Path]:
    """Bericht ``reports/debt_latest.md`` und Historie ``reports/debt_history.csv``."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    result, score = run.result, config.debt_cycle.score
    lines = ["# Langfristiger Schuldenzyklus", ""]
    if paths.demo:
        lines += ["> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte.", ""]
    lines += [
        f"Erstellt: {utc_now().isoformat(timespec='seconds')} · Stichtag: "
        f"{(asof or pd.Timestamp.today()).date()} · Konfigurations-Hash: "
        f"`{config.config_hash[:12]}`",
        "",
        "Score 0 bis 100: gewichtetes Mittel der Perzentile aller verfügbaren Bestandteile "
        "gegen die bis zum Stichtag bekannte Verteilung im Referenzpanel (JST-Länder und die "
        "Länder des Tools). Jahreswerte; Fiskaldaten gelten ab Ende April des Folgejahres.",
        "",
    ]
    if run.warnings:
        lines += ["## Warnungen", ""] + [f"- {w}" for w in run.warnings] + [""]
    lines += ["## Stand je Land", "", markdown_table(run.current, "{:.1f}")]
    for country, entry in config.debt_cycle.assessments.items():
        if entry.get("phase"):
            lines += [
                f"**Manuelle Einschätzung {COUNTRY_NAMES.get(country, country)}** "
                f"({entry.get('date', '')}): {entry['phase']}. {entry.get('rationale', '')}",
                "",
                f"*Gegenposition:* {entry.get('counter_position', '–')}",
                "",
            ]
    lines += [
        "## Bestandteile (Wert, Perzentil in Klammern, Datenjahr)",
        "",
        markdown_table(_components_table(config, result, asof)),
        "## Kalibrierung der Phasenschwellen",
        "",
    ]
    cal = result.calibration
    status = (
        "festgeschrieben in config/debt_cycle.yaml"
        if result.thresholds_fixed
        else "kalibriert, noch nicht festgeschrieben"
    )
    lines += [
        f"Verwendete Schwellen: **{' | '.join(_fmt(t) for t in result.thresholds)}** ({status}).",
        "",
    ]
    if not cal.empty:
        n = cal.attrs.get("n")
        years = cal.attrs.get("years")
        lines += [
            f"Quantile der Score-Verteilung über {n} Länder-Jahre "
            f"({years[0]}–{years[1]}, Jahresenden, alle Länder des Panels und des Tools):",
            "",
            markdown_table(cal, "{:.2f}"),
        ]
    lines += [
        "Zusatzregel: Liegt die Staatsverschuldung über dem "
        f"{score.rules.high_debt_percentile:.0%}-Perzentil und ist die Quote in 5 Jahren um "
        f"mindestens {-score.rules.deleveraging_pp:.0f} Pp. gesunken (ohne positives r − g) "
        "oder die Zentralbankbilanz in 3 Jahren um mindestens "
        f"{score.rules.monetization_pp:.0f} Pp. des BIP "
        "gewachsen, gilt „Entschuldung / Monetarisierung“. „Neuordnung“ ist nur manuell setzbar.",
        "",
        "## Episoden-Check (qualitativ)",
        "",
        markdown_table(episode_check(result, score), "{:.2f}"),
        "## Phasen im Zeitverlauf (Jahresende: Score und Phase)",
        "",
        markdown_table(_history_table(result, score.countries)),
    ]
    if run.overlay is not None:
        overlay = run.overlay
        lines += ["## Wirkung des Overlays auf die Allokation", ""]
        for lam in overlay.lambdas:
            lines.append(
                f"- {COUNTRY_NAMES.get(lam.country, lam.country)}: Phase "
                f"„{lam.phase or 'unbekannt'}“ ({lam.source}), λ = {_fmt(lam.value, '{:.2f}')}"
            )
        lines += [
            "",
            "Basis vorläufig: inverse Volatilität je Umfeldkorb über 60 Monate in "
            f"{config.currency.base}; ab M5 Risikoparität mit Ledoit-Wolf-Kovarianz (7.1).",
            "",
            markdown_table(overlay.table(config), "{:.1f}"),
            "Ungesichertes USD-Exposure: ohne Overlay "
            f"{_fmt(usd_share(overlay.base, config) * 100)} %, "
            f"mit Overlay {_fmt(usd_share(overlay.weights, config) * 100)} %"
            + (
                f"; Obergrenze laut Overlay {_fmt(overlay.usd_cap * 100)} % "
                "(Umsetzung über die Währungssicherung in M5)."
                if overlay.usd_cap is not None
                else "."
            ),
            "",
        ]
        if overlay.notes:
            lines += [f"- {n}" for n in overlay.notes] + [""]
    lines += [
        "## Datenabdeckung (erstes–letztes Jahr, Median; letzter Wert)",
        "",
        markdown_table(_coverage_table(result, score.countries, score.panel)),
        "Quellen: IMF DataMapper (WEO, Fiscal Monitor, Public Finances in Modern History), "
        "BIS, FRED (OECD-Zinsen, Kim-Wright-Laufzeitprämie, Notenbankbilanzen), Jordà-Schularick-"
        "Taylor Macrohistory Database (Jordà, Schularick, Taylor 2017).",
        "",
    ]
    md_path = paths.reports / "debt_latest.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    frames = []
    for country, frame in result.monthly.items():
        if frame.empty:
            continue
        cols = [c for c in frame.columns if not c.endswith(":year")]
        part = frame[cols].copy()
        part.insert(0, "country", country)
        frames.append(part)
    csv_path = paths.reports / "debt_history.csv"
    if frames:
        pd.concat(frames).rename_axis("date").to_csv(csv_path)
    else:
        csv_path.write_text("", encoding="utf-8")
    write_run(
        paths.runs,
        "debt run",
        config.config_hash,
        {
            "demo": paths.demo,
            "thresholds": result.thresholds,
            "thresholds_fixed": result.thresholds_fixed,
            "phases": {str(c): str(r["gemessene Phase"]) for c, r in run.current.iterrows()},
            "warnings": len(run.warnings),
        },
    )
    return md_path, csv_path
