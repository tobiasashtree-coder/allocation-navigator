"""Prüfungen der Datenschicht und Validierungsbericht (Prüfpunkt M1).

Geprüft werden Lücken, Sprünge, fehlende Dividenden, Split-Fehler, Aktualität,
Abweichungen zwischen Erst- und Zweitquelle (über 0,5 % Monatsrendite), synthetische
Anleihen gegen echte Fondsrenditen sowie die Abdeckung aller Assetklassen in jeder
unterstützten Basiswährung.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from navigator.data.cache import CacheMeta
from navigator.data.fx import to_month_end

Severity = Literal["Fehler", "Warnung", "Hinweis"]
_SPLIT_RATIOS = (2.0, 3.0, 4.0, 5.0, 10.0, 1.5)
_MAX_AGE_DAYS = {
    "price": 7,
    "level": 10,
    "fx": 7,
    "yield": 10,
    "rate": 45,
    "macro": 200,
    "returns": 150,
}


@dataclass(frozen=True)
class Finding:
    """Ein Prüfergebnis."""

    severity: Severity
    scope: str
    check: str
    message: str


def check_gaps(frame: pd.DataFrame, scope: str, max_gap_days: int = 10) -> list[Finding]:
    """Lücken in Tagesreihen (mehr als ``max_gap_days`` Kalendertage ohne Wert)."""
    dates = pd.DatetimeIndex(frame["obs_date"])
    if len(dates) < 3:
        return []
    gaps = pd.Series(dates[1:] - dates[:-1], index=dates[1:])
    if gaps.median() > pd.Timedelta(days=20):
        missing = gaps[gaps > pd.Timedelta(days=45)]
        label = "Monatsreihe mit fehlenden Monaten"
    else:
        missing = gaps[gaps > pd.Timedelta(days=max_gap_days)]
        label = f"Lücken über {max_gap_days} Tage"
    if missing.empty:
        return []
    worst = missing.idxmax()
    return [
        Finding(
            "Warnung",
            scope,
            "Lücken",
            f"{label}: {len(missing)} (größte: {missing.max().days} Tage bis {worst.date()})",
        )
    ]


def check_jumps(frame: pd.DataFrame, scope: str, threshold: float = 0.25) -> list[Finding]:
    """Auffällige Tagessprünge im bereinigten Kurs."""
    values = frame.set_index("obs_date")["value"]
    returns = values.pct_change(fill_method=None).dropna()
    jumps = returns[returns.abs() > threshold]
    if jumps.empty:
        return []
    worst = jumps.abs().idxmax()
    return [
        Finding(
            "Warnung",
            scope,
            "Sprünge",
            f"{len(jumps)} Sprünge über {threshold:.0%} (größter: {jumps[worst]:+.1%} "
            f"am {worst.date()})",
        )
    ]


def check_splits(frame: pd.DataFrame, scope: str, tolerance: float = 0.02) -> list[Finding]:
    """Split-Fehler: Der bereinigte Kurs springt um ein typisches Split-Verhältnis."""
    values = frame.set_index("obs_date")["value"]
    ratio = (values / values.shift(1)).dropna()
    suspicious = []
    for split in _SPLIT_RATIOS:
        for target in (split, 1.0 / split):
            hits = ratio[(ratio / target - 1.0).abs() < tolerance]
            suspicious.extend(hits.index.tolist())
    if not suspicious:
        return []
    first = min(suspicious)
    return [
        Finding(
            "Fehler",
            scope,
            "Split-Fehler",
            f"{len(suspicious)} Sprünge im bereinigten Kurs nahe einem Split-Verhältnis "
            f"(erster: {first.date()})",
        )
    ]


def check_dividends(frame: pd.DataFrame, scope: str, years: int = 5) -> list[Finding]:
    """Fehlende Dividenden bei ausschüttenden Fonds.

    Bereinigter und unbereinigter Kurs müssen über ein Kalenderjahr auseinanderlaufen;
    tun sie das nicht, fehlen der Quelle vermutlich die Ausschüttungen.
    """
    if "raw" not in frame.columns or frame["raw"].isna().all():
        return [Finding("Hinweis", scope, "Dividenden", "kein unbereinigter Kurs vorhanden")]
    data = frame.set_index("obs_date")[["value", "raw"]].dropna()
    yearly = data.resample("YE").last()
    growth = (yearly["value"] / yearly["value"].shift(1)) / (yearly["raw"] / yearly["raw"].shift(1))
    implied = (growth - 1.0).dropna().iloc[-years:]
    missing = implied[implied.abs() < 5e-5]
    if implied.empty or missing.empty:
        return []
    listed = ", ".join(str(y.year) for y in missing.index)
    return [
        Finding(
            "Warnung",
            scope,
            "Dividenden",
            f"keine Ausschüttung im bereinigten Kurs erkennbar in: {listed}; Zweitquelle prüfen",
        )
    ]


def check_staleness(
    meta: CacheMeta,
    scope: str,
    now: datetime,
    frame: pd.DataFrame | None = None,
    historical: bool = False,
) -> list[Finding]:
    """Aktualität einer Reihe und Hinweis auf einen veralteten Cache-Stand.

    Die Altersgrenze richtet sich nach Art und tatsächlichem Abstand der Beobachtungen.
    Abgeschlossene Reihen (``historical``, z. B. Backfill oder EONIA) werden nicht auf
    ihr Alter geprüft.
    """
    findings = []
    if meta.stale:
        findings.append(
            Finding(
                "Warnung",
                scope,
                "Aktualität",
                f"Quelle ausgefallen, Stand vom {meta.fetched_at} verwendet ({meta.error[:120]})",
            )
        )
    if historical:
        return findings
    limit = _MAX_AGE_DAYS.get(meta.kind, 60)
    if frame is not None and len(frame) > 3:
        spacing = pd.Series(frame["obs_date"]).diff().median().days
        if spacing > 300:
            limit = max(limit, 550)
        elif spacing > 80:
            limit = max(limit, 250)
        elif spacing > 20:
            limit = max(limit, 100)
    age = (pd.Timestamp(now.date()) - pd.Timestamp(meta.last_obs)).days
    if age > limit:
        findings.append(
            Finding(
                "Warnung",
                scope,
                "Aktualität",
                f"letzte Beobachtung {meta.last_obs} ist {age} Tage alt (Grenze {limit})",
            )
        )
    return findings


def check_start(
    expected: str | None, actual: pd.Timestamp, scope: str, tolerance_months: int = 12
) -> list[Finding]:
    """Vergleicht den tatsächlichen Start einer Reihe mit dem erwarteten Start."""
    if not expected:
        return []
    wanted = pd.Timestamp(f"{expected}-01")
    months = (actual.year - wanted.year) * 12 + actual.month - wanted.month
    if abs(months) <= tolerance_months:
        return []
    severity: Severity = "Warnung" if abs(months) > 60 else "Hinweis"
    return [
        Finding(
            severity,
            scope,
            "Startdatum",
            f"Daten ab {actual.strftime('%Y-%m')}, erwartet {expected} ({months:+d} Monate)",
        )
    ]


def cross_check(primary: pd.DataFrame, secondary: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Monatsrenditen zweier Quellen; liefert die Monate mit Abweichung über ``tolerance``."""
    first = to_month_end(primary.set_index("obs_date")["value"]).pct_change(fill_method=None)
    second = to_month_end(secondary.set_index("obs_date")["value"]).pct_change(fill_method=None)
    joined = pd.concat([first, second], axis=1, join="inner").dropna()
    joined.columns = ["primary", "secondary"]
    joined["diff"] = joined["primary"] - joined["secondary"]
    return joined[joined["diff"].abs() > tolerance]


