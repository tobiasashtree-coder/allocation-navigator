"""Methode B als Ganzes und Vergleich mit Methode A: Ablauf und Bericht."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from navigator.config import QUADRANTS, AppConfig
from navigator.data.pit import PitStore
from navigator.data.validate import markdown_table
from navigator.features.market import feature_matrix
from navigator.paths import ProjectPaths
from navigator.regimes.compare import (
    STATE_LABELS,
    agreement,
    b_drivers,
    conviction,
    explanation,
    feature_name,
)
from navigator.regimes.hmm import MethodBResult, run_method_b
from navigator.regimes.method_a import MethodAResult, regime_spans, run_method_a
from navigator.regimes.rules import LABELS
from navigator.runlog import utc_now, write_run

COMPARE_REGION = "US"


@dataclass
class Comparison:
    """Methode A, Methode B und ihr Vergleich."""

    a: MethodAResult
    b: MethodBResult
    conviction: pd.Series
    agreement_rate: float
    crosstab: pd.DataFrame
    gmm_agreement: float
    explanations: pd.Series

    def episode_check(self, config: AppConfig) -> pd.DataFrame:
        """Anteil der Episodenmonate, in denen B den erwarteten Quadranten führt."""
        rows = []
        for episode in config.regime_map.episodes:
            start = pd.Timestamp(episode.start) + pd.offsets.MonthEnd(0)
            end = pd.Timestamp(episode.end) + pd.offsets.MonthEnd(0)
            window = self.b.regime[(self.b.regime.index >= start) & (self.b.regime.index <= end)]
            window = window.dropna()
            a_part = (
                self.a.regimes[COMPARE_REGION]["regime"].loc[window.index] if len(window) else []
            )
            rows.append(
                {
                    "Episode": episode.name,
                    "Monate": len(window),
                    "Anteil erwartet B": float(window.isin(episode.expected).mean())
                    if len(window)
                    else float("nan"),
                    "Anteil erwartet A": float(pd.Series(a_part).isin(episode.expected).mean())
                    if len(window)
                    else float("nan"),
                    "Verteilung B": ", ".join(
                        f"{LABELS[q]} {n}" for q, n in window.value_counts().items()
                    ),
                }
            )
        return pd.DataFrame(rows)


def indicator_groups(config: AppConfig) -> tuple[list[str], list[str]]:
    """Wachstums- und Inflationsmerkmale der Methode B (für die Benennung der Zustände)."""
    cfg = config.regime_map.hmm
    growth = [k for k in cfg.indicator_features if config.indicators.indicators[k].axis == "growth"]
    inflation = [
        k for k in cfg.indicator_features if config.indicators.indicators[k].axis == "inflation"
    ]
    return growth, inflation


def run_comparison(
    config: AppConfig, store: PitStore, dates: pd.DatetimeIndex, a: MethodAResult | None = None
) -> Comparison:
    """Führt A (falls nötig) und B aus und vergleicht beide."""
    a = a or run_method_a(config, store, dates)
    cfg = config.regime_map.hmm
    features = feature_matrix(
        a.scores,
        store,
        cfg.indicator_features,
        cfg.market_features,
        config.indicators.defaults,
        config.regime_map.credit_cycle,
    )
    features = features.loc[features.index >= pd.Timestamp(cfg.start) + pd.offsets.MonthEnd(0)]
    growth, inflation = indicator_groups(config)
    b = run_method_b(features, cfg, growth, inflation)
    table_a = a.regimes[COMPARE_REGION]
    probs_a = table_a[[f"p_{q}" for q in QUADRANTS]]
    probs_a.columns = list(QUADRANTS)
    conv = conviction(probs_a.reindex(b.probs.index), b.probs)
    rate, crosstab = agreement(table_a["regime"].reindex(b.regime.index), b.regime)
    gmm_rate, _ = agreement(b.gmm_regime, b.regime)
    names = {k: v.name for k, v in config.indicators.indicators.items()}
    texts = pd.Series(
        {
            when: explanation(when, table_a["regime"].get(when), a.scores, b, names)
            for when in b.regime.dropna().index
        },
        dtype="object",
    )
    return Comparison(a, b, conv, rate, crosstab, gmm_rate, texts)


def current_comparison(cmp: Comparison) -> pd.DataFrame:
    """Aktuelle Wahrscheinlichkeiten beider Methoden je Quadrant."""
    when = cmp.b.regime.last_valid_index()
    table_a = cmp.a.regimes[COMPARE_REGION]
    rows = []
    for q in QUADRANTS:
        rows.append(
            {
                "Quadrant": LABELS[q],
                "Methode A": float(table_a.loc[when, f"p_{q}"]),
                "Methode B (HMM)": float(cmp.b.probs.loc[when, q]),
                "Gegencheck (GMM)": float(cmp.b.gmm_probs.loc[when, q]),
            }
        )
    return pd.DataFrame(rows).set_index("Quadrant")


def write_report(config: AppConfig, paths: ProjectPaths, cmp: Comparison) -> tuple[Path, Path]:
    """Bericht zu Methode B und dem Vergleich mit A (Markdown, CSV)."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    when = cmp.b.regime.last_valid_index()
    names = {k: v.name for k, v in config.indicators.indicators.items()}
    lines = ["# Methode B und Vergleich mit Methode A", ""]
    if paths.demo:
        lines += ["> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte.", ""]
    lines += [
        f"Erstellt: {utc_now().isoformat(timespec='seconds')} · Konfigurations-Hash: "
        f"`{config.config_hash[:12]}`",
        "",
    ]
    if when is None:
        lines += ["Keine Ergebnisse: zu wenig Historie für die erste Schätzung."]
    else:
        regime_a = cmp.a.regimes[COMPARE_REGION]["regime"].get(when)
        lines += [
            f"## Stand {when:%Y-%m-%d}",
            "",
            f"- Methode A (USA): **{LABELS.get(regime_a, '–')}**",
            f"- Methode B (HMM): **{STATE_LABELS.get(cmp.b.label[when], '–')}**",
            f"- Überzeugung (1 − Totalvariationsdistanz): **{cmp.conviction[when]:.2f}**",
            f"- Begründung: {cmp.explanations.get(when, '')}",
            "",
            markdown_table(current_comparison(cmp), "{:.2f}"),
            "## Merkmale, die B zum wahrscheinlichsten Zustand führen",
            "",
        ]
        drivers = b_drivers(cmp.b, when, top=0)
        if not drivers.empty:
            drivers["Merkmal"] = [feature_name(k, names) for k in drivers["Merkmal"]]
            lines += [
                f"Zerlegung der Log-Likelihood-Differenz zwischen "
                f'„{STATE_LABELS[drivers.attrs["first"]]}" und '
                f'„{STATE_LABELS[drivers.attrs["second"]]}" (positiv = spricht für den ersten).',
                "",
                markdown_table(drivers.set_index("Merkmal"), "{:+.2f}"),
            ]
        lines += [
            "## Übergangsmatrix des aktuellen Modells",
            "",
            markdown_table(cmp.b.transition_matrix().rename_axis("von"), "{:.2f}"),
            "## Erwartete Verweildauer (Monate)",
            "",
            markdown_table(
                cmp.b.expected_duration().rename("Monate").to_frame().rename_axis("Zustand"),
                "{:.1f}",
            ),
        ]
    lines += [
        "## Übereinstimmung über die Historie",
        "",
        f"- A und B gleich: **{cmp.agreement_rate:.0%}** der gemeinsamen Monate",
        f"- HMM und GMM-Gegencheck gleich: **{cmp.gmm_agreement:.0%}**",
        f"- mittlere Überzeugung: **{cmp.conviction.mean():.2f}**",
        "",
        "Kreuztabelle (Zeilen: Methode A, Spalten: Methode B, Anzahl Monate):",
        "",
        markdown_table(cmp.crosstab, "{:.0f}"),
        "## Episoden-Check",
        "",
        markdown_table(cmp.episode_check(config), "{:.2f}"),
        "## Begründungen der letzten 12 Monate",
        "",
    ]
    for stamp, text in cmp.explanations.tail(12).items():
        lines.append(f"- {stamp:%Y-%m}: {text}")
    lines += [
        "",
        "## Anzahl Zustände (BIC, Diagnose über die ganze Historie)",
        "",
        "Nur zur Information; der BIC nutzt alle Daten und fließt in keine Entscheidung ein.",
        "",
        markdown_table(
            cmp.b.bic_table.set_index("Zustände") if len(cmp.b.bic_table) else cmp.b.bic_table,
            "{:.1f}",
        ),
        "## Regime-Abschnitte Methode B",
        "",
        markdown_table(regime_spans(cmp.b.regime)),
    ]
    markdown = "\n".join(lines)
    md_path = paths.reports / "regime_b_latest.md"
    md_path.write_text(markdown, encoding="utf-8")
    history = pd.concat(
        {
            "A": cmp.a.regimes[COMPARE_REGION][["regime"] + [f"p_{q}" for q in QUADRANTS]],
            "B": cmp.b.probs.assign(regime=cmp.b.regime, label=cmp.b.label),
            "GMM": cmp.b.gmm_probs.assign(regime=cmp.b.gmm_regime),
        },
        axis=1,
    )
    history[("vergleich", "ueberzeugung")] = cmp.conviction
    history[("vergleich", "begruendung")] = cmp.explanations
    csv_path = paths.reports / "regime_b_history.csv"
    history.loc[cmp.b.probs.index].to_csv(csv_path, float_format="%.4f")
    write_run(
        paths.runs,
        "regime run --method b",
        config.config_hash,
        {"stichtag": str(when.date()) if when is not None else "", "demo": paths.demo},
    )
    return md_path, csv_path
