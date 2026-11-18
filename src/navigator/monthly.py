"""Monatsbetrieb (Spezifikation M8): ein Lauf ohne manuelle Eingriffe.

``navigator monthly`` führt nacheinander aus: Datenabruf, Validierung, Regime (A und B),
Schuldenzyklus, Empfehlung und Monatsbericht. Scheitert ein Schritt, laufen die übrigen
weiter, soweit sie nicht auf ihm aufbauen; der Bericht nennt jeden Schritt mit Status. Der
Bericht steht in ``reports/monthly_latest.md`` (und ``.html``) und wird je Stichtag unter
``reports/monthly/`` archiviert, die Empfehlung unter ``reports/snapshot/archive/``.
"""

from __future__ import annotations

import html
import shutil
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from navigator.config import AppConfig
from navigator.data.validate import markdown_table
from navigator.paths import ProjectPaths
from navigator.reporting.views import View, allocation_table, snapshot_path
from navigator.runlog import utc_now, write_run

QUADRANT_LABELS = {
    "disinflationary_boom": "Disinflationärer Aufschwung",
    "reflation": "Reflation / Überhitzung",
    "deflationary_bust": "Deflationäre Rezession",
    "stagflation": "Stagflation",
}
MAIN_VARIANT = "ab+overlay"


@dataclass
class Step:
    """Ergebnis eines Schritts."""

    name: str
    status: str  # ok, Warnung, Fehler, übersprungen
    seconds: float
    message: str = ""


@dataclass
class MonthlyRun:
    """Alle Schritte eines Monatslaufs."""

    steps: list[Step] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(s.status in ("ok", "Warnung") for s in self.steps)

    def run(
        self, name: str, func: Callable[[], str | None], needs: list[str] | None = None
    ) -> bool:
        """Führt einen Schritt aus; ``needs`` nennt Schritte, die gelungen sein müssen."""
        failed = [n for n in needs or [] if not self._succeeded(n)]
        if failed:
            self.steps.append(Step(name, "übersprungen", 0.0, "wegen: " + ", ".join(failed)))
            return False
        start = time.monotonic()
        try:
            message = func() or ""
        except Exception as exc:
            detail = traceback.format_exception_only(type(exc), exc)[-1].strip()
            self.steps.append(Step(name, "Fehler", time.monotonic() - start, detail))
            return False
        status = "Warnung" if message.startswith("Warnung") else "ok"
        self.steps.append(Step(name, status, time.monotonic() - start, message))
        return True

    def _succeeded(self, name: str) -> bool:
        return any(s.name == name and s.status in ("ok", "Warnung") for s in self.steps)


