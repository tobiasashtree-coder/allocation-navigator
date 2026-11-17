"""Empfehlung zum Stichtag: Methoden A, B und Zusammenführung, je mit und ohne Overlay.

Ruft Basis (7.1), Black-Litterman (7.2), die drei Ausgabeformen (7.3), die Zerlegung (7.4)
und die Währungssicht (7.6) auf. Schreibt ``reports/recommend_latest.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from navigator.allocation.base import BaseAllocation, base_allocation, risk_contributions
from navigator.allocation.engine import (
    BlackLitterman,
    TargetResult,
    ampel,
    assumption_returns,
    black_litterman,
    decomposition,
    historical_regime_returns,
    james_stein,
    target_weights,
    tilts,
)
from navigator.allocation.overlay import OverlayResult
from navigator.config import QUADRANTS, AppConfig
from navigator.data.validate import markdown_table
from navigator.paths import ProjectPaths
from navigator.runlog import utc_now, write_run

QUADRANT_LABELS = {
    "disinflationary_boom": "Disinflationärer Aufschwung",
    "reflation": "Reflation / Überhitzung",
    "deflationary_bust": "Deflationäre Rezession",
    "stagflation": "Stagflation",
}


def excess_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Monatliche Überrenditen gegenüber Cash in Basiswährung."""
    if "cash" not in returns.columns:
        return returns
    cash = returns["cash"].fillna(0.0)
    return returns.drop(columns=["cash"]).sub(cash, axis=0)


@dataclass
class Variant:
    """Eine Empfehlung (Methode, mit oder ohne Overlay)."""

    name: str
    probs: pd.Series
    conviction: float
    regime_view: pd.Series
    bl: BlackLitterman
    bl_regime: BlackLitterman
    signal: pd.Series
    lights: pd.Series
    tilt_pp: pd.Series
    target: TargetResult
    parts: pd.DataFrame


@dataclass
class Recommendation:
    """Alle Varianten zum Stichtag."""

    asof: pd.Timestamp
    base: BaseAllocation
    regime_returns: pd.DataFrame
    shrink: pd.Series
    variants: dict[str, Variant]
    previous_lights: dict[str, pd.Series]
    currency: pd.DataFrame
    currency_risk: float
    usd_exposure: dict[str, float]
    notes: list[str] = field(default_factory=list)


def regime_view(probs: pd.Series, regime_returns: pd.DataFrame) -> pd.Series:
    """Sicht je Klasse: Σ_q P(q) · Regime-Rendite(Klasse, q)."""
    p = probs.reindex(list(QUADRANTS)).fillna(0.0)
    p = p / p.sum() if p.sum() > 0 else pd.Series(0.25, index=list(QUADRANTS))
    return regime_returns[list(QUADRANTS)] @ p


def build_variant(
    name: str,
    probs: pd.Series,
    conviction: float,
    base: BaseAllocation,
    returns_table: pd.DataFrame,
    config: AppConfig,
    overlay: OverlayResult | None,
    current: pd.Series | None,
    simulations: int | None,
) -> Variant:
    """Eine Variante: Sichten, Posterior, Ampel, Tilts, Zielgewichte, Zerlegung."""
    view = regime_view(probs, returns_table)
    bl_regime = black_litterman(base, config, view, conviction, None)
    overlay_w = overlay.weights if overlay is not None else None
    bl = black_litterman(base, config, view, conviction, overlay_w) if overlay else bl_regime
    signal = bl.posterior - bl.prior
    outputs = config.base.outputs
    lights = ampel(signal, float(outputs["ampel"].get("threshold_sd", 0.5)))
    tilt_pp = tilts(signal, conviction, base.weights, config)
    usd_cap = overlay.usd_cap if overlay is not None else None
    target = target_weights(bl, base, config, current, usd_cap, simulations)
    parts = decomposition(base, bl_regime, bl, target.weights, config)
    return Variant(
        name, probs, conviction, view, bl, bl_regime, signal, lights, tilt_pp, target, parts
    )


