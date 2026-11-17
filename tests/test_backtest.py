"""Backtest (M6): Simulation, Kennzahlen, Placebo, Look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from navigator.backtest.engine import Decider, Inputs, placebo_sequences, rebalance_dates, simulate
from navigator.backtest.metrics import deflated_sharpe, metrics
from navigator.backtest.run import run_backtest
from navigator.config import QUADRANTS, AppConfig


def _inputs(config: AppConfig, months: int = 150, seed: int = 5) -> Inputs:
    rng = np.random.default_rng(seed)
    assets = list(config.universe.enabled_assets())
    index = pd.date_range("2000-01-31", periods=months, freq="ME")
    vols = rng.uniform(0.01, 0.05, size=len(assets))
    data = rng.normal(0.004, 1.0, size=(months, len(assets))) * vols
    returns = pd.DataFrame(data, index=index, columns=assets)
    returns["cash"] = 0.001
    returns.loc[index[:40], "bitcoin"] = np.nan  # spät verfügbare Klasse
    probs = {}
    for k, s in (("a", 1), ("b", 2)):
        raw = np.random.default_rng(s).dirichlet(np.ones(4), size=months)
        probs[k] = pd.DataFrame(raw, index=index, columns=[f"p_{q}" for q in QUADRANTS])
    regimes = probs["a"].idxmax(axis=1).str.removeprefix("p_")
    phase = pd.Series("Spätphase (Finanzierungsstress)", index=index)
    scores = pd.DataFrame({"US": 70.0, "DE": 40.0, "JP": 80.0}, index=index)
    return Inputs(returns, probs, pd.Series(0.5, index=index), regimes, phase, scores)


def test_metrics_basic() -> None:
    r = pd.Series([0.01] * 24, index=pd.date_range("2020-01-31", periods=24, freq="ME"))
    r.iloc[5] = -0.05
    m = metrics(r, pd.Series(0.0, index=r.index))
    assert m["Max. Drawdown"] == pytest.approx(-0.05)
    assert m["Rendite p. a."] > 0
    assert 0 <= deflated_sharpe(r, 10, 0.01) <= 1


def test_placebo_preserves_dwell_times() -> None:
    regimes = pd.Series(["a"] * 5 + ["b"] * 3 + ["c"] * 7, index=range(15))
    seqs = placebo_sequences(regimes, 20, 1)
    for seq in seqs:
        assert len(seq) == 15
        lengths = sorted((seq != seq.shift()).cumsum().value_counts().tolist())
        assert sum(lengths) == 15


def test_costs_and_drift(config: AppConfig) -> None:
    inputs = _inputs(config)
    dates = rebalance_dates(inputs.returns.index, "2006-01", "quarterly")
    decider = Decider(config, inputs, 2)
    result = simulate(
        "Basis", inputs.returns, decider.static_base, dates, dict(config.backtest.costs_bps), 0.0
    )
    assert (result.weights.sum(axis=1) - 1).abs().max() < 1e-9
    assert (result.costs >= 0).all() and result.costs.iloc[0] > 0  # Erstkauf kostet
    assert (result.returns <= result.gross + 1e-15).all()


def test_no_lookahead_in_backtest_decisions(config: AppConfig) -> None:
    """Alle Daten nach t verändert: alle Gewichte bis einschließlich t+1 unverändert."""
    inputs = _inputs(config)
    when = inputs.returns.index[110]
    later = inputs.returns.index > when
    rng = np.random.default_rng(3)
    changed = Inputs(
        inputs.returns.copy(),
        {k: v.copy() for k, v in inputs.probs.items()},
        inputs.conviction.copy(),
        inputs.regimes.copy(),
        inputs.debt_phase.copy(),
        inputs.debt_scores.copy(),
    )
    changed.returns.loc[later] = rng.normal(0, 0.1, size=changed.returns.loc[later].shape)
    for frame in changed.probs.values():
        frame.loc[later] = rng.dirichlet(np.ones(4), size=int(later.sum()))
    changed.conviction[later] = 0.01
    changed.regimes[later] = "stagflation"
    changed.debt_phase[later] = "gesund"
    changed.debt_scores.loc[later] = 10.0
    dates = rebalance_dates(inputs.returns.index, "2006-01", "quarterly")
    costs = dict(config.backtest.costs_bps)
    for build in ("static", "ab+overlay", "tilt"):
        runs = []
        for data in (inputs, changed):
            d = Decider(config, data, 3)
            fn = {
                "static": d.static_base,
                "ab+overlay": d.regime("ab", True),
                "tilt": d.tilt_strategy(lambda t, d=d: d.probs("ab", t)),
            }[build]
            runs.append(simulate(build, data.returns, fn, dates, costs, 0.02))
        a, b = runs
        cut = a.weights.index <= when + pd.offsets.MonthEnd(1)
        wa, wb = a.weights[cut], b.weights[cut]
        wa, wb = wa.loc[:, (wa != 0).any()], wb.loc[:, (wb != 0).any()]
        pd.testing.assert_frame_equal(wa, wb)


def test_run_backtest_small(config: AppConfig) -> None:
    custom = config.model_copy(deep=True)
    custom.backtest.periods["long_history_start"] = "2006-01"
    result = run_backtest(custom, _inputs(custom), placebo_runs=3, simulations=2, sensitivity=False)
    assert "Voraussicht (nicht umsetzbar)" in result.strategies
    assert not result.strategies["Voraussicht (nicht umsetzbar)"].implementable
    assert len(result.placebo_sharpes) == 3
    assert 0 < result.placebo_p <= 1