def summarize_cross_check(
    deviations: pd.DataFrame, scope: str, names: tuple[str, str], tolerance: float
) -> list[Finding]:
    """Fasst die Kreuzprüfung einer Reihe in einem Befund zusammen."""
    if deviations.empty:
        return []
    worst = deviations["diff"].abs().idxmax()
    return [
        Finding(
            "Warnung",
            scope,
            "Zweitquelle",
            f"{names[0]} gegen {names[1]}: {len(deviations)} Monate über {tolerance:.1%} "
            f"(größte: {deviations.loc[worst, 'diff']:+.2%} im {worst.strftime('%Y-%m')})",
        )
    ]


def check_universe(returns: pd.DataFrame, expected_assets: list[str], base: str) -> list[Finding]:
    """Abdeckung: jede Assetklasse als Monatsreihe in der Basiswährung, mit plausiblen Werten."""
    findings: list[Finding] = []
    for asset in expected_assets:
        scope = f"{base}/{asset}"
        if asset not in returns.columns or returns[asset].dropna().empty:
            findings.append(Finding("Fehler", scope, "Abdeckung", "keine Monatsreihe vorhanden"))
            continue
        series = returns[asset].dropna()
        expected_months = (
            (series.index[-1].year - series.index[0].year) * 12
            + series.index[-1].month
            - series.index[0].month
            + 1
        )
        if len(series) < expected_months:
            findings.append(
                Finding(
                    "Warnung",
                    scope,
                    "Abdeckung",
                    f"{expected_months - len(series)} Monate fehlen innerhalb der Historie",
                )
            )
        extreme = series[series.abs() > 0.6]
        if asset != "bitcoin" and len(extreme):
            findings.append(
                Finding(
                    "Warnung",
                    scope,
                    "Plausibilität",
                    f"{len(extreme)} Monatsrenditen über 60 % (z. B. {extreme.index[0]:%Y-%m})",
                )
            )
        if not np.isfinite(series.to_numpy()).all():
            findings.append(Finding("Fehler", scope, "Plausibilität", "nicht-endliche Werte"))
    return findings