def currency_view(
    returns: pd.DataFrame, effect: pd.DataFrame, weights: pd.Series, config: AppConfig
) -> tuple[pd.DataFrame, float, dict[str, float]]:
    """Währungszerlegung (7.6): je Klasse Lokal- und Währungsbeitrag über 12 Monate,
    Risikoanteil der Währungen und Exposure je Währung.

    Rendite in Basiswährung = (1 + lokal) × (1 + Währung) − 1.
    """
    assets = [a for a in weights.index if a in returns.columns]
    last = returns[assets].iloc[-12:]
    fx = effect.reindex(columns=assets).reindex(last.index).fillna(0.0)
    local = (1 + last) / (1 + fx) - 1
    table = pd.DataFrame(
        {
            "Rendite 12 M. (Basis)": ((1 + last).prod() - 1) * 100,
            "davon lokal": ((1 + local).prod() - 1) * 100,
            "davon Währung": ((1 + fx).prod() - 1) * 100,
        }
    )
    window = returns[assets].iloc[-60:].fillna(0.0)
    fx_window = effect.reindex(columns=assets).reindex(window.index).fillna(0.0)
    w = weights.reindex(assets).fillna(0.0)
    port = window @ w
    port_fx = fx_window @ w
    risk = float(np.cov(port, port_fx)[0, 1] / port.var()) if port.var() > 0 else 0.0
    exposure: dict[str, float] = {}
    for asset, weight in w.items():
        spec = config.universe.assets[str(asset)]
        if spec.hedged:
            continue
        for ccy, share in spec.fx_exposure.items():
            exposure[ccy] = exposure.get(ccy, 0.0) + float(weight) * float(share)
    return table, risk, exposure


def run_recommendation(
    config: AppConfig,
    returns: pd.DataFrame,
    effect: pd.DataFrame,
    probabilities: dict[str, pd.DataFrame],
    conviction: pd.Series,
    regimes: pd.Series,
    asof: pd.Timestamp,
    overlay: OverlayResult | None,
    current: pd.Series | None = None,
    simulations: int | None = None,
) -> Recommendation:
    """Empfehlung zum Stichtag ``asof``; alle Eingaben nur bis ``asof`` (Point-in-Time).

    ``probabilities`` je Methode (``a``, ``b``) mit Spalten ``p_<Quadrant>``; die
    Zusammenführung ist ihr Mittel. ``regimes`` (Methode A) dient den historischen
    Regime-Renditen.
    """
    returns = returns[returns.index <= asof]
    effect = effect[effect.index <= asof]
    base = base_allocation(returns, config)
    assets = list(base.cov.index)
    excess = excess_returns(returns)[assets]
    hist, counts = historical_regime_returns(excess, regimes[regimes.index <= asof])
    target = assumption_returns(config, assets)
    table, shrink = james_stein(hist, counts, target, excess.var())
    conv_series = conviction[conviction.index <= asof].dropna()
    conv = float(conv_series.iloc[-1]) if not conv_series.empty else 0.0
    notes: list[str] = []
    probs: dict[str, pd.Series] = {}
    for method, frame in probabilities.items():
        known = frame[frame.index <= asof].dropna(how="all")
        if known.empty:
            notes.append(f"Methode {method.upper()}: keine Wahrscheinlichkeiten bis {asof.date()}")
            continue
        row = known.iloc[-1]
        probs[method] = pd.Series({q: float(row.get(f"p_{q}", np.nan)) for q in QUADRANTS})
    if len(probs) == 2:
        probs["ab"] = (probs["a"] + probs["b"]) / 2.0
    variants: dict[str, Variant] = {}
    for method, p in probs.items():
        variants[method] = build_variant(
            method, p, conv, base, table, config, None, current, simulations
        )
        if overlay is not None:
            variants[f"{method}+overlay"] = build_variant(
                f"{method}+overlay", p, conv, base, table, config, overlay, current, simulations
            )
    previous: dict[str, pd.Series] = {}
    prev_date = asof - pd.offsets.MonthEnd(1)
    for method, frame in probabilities.items():
        known = frame[frame.index <= prev_date].dropna(how="all")
        if known.empty or method not in variants:
            continue
        row = known.iloc[-1]
        p_prev = pd.Series({q: float(row.get(f"p_{q}", np.nan)) for q in QUADRANTS})
        bl_prev = black_litterman(base, config, regime_view(p_prev, table), conv, None)
        signal = bl_prev.posterior - bl_prev.prior
        previous[method] = ampel(signal, float(config.base.outputs["ampel"]["threshold_sd"]))
    main = variants.get("ab+overlay") or variants.get("ab") or next(iter(variants.values()))
    cur_table, cur_risk, exposure = currency_view(returns, effect, main.target.weights, config)
    return Recommendation(
        asof, base, table, shrink, variants, previous, cur_table, cur_risk, exposure, notes
    )


