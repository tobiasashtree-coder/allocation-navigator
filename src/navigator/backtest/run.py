"""Backtest gesamt: Strategien, Zeiträume, Placebo, Sensitivität, Bericht (8.1 bis 8.5)."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from navigator.backtest.engine import (
    Decider,
    Inputs,
    StrategyResult,
    one_hot,
    placebo_sequences,
    rebalance_dates,
    simulate,
)
from navigator.backtest.metrics import deflated_sharpe, metrics
from navigator.config import AppConfig
from navigator.data.validate import markdown_table
from navigator.paths import ProjectPaths
from navigator.runlog import utc_now, write_run

SENSITIVITY = {
    "Annahme-Skala": ("black_litterman", "assumption_scale", 0.025),
    "tau": ("black_litterman", "tau", 0.05),
    "Prior-Sharpe": ("black_litterman", "prior_sharpe", 0.3),
}


@dataclass
class BacktestResult:
    """Ergebnis des Backtests."""

    strategies: dict[str, StrategyResult]
    cash: pd.Series
    start: pd.Timestamp
    placebo_sharpes: list[float] = field(default_factory=list)
    placebo_reference: float = float("nan")
    sensitivity: pd.DataFrame = field(default_factory=pd.DataFrame)
    deflated: float = float("nan")
    n_trials: int = 0
    regimes: pd.Series = field(default_factory=pd.Series)

    @property
    def placebo_p(self) -> float:
        """Anteil der Placebo-Folgen mit mindestens so hoher Sharpe-Ratio."""
        if not self.placebo_sharpes:
            return float("nan")
        values = np.array(self.placebo_sharpes)
        return float((np.sum(values >= self.placebo_reference) + 1) / (len(values) + 1))


def first_start(returns: pd.DataFrame, configured: str, window: int = 60) -> pd.Timestamp:
    """Frühester Termin ab ``configured`` mit mindestens ``window`` Monaten für die Kovarianz."""
    count = returns.drop(columns=["cash"], errors="ignore").notna().sum(axis=1)
    enough = count[count >= 4].index
    if len(enough) <= window:
        raise ValueError("zu wenig Historie für den Backtest")
    earliest = enough[window]
    return max(pd.Timestamp(configured) + pd.offsets.MonthEnd(0), earliest)


def run_backtest(
    config: AppConfig,
    inputs: Inputs,
    placebo_runs: int | None = None,
    simulations: int | None = None,
    sensitivity: bool = True,
) -> BacktestResult:
    """Alle Vergleichsstrategien (8.2) über die lange Historie."""
    bt = config.backtest
    sims = int(simulations or bt.rebalancing.get("resampling_simulations", 30))
    band = float(bt.rebalancing.get("no_trade_band_pp", 2.0)) / 100
    costs = dict(bt.costs_bps)
    returns = inputs.returns
    start = first_start(returns, str(bt.periods.get("long_history_start", "1973-01")))
    dates = rebalance_dates(returns.index, str(start.date()), str(bt.rebalancing["frequency"]))
    decider = Decider(config, inputs, sims)
    asset_returns = returns
    strategies: dict[str, StrategyResult] = {}

    def add(name: str, fn, implementable: bool = True, note: str = "") -> None:  # type: ignore[no-untyped-def]
        strategies[name] = simulate(
            name, asset_returns, fn, dates, costs, band, implementable, note
        )

    b = bt.benchmarks
    if b.get("static_base", True):
        add("Basis (statisch)", decider.static_base)
    if b.get("method_a", True):
        add("Methode A", decider.regime("a", False))
    if b.get("method_b", True):
        add("Methode B", decider.regime("b", False))
    if b.get("combined", True):
        add("A + B", decider.regime("ab", False))
    if b.get("combined_with_overlay", True):
        add("A + B + Overlay", decider.regime("ab", True))
    if b.get("sixty_forty"):
        add("60/40 (EUR)", decider.sixty_forty)
    if b.get("equal_weight", True):
        add("Gleichgewichtung", decider.equal_weight)
    if b.get("minimum_variance", True):
        add("Minimum-Varianz", decider.minimum_variance)
    tilt_real = decider.tilt_strategy(lambda t: decider.probs("ab", t))
    add("Tilts A + B (Form ii)", tilt_real)
    if b.get("perfect_foresight", True):
        # Obergrenze: Regime von Methode A sechs Monate später, als ob heute bekannt.
        future = inputs.regimes.shift(-6)
        add(
            "Voraussicht (nicht umsetzbar)",
            decider.tilt_strategy(
                lambda t: one_hot(str(future.get(t))) if pd.notna(future.get(t)) else None
            ),
            implementable=False,
            note="nutzt das Regime sechs Monate später; nur als Obergrenze",
        )
    cash = returns["cash"] if "cash" in returns.columns else pd.Series(0.0, index=returns.index)
    result = BacktestResult(strategies, cash, start, regimes=inputs.regimes)
    reference = strategies["Tilts A + B (Form ii)"].returns
    result.placebo_reference = float(metrics(reference, cash).get("Sharpe", np.nan))
    n_placebo = int(
        placebo_runs if placebo_runs is not None else bt.placebo.get("simulations", 1000)
    )
    for seq in placebo_sequences(
        inputs.regimes[inputs.regimes.index >= start], n_placebo, int(bt.placebo.get("seed", 1))
    ):
        fn = decider.tilt_strategy(_placebo_probs(seq))
        run = simulate("placebo", asset_returns, fn, dates, costs, band)
        result.placebo_sharpes.append(float(metrics(run.returns, cash).get("Sharpe", np.nan)))
    trials = [s.returns for s in strategies.values() if s.implementable]
    if sensitivity:
        rows = []
        span = float(bt.robustness.get("sensitivity_range", 0.5))
        for label, (section, key, default) in SENSITIVITY.items():
            for factor in (1 - span, 1 + span):
                custom = config.model_copy(deep=True)
                block = getattr(custom.base, section)
                block[key] = float(block.get(key, default)) * factor
                d = Decider(custom, inputs, sims)
                d._base = decider._base  # Basis hängt nicht von diesen Parametern ab
                run = simulate(
                    "sens",
                    asset_returns,
                    d.tilt_strategy(_combined_probs(d)),
                    dates,
                    costs,
                    band,
                )
                trials.append(run.returns)
                m = metrics(run.returns, cash)
                rows.append(
                    {
                        "Parameter": label,
                        "Faktor": factor,
                        "Sharpe": m.get("Sharpe"),
                        "Rendite p. a.": m.get("Rendite p. a."),
                    }
                )
        result.sensitivity = pd.DataFrame(rows)
    monthly_sr = [float(r.mean() / r.std()) for r in trials if r.std() > 0]
    result.n_trials = len(trials)
    main = strategies.get("A + B + Overlay") or reference
    main_series = main.returns if isinstance(main, StrategyResult) else main
    result.deflated = deflated_sharpe(
        main_series - cash.reindex(main_series.index).fillna(0.0),
        len(trials),
        float(np.var(monthly_sr)) if monthly_sr else 0.0,
    )
    return result


def _placebo_probs(seq: pd.Series):  # type: ignore[no-untyped-def]
    def probs(t: pd.Timestamp) -> pd.Series | None:
        value = seq.get(t)
        return one_hot(str(value)) if pd.notna(value) else None

    return probs


def _combined_probs(decider: Decider):  # type: ignore[no-untyped-def]
    def probs(t: pd.Timestamp) -> pd.Series | None:
        return decider.probs("ab", t)

    return probs


# --------------------------------------------------------------------- Bericht
def _period_table(result: BacktestResult, start: str | None, end: str | None) -> pd.DataFrame:
    base = result.strategies["Basis (statisch)"].returns
    rows = {}
    for name, s in result.strategies.items():
        r = s.returns
        if start:
            r = r[r.index >= pd.Timestamp(start)]
        if end:
            r = r[r.index <= pd.Timestamp(end) + pd.offsets.MonthEnd(0)]
        m = metrics(r, result.cash, base, s.turnover, s.costs)
        if m:
            rows[name + ("" if s.implementable else " *")] = m
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("Strategie")


def _svg_lines(series: dict[str, pd.Series], title: str, log: bool = True) -> str:
    width, height, pad = 900, 320, 40
    frames = {k: v.dropna() for k, v in series.items() if not v.dropna().empty}
    if not frames:
        return ""
    all_vals = pd.concat(frames.values())
    lo, hi = float(all_vals.min()), float(all_vals.max())
    if log:
        lo, hi = np.log(max(lo, 1e-6)), np.log(hi)
    start = min(v.index.min() for v in frames.values())
    end = max(v.index.max() for v in frames.values())
    span = (end - start).days or 1
    colors = [
        "#1f77b4",
        "#d62728",
        "#2ca02c",
        "#9467bd",
        "#ff7f0e",
        "#8c564b",
        "#7f7f7f",
        "#17becf",
        "#bcbd22",
        "#e377c2",
    ]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        'style="max-width:100%">',
        f'<text x="{pad}" y="20" font-size="14">{html.escape(title)}</text>',
    ]
    for i, (name, s) in enumerate(frames.items()):
        pts = []
        for d, v in s.items():
            x = pad + (d - start).days / span * (width - 2 * pad)
            val = np.log(max(v, 1e-6)) if log else v
            y = height - pad - (val - lo) / ((hi - lo) or 1) * (height - 2 * pad)
            pts.append(f"{x:.1f},{y:.1f}")
        color = colors[i % len(colors)]
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.4" points="{" ".join(pts)}"/>'
        )
        parts.append(
            f'<text x="{width - 230}" y="{40 + 14 * i}" font-size="11" fill="{color}">'
            f"{html.escape(name)}</text>"
        )
    parts.append(f'<text x="{pad}" y="{height - 10}" font-size="11">{start.year}</text>')
    parts.append(f'<text x="{width - pad - 30}" y="{height - 10}" font-size="11">{end.year}</text>')
    parts.append("</svg>")
    return "".join(parts)


def write_report(
    config: AppConfig, paths: ProjectPaths, result: BacktestResult
) -> tuple[Path, Path]:
    """Markdown- und HTML-Bericht (8.5)."""
    paths.reports.mkdir(parents=True, exist_ok=True)
    p = config.backtest.periods
    lines = ["# Backtest", ""]
    if paths.demo:
        lines += [
            "> **DEMO-DATEN.** Synthetische Reihen; keine Aussage über Märkte oder Strategien.",
            "",
        ]
    lines += [
        f"Erstellt: {utc_now().isoformat(timespec='seconds')} · "
        f"Basiswährung {config.currency.base} · "
        f"Konfigurations-Hash `{config.config_hash[:12]}` (Parameter vor dem Lauf festgeschrieben)",
        "",
        f"Start {result.start.date()} (erste Entscheidung mit 60 Monaten Historie), quartalsweise "
        "Umschichtung mit No-Trade-Band, Kosten je Klasse. * = nicht umsetzbar (Obergrenze).",
        "",
        f"## Prüfzeitraum ab {p.get('test_start', '2008-01')} (nur echte Proxies, alle Klassen)",
        "",
        markdown_table(_period_table(result, str(p.get("test_start", "2008-01")), None), "{:.3f}"),
        f"## Entwicklungszeitraum bis {p.get('development_end', '2007-12')} "
        "(mit Backfill, teils synthetisch)",
        "",
        markdown_table(
            _period_table(result, None, str(p.get("development_end", "2007-12"))), "{:.3f}"
        ),
        "## Gesamte Historie",
        "",
        markdown_table(_period_table(result, None, None), "{:.3f}"),
        "## Stressphasen (Rendite über die Phase)",
        "",
    ]
    stress_rows = {}
    median_placebo = (
        float(np.nanmedian(result.placebo_sharpes)) if result.placebo_sharpes else float("nan")
    )
    for label, (a, b) in dict(p.get("stress", {})).items():
        row = {}
        for name, s in result.strategies.items():
            r = s.returns[
                (s.returns.index >= pd.Timestamp(a))
                & (s.returns.index <= pd.Timestamp(b) + pd.offsets.MonthEnd(0))
            ]
            row[name] = float((1 + r).prod() - 1) if len(r) else np.nan
        stress_rows[f"{label} ({a} bis {b})"] = row
    lines += [
        markdown_table(
            pd.DataFrame.from_dict(stress_rows, orient="index").rename_axis("Phase"), "{:+.3f}"
        )
    ]
    lines += [
        "## Placebo (zufällige Regimefolgen mit gleicher Verweildauer, Form ii)",
        "",
        f"Sharpe der echten Tilts A + B: {result.placebo_reference:.3f}; Placebo: Median "
        f"{median_placebo:.3f} über "
        f"{len(result.placebo_sharpes)} Folgen; **p-Wert {result.placebo_p:.3f}**.",
        "",
        "## Sensitivität (zentrale Parameter ±50 %, Form ii)",
        "",
        markdown_table(result.sensitivity, "{:.3f}"),
        f"## Deflated Sharpe Ratio (A + B + Overlay): {result.deflated:.3f} bei "
        f"{result.n_trials} getesteten Varianten",
        "",
        "## Rendite je Regime (Methode A, Monatsmittel % )",
        "",
    ]
    regime_rows = {}
    for name, s in result.strategies.items():
        aligned = result.regimes.shift(1).reindex(s.returns.index)
        regime_rows[name] = (s.returns.groupby(aligned).mean() * 100).to_dict()
    lines += [
        markdown_table(
            pd.DataFrame.from_dict(regime_rows, orient="index").rename_axis("Strategie"), "{:+.2f}"
        )
    ]
    md = paths.reports / "backtest_latest.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    wealth = {k: (1 + s.returns).cumprod() for k, s in result.strategies.items()}
    dd = {
        k: w / w.cummax() - 1
        for k, w in wealth.items()
        if k in ("Basis (statisch)", "A + B + Overlay", "60/40 (EUR)")
    }
    body = "".join(
        f"<pre>{html.escape(line)}</pre>" if line.startswith("|") else f"<p>{html.escape(line)}</p>"
        for line in lines
    )
    page = (
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>Backtest</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:auto}pre{margin:0;font-size:12px}</style></head><body>"
        + _svg_lines(wealth, "Wertentwicklung (log)")
        + _svg_lines({k: v + 1 for k, v in dd.items()}, "Drawdown", log=False)
        + body
        + "</body></html>"
    )
    page_path = paths.reports / "backtest_latest.html"
    page_path.write_text(page, encoding="utf-8")
    write_run(
        paths.runs,
        "backtest",
        config.config_hash,
        {"demo": paths.demo, "start": str(result.start.date()), "placebo_p": result.placebo_p},
    )
    return md, page_path


def load_inputs(config: AppConfig, paths: ProjectPaths, end: pd.Timestamp) -> Inputs:
    """Lädt Universum, Regime beider Methoden und Schuldenzyklus (je Monatsende, Point-in-Time)."""
    from navigator.config import QUADRANTS
    from navigator.data.pipeline import make_cache, make_providers
    from navigator.data.pit import PitStore
    from navigator.data.universe import SeriesLoader, UniverseBuilder
    from navigator.features.debt_stress import run_debt_stress
    from navigator.regimes import method_b
    from navigator.regimes.method_a import load_and_run

    store = PitStore(paths.pit)
    loader = SeriesLoader(make_cache(config, paths), make_providers(config, paths))
    universe = UniverseBuilder(config, loader).build(config.currency.base, end)
    result_a = load_and_run(config, paths, "1960-01", end)
    cmp = method_b.run_comparison(config, store, result_a.dates, result_a)
    debt = run_debt_stress(config, store, end)
    us = debt.monthly.get("US", pd.DataFrame())
    scores = pd.DataFrame({c: f["score"] for c, f in debt.monthly.items() if "score" in f})
    return Inputs(
        returns=universe.returns[universe.returns.index <= end],
        probs={
            "a": result_a.regimes["GLOBAL"][[f"p_{q}" for q in QUADRANTS]],
            "b": cmp.b.probs.rename(columns={q: f"p_{q}" for q in QUADRANTS}),
        },
        conviction=cmp.conviction,
        regimes=result_a.regimes["GLOBAL"]["regime"],
        debt_phase=us["phase"] if "phase" in us else pd.Series(dtype=object),
        debt_scores=scores,
    )