def run_monthly(
    config: AppConfig,
    paths: ProjectPaths,
    asof: pd.Timestamp | None = None,
    simulations: int | None = None,
    with_backtest: bool = False,
) -> MonthlyRun:
    """Der vollständige Monatslauf."""
    from navigator.allocation.recommend import load_and_recommend
    from navigator.allocation.recommend import write_report as write_recommend
    from navigator.data.pipeline import run_validation, update_data
    from navigator.data.pit import PitStore
    from navigator.regimes import method_b
    from navigator.regimes.method_a import load_and_run
    from navigator.regimes.method_a import write_report as write_a
    from navigator.reporting.debt import run_debt
    from navigator.reporting.debt import write_report as write_debt
    from navigator.reporting.views import recommendation_view

    run = MonthlyRun()

    def step_update() -> str:
        results = update_data(config, paths)
        missing = [r.key for r in results if r.status == "fehlgeschlagen" and not r.optional]
        optional = [r.key for r in results if r.status == "fehlgeschlagen" and r.optional]
        stale = [r.key for r in results if r.status == "stale"]
        if missing:
            raise RuntimeError(f"Pflichtreihen fehlen: {', '.join(missing[:10])}")
        parts = [f"{len(results)} Reihen"]
        if optional or stale:
            parts.append(f"{len(optional)} optionale fehlgeschlagen, {len(stale)} aus dem Cache")
            run.notes["failed_optional"] = ", ".join(optional[:40])
            return "Warnung: " + "; ".join(parts)
        return "; ".join(parts)

    def step_validate() -> str:
        report = run_validation(config, paths)
        report.write(paths.reports)
        errors, warnings = report.count("Fehler"), report.count("Warnung")
        text = f"{errors} Fehler, {warnings} Warnungen, {report.count('Hinweis')} Hinweise"
        if errors:
            raise RuntimeError(text)
        return ("Warnung: " if warnings else "") + text

    def step_regime() -> str:
        result = load_and_run(config, paths, "1960-01", asof)
        write_a(config, paths, result, None)
        cmp = method_b.run_comparison(config, PitStore(paths.pit), result.dates, result)
        method_b.write_report(config, paths, cmp)
        when = cmp.b.regime.last_valid_index()
        return f"Übereinstimmung A/B {cmp.agreement_rate:.0%}" + (
            f", Überzeugung {cmp.conviction[when]:.2f}" if when is not None else ""
        )

    def step_debt() -> str:
        debt = run_debt(config, paths, asof, with_overlay=False)
        write_debt(config, paths, debt, asof)
        if debt.warnings:
            run.notes["debt_warnings"] = "\n".join(debt.warnings)
            return f"Warnung: {len(debt.warnings)} Hinweise zum Schuldenzyklus"
        return "ok"

    def step_recommend() -> str:
        rec = load_and_recommend(config, paths, asof, True, None, simulations)
        write_recommend(config, paths, rec)
        view = recommendation_view(rec, config)
        path = view.save(snapshot_path(paths.reports, "recommend"))
        archive = paths.reports / "snapshot" / "archive" / f"recommend_{view.values['asof']}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archive)
        failed = [k for k, ok in view.values["checks"].get(MAIN_VARIANT, {}).items() if not ok]
        if failed:
            return "Warnung: Restriktionen verletzt: " + ", ".join(failed)
        return f"Stichtag {view.values['asof']}"

    def step_backtest() -> str:
        from navigator.backtest.run import load_inputs, run_backtest
        from navigator.backtest.run import write_report as write_bt
        from navigator.reporting.views import backtest_view

        end = asof or (pd.Timestamp(utc_now().date()) - pd.offsets.MonthEnd(1))
        result = run_backtest(config, load_inputs(config, paths, pd.Timestamp(end)))
        write_bt(config, paths, result)
        backtest_view(result, config).save(snapshot_path(paths.reports, "backtest"))
        return f"Placebo-p-Wert {result.placebo_p:.3f}"

    if not run.run("Datenabruf", step_update):
        # ohne frische Daten keine Aussage: übrige Schritte entfallen (Regel 10)
        for name in ("Validierung", "Regime", "Schuldenzyklus", "Empfehlung"):
            run.steps.append(Step(name, "übersprungen", 0.0, "wegen: Datenabruf"))
    else:
        run.run("Validierung", step_validate)
        run.run("Regime", step_regime, needs=["Validierung"])
        run.run("Schuldenzyklus", step_debt, needs=["Validierung"])
        run.run("Empfehlung", step_recommend, needs=["Regime"])
        if with_backtest:
            run.run("Backtest", step_backtest, needs=["Regime"])
    run.run("Monatsbericht", lambda: str(write_monthly_report(config, paths, run)))
    write_run(
        paths.runs,
        "monthly",
        config.config_hash,
        {"demo": paths.demo, "steps": {s.name: s.status for s in run.steps}},
    )
    return run


def previous_snapshot(reports: Path, asof: str) -> View | None:
    """Archivierte Empfehlung des letzten früheren Stichtags."""
    folder = reports / "snapshot" / "archive"
    if not folder.exists():
        return None
    older = sorted(p for p in folder.glob("recommend_*.json") if p.stem.split("_", 1)[1] < asof)
    return View.load(older[-1]) if older else None