ARROWS = {
    ("rot", "gelb"): "↑",
    ("gelb", "grün"): "↑",
    ("rot", "grün"): "↑",
    ("grün", "gelb"): "↓",
    ("gelb", "rot"): "↓",
    ("grün", "rot"): "↓",
}


def write_report(config: AppConfig, paths: ProjectPaths, rec: Recommendation) -> tuple[Path, Path]:
    """Bericht ``reports/recommend_latest.md`` und Zielgewichte als CSV."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    names = {k: a.name for k, a in config.universe.assets.items()}
    lines = ["# Empfehlung", ""]
    if paths.demo:
        lines += ["> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte.", ""]
    lines += [
        f"Erstellt: {utc_now().isoformat(timespec='seconds')} · Stichtag {rec.asof.date()} · "
        f"Basiswährung {config.currency.base} · Konfigurations-Hash `{config.config_hash[:12]}`",
        "",
        "Keine Anlageberatung: Das Tool setzt eine Methode um; entscheiden muss der Nutzer.",
        "",
    ]
    lines += [f"- {n}" for n in rec.notes]
    main_key = "ab+overlay" if "ab+overlay" in rec.variants else next(iter(rec.variants))
    main = rec.variants[main_key]
    lines += [
        "## Regime-Wahrscheinlichkeiten",
        "",
        markdown_table(
            pd.DataFrame({k: v.probs for k, v in rec.variants.items() if "+" not in k})
            .rename(index=QUADRANT_LABELS)
            .rename_axis("Quadrant")
            * 100,
            "{:.0f}",
        ),
        f"Überzeugung (5.4): {main.conviction:.2f}",
        "",
        f"## Basis: Risikoparität über vier Körbe (Volatilität {rec.base.volatility():.1%} p. a., "
        f"Ledoit-Wolf δ = {rec.base.shrinkage:.2f})",
        "",
    ]
    rc = risk_contributions(rec.base.weights, rec.base.cov)
    lines += [
        markdown_table(
            pd.DataFrame(
                {
                    "Klasse": [names.get(a, a) for a in rec.base.weights.index],
                    "Gewicht %": rec.base.weights.to_numpy() * 100,
                    "Risikobeitrag %": rc.reindex(rec.base.weights.index).to_numpy() * 100,
                },
                index=rec.base.weights.index,
            ).rename_axis("Kürzel"),
            "{:.1f}",
        ),
        "Körbe (gleicher Risikobeitrag): "
        + ", ".join(f"{k} {v:.0%}" for k, v in rec.base.basket_weights.items())
        + ". Cash nimmt nicht teil (E-70).",
        "",
        f"## Empfehlung „{main_key}“: Ampel, Über-/Untergewichtung, Zielgewichte",
        "",
    ]
    prev = rec.previous_lights.get(main_key.split("+")[0], pd.Series(dtype=str))
    t = main.target
    frame = pd.DataFrame(
        {
            "Klasse": [names.get(a, a) for a in main.lights.index],
            "Ampel": [
                main.lights[a] + " " + ARROWS.get((str(prev.get(a, "")), main.lights[a]), "")
                for a in main.lights.index
            ],
            "Signal % p. a.": main.signal.to_numpy() * 100,
            "Tilt Pp.": main.tilt_pp.reindex(main.lights.index).to_numpy(),
            "Basis %": rec.base.weights.reindex(main.lights.index).to_numpy() * 100,
            "Ziel %": t.weights.reindex(main.lights.index).to_numpy() * 100,
            "Bandbreite %": [
                f"{t.low[a] * 100:.1f}–{t.high[a] * 100:.1f}" for a in main.lights.index
            ],
        },
        index=main.lights.index,
    ).rename_axis("Kürzel")
    lines += [
        markdown_table(frame, "{:.1f}"),
        f"Tracking Error {t.tracking_error:.2%} · Umschlag {t.turnover:.1%} · Prüfungen: "
        + ", ".join(f"{k} {'ok' if v else 'VERLETZT'}" for k, v in t.checks.items()),
        "",
    ]
    lines += [f"- {n}" for n in t.notes]
    parts = (main.parts * 100).rename_axis("Kürzel")
    parts.insert(0, "Klasse", [names.get(a, a) for a in parts.index])
    lines += [
        "## Zerlegung je Klasse (Prozentpunkte; Basis + Regime + Overlay + Restriktionen = Ziel)",
        "",
        markdown_table(parts, "{:+.2f}"),
        "## Alle Varianten (Zielgewichte %)",
        "",
        markdown_table(
            pd.DataFrame({k: v.target.weights * 100 for k, v in rec.variants.items()})
            .assign(Basis=rec.base.weights * 100)
            .rename_axis("Kürzel"),
            "{:.1f}",
        ),
        "## Regime-Renditen je Klasse (% p. a., Annahme mit Historie gemischt, James-Stein)",
        "",
        markdown_table(
            (rec.regime_returns * 100).rename(columns=QUADRANT_LABELS).rename_axis("Kürzel"),
            "{:+.1f}",
        ),
        "Schrumpfung zur Annahme je Quadrant: "
        + ", ".join(f"{QUADRANT_LABELS[q]} {c:.2f}" for q, c in rec.shrink.items()),
        "",
        f"## Währungen ({config.currency.base})",
        "",
        "Exposure der Zielgewichte (ungesichert): "
        + ", ".join(f"{k} {v:.1%}" for k, v in sorted(rec.usd_exposure.items())),
        "",
        f"Anteil der Wechselkurse am Portfoliorisiko (60 Monate): {rec.currency_risk:.1%}. "
        f"Szenario: USD ±10 % gegenüber {config.currency.base} ändert den Portfoliowert um "
        f"±{rec.usd_exposure.get('USD', 0.0) * 10:.1f} %.",
        "",
        markdown_table(rec.currency.rename_axis("Kürzel"), "{:+.1f}"),
    ]
    md = paths.reports / "recommend_latest.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    csv = paths.reports / "recommend_targets.csv"
    pd.DataFrame({k: v.target.weights for k, v in rec.variants.items()}).assign(
        base=rec.base.weights
    ).to_csv(csv)
    write_run(
        paths.runs,
        "recommend",
        config.config_hash,
        {"demo": paths.demo, "asof": str(rec.asof.date()), "variants": list(rec.variants)},
    )
    return md, csv


def load_and_recommend(
    config: AppConfig,
    paths: ProjectPaths,
    asof: pd.Timestamp | None = None,
    with_overlay: bool = True,
    current: pd.Series | None = None,
    simulations: int | None = None,
) -> Recommendation:
    """Lädt alles Nötige (Universum, Methoden A und B, Schuldenzyklus) und empfiehlt."""
    from navigator.allocation.overlay import apply_overlay
    from navigator.data.pipeline import make_cache, make_providers
    from navigator.data.pit import PitStore
    from navigator.data.universe import SeriesLoader, UniverseBuilder
    from navigator.features.debt_stress import run_debt_stress
    from navigator.regimes import method_b
    from navigator.regimes.method_a import load_and_run
    from navigator.reporting.debt import current_table

    end = asof if asof is not None else pd.Timestamp(utc_now().date()) - pd.offsets.MonthEnd(1)
    end = (
        pd.Timestamp(end) + pd.offsets.MonthEnd(0)
        if not pd.Timestamp(end).is_month_end
        else pd.Timestamp(end)
    )
    store = PitStore(paths.pit)
    loader = SeriesLoader(make_cache(config, paths), make_providers(config, paths))
    universe = UniverseBuilder(config, loader).build(config.currency.base, end)
    result_a = load_and_run(config, paths, "1960-01", end)
    cmp = method_b.run_comparison(config, store, result_a.dates, result_a)
    probs_a = result_a.regimes["GLOBAL"][[f"p_{q}" for q in QUADRANTS]]
    probs_b = cmp.b.probs.rename(columns={q: f"p_{q}" for q in QUADRANTS})
    overlay = None
    if with_overlay:
        base = base_allocation(universe.returns[universe.returns.index <= end], config)
        debt = run_debt_stress(config, store, end)
        table = current_table(config, debt, end)
        measured = {
            str(c): (None if r["gemessene Phase"] == "–" else str(r["gemessene Phase"]))
            for c, r in table.iterrows()
        }
        scores = {str(c): float(r["Score"]) for c, r in table.iterrows()}
        overlay = apply_overlay(base.weights, config, measured, scores)
    return run_recommendation(
        config,
        universe.returns,
        universe.currency_effect,
        {"a": probs_a, "b": probs_b},
        cmp.conviction,
        result_a.regimes["GLOBAL"]["regime"],
        end,
        overlay,
        current,
        simulations,
    )