# ----------------------------------------------------------------------------- Bericht


def markdown_table(frame: pd.DataFrame, float_format: str = "{:.3f}") -> str:
    """Einfache Markdown-Tabelle (ohne Zusatzbibliothek)."""
    if frame.empty:
        return "_keine Einträge_\n"

    def cell(value: object) -> str:
        if isinstance(value, float):
            return "" if np.isnan(value) else float_format.format(value)
        return str(value).replace("|", "\\|").replace("\n", " ")

    table = frame.reset_index() if frame.index.name else frame
    lines = [
        "| " + " | ".join(str(c) for c in table.columns) + " |",
        "| " + " | ".join("---" for _ in table.columns) + " |",
    ]
    for row in table.itertuples(index=False):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


@dataclass
class ValidationReport:
    """Ergebnis einer Validierung: Befunde und Tabellen."""

    created_at: str
    config_hash: str
    demo: bool = False
    findings: list[Finding] = field(default_factory=list)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def count(self, severity: Severity) -> int:
        """Anzahl der Befunde einer Stufe."""
        return sum(1 for f in self.findings if f.severity == severity)

    def findings_frame(self) -> pd.DataFrame:
        """Befunde als Tabelle, schwerste zuerst."""
        order = {"Fehler": 0, "Warnung": 1, "Hinweis": 2}
        rows = sorted(self.findings, key=lambda f: (order[f.severity], f.scope, f.check))
        return pd.DataFrame(
            [(f.severity, f.scope, f.check, f.message) for f in rows],
            columns=["Stufe", "Bereich", "Prüfung", "Befund"],
        )

    def to_markdown(self) -> str:
        """Bericht als Markdown."""
        parts = ["# Validierungsbericht Datenschicht", ""]
        if self.demo:
            parts += ["> **DEMO-DATEN.** Synthetische Reihen, keine echten Marktdaten.", ""]
        parts += [
            f"Erstellt: {self.created_at} · Konfigurations-Hash: `{self.config_hash[:12]}`",
            "",
            f"**{self.count('Fehler')} Fehler, {self.count('Warnung')} Warnungen, "
            f"{self.count('Hinweis')} Hinweise.**",
            "",
        ]
        parts += [f"- {note}" for note in self.notes]
        parts += ["", "## Befunde", "", markdown_table(self.findings_frame())]
        for title, table in self.tables.items():
            parts += [f"## {title}", "", markdown_table(table)]
        return "\n".join(parts)

    def to_html(self) -> str:
        """Bericht als eigenständige HTML-Seite."""
        style = (
            "body{font-family:system-ui,sans-serif;margin:2rem;max-width:1200px}"
            "table{border-collapse:collapse;margin:1rem 0;font-size:.85rem}"
            "th,td{border:1px solid #ccc;padding:.25rem .5rem;text-align:left}"
            "th{background:#f3f3f3}"
            ".demo{background:#fff3cd;padding:.75rem;border:1px solid #e0c36a}"
        )
        body = ["<h1>Validierungsbericht Datenschicht</h1>"]
        if self.demo:
            body.append('<p class="demo"><b>DEMO-DATEN.</b> Synthetische Reihen.</p>')
        body.append(
            f"<p>Erstellt: {html.escape(self.created_at)} · Konfigurations-Hash: "
            f"<code>{self.config_hash[:12]}</code></p>"
            f"<p><b>{self.count('Fehler')} Fehler, {self.count('Warnung')} Warnungen, "
            f"{self.count('Hinweis')} Hinweise.</b></p>"
        )
        body.append("<ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in self.notes) + "</ul>")
        body.append("<h2>Befunde</h2>" + self.findings_frame().to_html(index=False, escape=True))
        for title, table in self.tables.items():
            body.append(
                f"<h2>{html.escape(title)}</h2>"
                + table.to_html(escape=True, float_format=lambda v: f"{v:.3f}", na_rep="")
            )
        return (
            "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'>"
            f"<title>Validierungsbericht</title><style>{style}</style></head><body>"
            + "".join(body)
            + "</body></html>"
        )

    def write(self, reports_dir: Path, stem: str = "validation") -> tuple[Path, Path]:
        """Schreibt Markdown und HTML (mit Zeitstempel und als ``_latest``)."""
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.created_at.replace(":", "").replace("-", "")[:15]
        markdown, page = self.to_markdown(), self.to_html()
        for name in (f"{stem}_{stamp}", f"{stem}_latest"):
            (reports_dir / f"{name}.md").write_text(markdown, encoding="utf-8")
            (reports_dir / f"{name}.html").write_text(page, encoding="utf-8")
        return reports_dir / f"{stem}_latest.md", reports_dir / f"{stem}_latest.html"
