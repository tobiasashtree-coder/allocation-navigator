"""Methode A als Ganzes: Scores, Quadranten, Schuldenzyklus, Episoden-Check und Bericht."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from navigator.config import AppConfig
from navigator.data.pit import PitStore
from navigator.data.validate import markdown_table
from navigator.features.credit_cycle import PHASE_LABELS, classify_credit_cycle, credit_inputs
from navigator.features.scores import Scores, compute_scores
from navigator.paths import ProjectPaths
from navigator.regimes.rules import LABELS, classify
from navigator.runlog import utc_now, write_run

REGIONS = ("US", "EA")


def month_ends(start: str, end: pd.Timestamp | str) -> pd.DatetimeIndex:
    """Monatsenden von ``start`` bis einschließlich des Monats von ``end``."""
    last = pd.Timestamp(end) + pd.offsets.MonthEnd(0)
    if pd.Timestamp(end).normalize() < last:
        last = last - pd.offsets.MonthEnd(1)
    return pd.date_range(pd.Timestamp(start) + pd.offsets.MonthEnd(0), last, freq="ME")


@dataclass
class MethodAResult:
    """Ergebnis von Methode A über alle Stichtage."""

    scores: Scores
    regimes: dict[str, pd.DataFrame]  # "GLOBAL", "US", "EA"
    credit: pd.DataFrame
    episodes: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def dates(self) -> pd.DatetimeIndex:
        """Stichtage."""
        return self.scores.dates


def run_method_a(config: AppConfig, store: PitStore, dates: pd.DatetimeIndex) -> MethodAResult:
    """Berechnet Methode A für alle Stichtage ``dates``."""
    scores = compute_scores(config.indicators, store, dates, REGIONS)
    rules = config.regime_map.rules
    regimes = {
        "GLOBAL": classify(scores.global_scores["growth"], scores.global_scores["inflation"], rules)
    }
    for region in REGIONS:
        regimes[region] = classify(
            scores.region_scores[(region, "growth")],
            scores.region_scores[(region, "inflation")],
            rules,
        )
    credit = classify_credit_cycle(
        credit_inputs(store, dates, config.regime_map.credit_cycle), config.regime_map.credit_cycle
    )
    result = MethodAResult(scores=scores, regimes=regimes, credit=credit)
    result.episodes = episode_check(config, result)
    return result


def episode_check(config: AppConfig, result: MethodAResult, region: str = "US") -> pd.DataFrame:
    """Anteil der Monate je Episode, die auf die erwarteten Quadranten entfallen."""
    rows = []
    table = result.regimes[region]
    for episode in config.regime_map.episodes:
        start = pd.Timestamp(episode.start) + pd.offsets.MonthEnd(0)
        end = pd.Timestamp(episode.end) + pd.offsets.MonthEnd(0)
        window = table.loc[(table.index >= start) & (table.index <= end)]
        regimes = window["regime"].dropna()
        counts = regimes.value_counts()
        share = float(regimes.isin(episode.expected).mean()) if len(regimes) else float("nan")
        rows.append(
            {
                "Episode": episode.name,
                "Zeitraum": f"{episode.start} bis {episode.end}",
                "erwartet": ", ".join(LABELS[q] for q in episode.expected),
                "Monate mit Regime": len(regimes),
                "Anteil erwartet": share,
                "Verteilung": ", ".join(f"{LABELS[q]} {n}" for q, n in counts.items()),
                "Ø Wachstum": float(window["growth"].mean()),
                "Ø Inflation": float(window["inflation"].mean()),
                "Schuldenzyklus (häufigste Phase)": _mode_label(result.credit, start, end),
            }
        )
    return pd.DataFrame(rows)


def _mode_label(credit: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> str:
    phases = credit.loc[(credit.index >= start) & (credit.index <= end), "phase"].dropna()
    return PHASE_LABELS[phases.mode().iloc[0]] if len(phases) else ""


def current_state(result: MethodAResult, when: pd.Timestamp | None = None) -> dict[str, object]:
    """Zustand zum Stichtag: Regime je Region, Wahrscheinlichkeiten, Schuldenzyklus."""
    table = result.regimes["GLOBAL"]
    when = when or table["regime"].last_valid_index()
    state: dict[str, object] = {"Stichtag": when.strftime("%Y-%m-%d") if when is not None else ""}
    for name, frame in result.regimes.items():
        if when is None or when not in frame.index:
            continue
        row = frame.loc[when]
        state[f"Regime {name}"] = LABELS.get(row["regime"], "kein Regime") if row["regime"] else ""
        state[f"Wachstum {name}"] = row["growth"]
        state[f"Inflation {name}"] = row["inflation"]
    if when is not None and when in result.credit.index:
        phase = result.credit.loc[when, "phase"]
        state["Schuldenzyklus USA"] = PHASE_LABELS.get(phase, "") if phase else ""
    return state


def _contributions(result: MethodAResult, when: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for region in REGIONS:
        for axis in ("growth", "inflation"):
            for key, value in result.scores.contributions(when, region, axis).items():
                obs = result.scores.observation.loc[when, key]
                rows.append(
                    {
                        "Region": region,
                        "Achse": "Wachstum" if axis == "growth" else "Inflation",
                        "Indikator": key,
                        "z-Wert": float(result.scores.z.loc[when, key]),
                        "Beitrag": float(value),
                        "Beobachtung": obs.strftime("%Y-%m") if pd.notna(obs) else "",
                    }
                )
    return pd.DataFrame(rows)


def history_table(result: MethodAResult) -> pd.DataFrame:
    """Monatliche Historie: Scores, Wahrscheinlichkeiten, Regime, Schuldenzyklus."""
    table = result.regimes["GLOBAL"].copy()
    for region in REGIONS:
        part = result.regimes[region][["growth", "inflation", "regime"]]
        table = table.join(part.add_prefix(f"{region}_"))
    table = table.join(result.credit[["phase", "real_gap", "curve", "spread", "credit_impulse"]])
    table.index.name = "date"
    return table


def regime_spans(regime: pd.Series) -> pd.DataFrame:
    """Zusammenhängende Abschnitte gleichen Regimes (für die Übersicht im Bericht)."""
    clean = regime.dropna()
    if clean.empty:
        return pd.DataFrame(columns=["von", "bis", "Monate", "Regime"])
    group = (clean != clean.shift()).cumsum()
    rows = []
    for _, part in clean.groupby(group):
        rows.append(
            {
                "von": part.index[0].strftime("%Y-%m"),
                "bis": part.index[-1].strftime("%Y-%m"),
                "Monate": len(part),
                "Regime": LABELS[part.iloc[0]],
            }
        )
    return pd.DataFrame(rows)


def write_report(
    config: AppConfig, paths: ProjectPaths, result: MethodAResult, when: pd.Timestamp | None
) -> tuple[Path, Path]:
    """Schreibt den Bericht zu Methode A (Markdown und CSV der Historie)."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    state = current_state(result, when)
    stamp = pd.Timestamp(str(state["Stichtag"])) if state["Stichtag"] else None
    lines = ["# Methode A: regelbasierte Regime-Erkennung", ""]
    if paths.demo:
        lines += ["> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte.", ""]
    lines += [
        f"Erstellt: {utc_now().isoformat(timespec='seconds')} · Konfigurations-Hash: "
        f"`{config.config_hash[:12]}`",
        "",
        "## Aktueller Stand",
        "",
        markdown_table(pd.DataFrame([state]).T.rename(columns={0: "Wert"}), "{:+.2f}"),
    ]
    if stamp is not None:
        lines += [
            "## Beiträge der Indikatoren",
            "",
            markdown_table(_contributions(result, stamp), "{:+.2f}"),
        ]
    lines += [
        "## Episoden-Check (USA)",
        "",
        "Anteil erwartet = Anteil der Monate der Episode, deren bestätigtes Regime zu den "
        "erwarteten Quadranten gehört.",
        "",
        markdown_table(result.episodes, "{:.2f}"),
        "## Regime-Abschnitte (USA)",
        "",
        markdown_table(regime_spans(result.regimes["US"]["regime"])),
        "## Regime-Abschnitte (Eurozone)",
        "",
        markdown_table(regime_spans(result.regimes["EA"]["regime"])),
    ]
    coverage = result.scores.z.notna().sum().rename("Monate mit Wert").to_frame()
    first = result.scores.z.apply(lambda c: c.first_valid_index())
    coverage["ab"] = [d.strftime("%Y-%m") if pd.notna(d) else "" for d in first]
    lines += [
        "## Verfügbarkeit der Indikatoren",
        "",
        markdown_table(coverage.rename_axis("Indikator")),
    ]
    markdown = "\n".join(lines)
    md_path = paths.reports / "regime_a_latest.md"
    md_path.write_text(markdown, encoding="utf-8")
    csv_path = paths.reports / "regime_a_history.csv"
    history_table(result).to_csv(csv_path, float_format="%.4f")
    html_path = paths.reports / "regime_a_latest.html"
    html_path.write_text(
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>Methode A</title>"
        "</head><body><pre>" + html.escape(markdown) + "</pre></body></html>",
        encoding="utf-8",
    )
    write_run(
        paths.runs,
        "regime run --method a",
        config.config_hash,
        {"stichtag": state["Stichtag"], "demo": paths.demo},
    )
    return md_path, csv_path


def load_and_run(
    config: AppConfig, paths: ProjectPaths, start: str, asof: pd.Timestamp | None
) -> MethodAResult:
    """Komfortfunktion für die Kommandozeile."""
    end = asof if asof is not None else pd.Timestamp(utc_now().date())
    return run_method_a(config, PitStore(paths.pit), month_ends(start, end))
