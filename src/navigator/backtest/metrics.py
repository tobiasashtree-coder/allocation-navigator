"""Kennzahlen des Backtests (Spezifikation 8.3) und Deflated Sharpe Ratio (8.4)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm


def metrics(
    returns: pd.Series,
    cash: pd.Series,
    base: pd.Series | None = None,
    turnover: pd.Series | None = None,
    costs: pd.Series | None = None,
) -> dict[str, float]:
    """Rendite, Risiko und Kennzahlen für Monatsrenditen (Sharpe und Sortino gegen Cash)."""
    r = returns.dropna()
    if len(r) < 12:
        return {}
    c = cash.reindex(r.index).fillna(0.0)
    excess = r - c
    years = len(r) / 12
    wealth = (1 + r).cumprod()
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1)
    vol = float(r.std() * math.sqrt(12))
    sharpe = float(excess.mean() / excess.std() * math.sqrt(12)) if excess.std() > 0 else np.nan
    downside = excess[excess < 0]
    dd_dev = math.sqrt(float((downside**2).sum() / len(excess))) * math.sqrt(12)
    sortino = float(excess.mean() * 12 / dd_dev) if dd_dev > 0 else np.nan
    drawdown = wealth / wealth.cummax() - 1
    max_dd = float(drawdown.min())
    rolling = (1 + r).rolling(12).apply(np.prod, raw=True) - 1
    q = r.quantile(0.05)
    out = {
        "Rendite p. a.": cagr,
        "Volatilität": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max. Drawdown": max_dd,
        "Calmar": cagr / abs(max_dd) if max_dd < 0 else np.nan,
        "Schlechteste 12 M.": float(rolling.min()),
        "CVaR 5 % (Monat)": float(r[r <= q].mean()),
    }
    if base is not None:
        active = r - base.reindex(r.index).fillna(0.0)
        te = float(active.std() * math.sqrt(12))
        out["Tracking Error"] = te
        out["Information Ratio"] = float(active.mean() * 12 / te) if te > 0 else np.nan
    if turnover is not None:
        out["Umschlag p. a."] = float(turnover.reindex(r.index).fillna(0.0).sum() / years)
    if costs is not None:
        out["Kosten p. a."] = float(costs.reindex(r.index).fillna(0.0).sum() / years)
    return out


def deflated_sharpe(returns: pd.Series, n_trials: int, sharpe_variance: float) -> float:
    """Deflated Sharpe Ratio nach Bailey und López de Prado (2014).

    Wahrscheinlichkeit, dass die wahre Sharpe-Ratio (monatlich) über dem erwarteten Maximum
    von ``n_trials`` unabhängigen Versuchen ohne Können liegt. ``sharpe_variance`` ist die
    Varianz der monatlichen Sharpe-Ratios der getesteten Varianten.
    """
    r = returns.dropna()
    t = len(r)
    if t < 24 or r.std() == 0:
        return float("nan")
    sr = float(r.mean() / r.std())
    gamma = 0.5772156649
    n = max(n_trials, 2)
    expected_max = math.sqrt(max(sharpe_variance, 1e-12)) * (
        (1 - gamma) * norm.ppf(1 - 1 / n) + gamma * norm.ppf(1 - 1 / (n * math.e))
    )
    skew = float(r.skew())
    kurt = float(r.kurt()) + 3.0
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, 1e-12))
    return float(norm.cdf((sr - expected_max) * math.sqrt(t - 1) / denom))