def write_monthly_report(config: AppConfig, paths: ProjectPaths, run: MonthlyRun | None) -> Path:
    """Monatsbericht aus den Schnappschüssen (auch ohne Lauf: ``navigator report``)."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    lines = ["# Monatsbericht Allokations-Navigator", ""]
    if paths.demo:
        lines += ["> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte.", ""]
    lines += [f"Erstellt: {utc_now().isoformat(timespec='seconds')}", ""]
    if run is not None:
        rows = [
            {
                "Schritt": s.name,
                "Status": s.status,
                "Dauer s": round(s.seconds),
                "Hinweis": s.message,
            }
            for s in run.steps
        ]
        lines += ["## Ablauf", "", markdown_table(pd.DataFrame(rows).set_index("Schritt"))]
    path = snapshot_path(paths.reports, "recommend")
    asof = "unbekannt"
    if path.exists():
        view = View.load(path)
        asof = str(view.values["asof"])
        variant = (
            MAIN_VARIANT
            if f"detail:{MAIN_VARIANT}" in view.tables
            else next(k.split(":", 1)[1] for k in view.tables if k.startswith("detail:"))
        )
        table = allocation_table(view, variant)
        previous = previous_snapshot(paths.reports, asof)
        if previous is not None and f"detail:{variant}" in previous.tables:
            before = previous.tables[f"detail:{variant}"]["Ziel"] * 100
            table.insert(2, "Vormonat %", before.reindex(table.index))
            table.insert(3, "Änderung Pp.", table["Gewicht %"] - table["Vormonat %"])
        probs = view.tables["probs"]
        checks = view.values["checks"].get(variant, {})
        failed = [k for k, ok in checks.items() if not ok]
        lines += [
            f"## Empfohlene Gewichtung zum Stichtag {asof} "
            f"({variant}, {view.values['base_currency']})",
            "",
            "Das Tool setzt eine Methode um; es ist keine Anlageberatung.",
            "",
            markdown_table(table.rename_axis("Kürzel"), "{:.1f}"),
            f"Tracking Error {view.values['tracking_error'][variant]:.2%} · Umschlag "
            f"{view.values['turnover'][variant]:.1%} · Restriktionen "
            + ("eingehalten" if not failed else "VERLETZT: " + ", ".join(failed)),
            "",
            "## Regime",
            "",
            markdown_table((probs * 100).rename_axis("Quadrant"), "{:.0f}"),
            f"Überzeugung (Übereinstimmung A und B): {view.values['conviction']:.2f}",
            "",
        ]
    else:
        lines += ["## Empfehlung", "", "Keine Empfehlung vorhanden (Schritt fehlgeschlagen).", ""]
    debt = paths.reports / "debt_history.csv"
    if debt.exists() and debt.stat().st_size > 0:
        frame = pd.read_csv(debt, parse_dates=["date"])
        last = frame.sort_values("date").groupby("country").last()[["score", "phase"]]
        manual = {c: e.get("phase", "") for c, e in config.debt_cycle.assessments.items()}
        last["manuell"] = [manual.get(str(c), "") for c in last.index]
        lines += ["## Schuldenzyklus", "", markdown_table(last.rename_axis("Land"), "{:.1f}")]
    if run is not None and run.notes.get("debt_warnings"):
        lines += [f"- {w}" for w in run.notes["debt_warnings"].splitlines()] + [""]
    if run is not None and run.notes.get("failed_optional"):
        lines += [
            "## Datenqualität",
            "",
            f"Optionale Reihen ohne frische Daten: {run.notes['failed_optional']}",
            "",
        ]
    lines += [
        "Details: `validation_latest.md`, `regime_a_latest.md`, `regime_b_latest.md`, "
        "`debt_latest.md`, `recommend_latest.md`; interaktiv: `navigator dashboard`.",
        "",
    ]
    text = "\n".join(lines)
    md = paths.reports / "monthly_latest.md"
    md.write_text(text, encoding="utf-8")
    body = "".join(
        f"<pre>{html.escape(line)}</pre>" if line.startswith("|") else f"<p>{html.escape(line)}</p>"
        for line in lines
    )
    (paths.reports / "monthly_latest.html").write_text(
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>Monatsbericht</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:auto}pre{margin:0}</style>"
        f"</head><body>{body}</body></html>",
        encoding="utf-8",
    )
    archive = paths.reports / "monthly" / f"{asof}.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(text, encoding="utf-8")
    return md
