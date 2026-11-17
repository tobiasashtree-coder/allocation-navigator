"""Synthetische Anleiherenditen aus Renditereihen (Spezifikation Abschnitt 9.5).

Wo keine Fondshistorie existiert, entsteht die Monatsrendite aus der Renditereihe:

    Rendite_t = y_{t-1} / 12  −  D · Δy  +  ½ · C · Δy²

Duration D und Konvexität C werden aus der Laufzeit abgeleitet (Anleihe zu pari,
halbjährlicher Kupon). Die synthetische Reihe wird in überlappenden Zeiträumen gegen
echte Fondsrenditen geprüft; Akzeptanzkriterium ist eine Korrelation über 0,95.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CORRELATION_THRESHOLD = 0.95


def par_bond_risk(
    yield_decimal: pd.Series | np.ndarray | float, maturity: float, freq: int = 2
) -> tuple[np.ndarray, np.ndarray]:
    """Modifizierte Duration und Konvexität einer Pari-Anleihe mit ``maturity`` Jahren Laufzeit."""
    y = np.atleast_1d(np.asarray(yield_decimal, dtype="float64"))
    n = maturity * freq
    duration = np.full_like(y, maturity)
    convexity = np.full_like(y, maturity * (maturity + 1.0 / freq))
    regular = np.abs(y) > 1e-4
    yr = y[regular]
    v = 1.0 / (1.0 + yr / freq)
    duration[regular] = (1.0 - v**n) / yr
    convexity[regular] = 2.0 * (1.0 - v**n) / yr**2 - 2.0 * n * v ** (n + 1) / (freq * yr)
    return duration, convexity


def synthetic_bond_returns(yield_percent: pd.Series, maturity: float) -> pd.Series:
    """Monatsrenditen einer Anleihe konstanter Laufzeit aus Monatsendrenditen (in Prozent)."""
    y = (yield_percent.dropna().sort_index() / 100.0).astype("float64")
    previous = y.shift(1)
    change = y - previous
    duration, convexity = par_bond_risk(previous.fillna(0.0), maturity)
    result = previous / 12.0 - duration * change + 0.5 * convexity * change**2
    return result.dropna().rename("synthetic_bond")


def synthetic_linker_returns(
    real_yield_percent: pd.Series, cpi_index: pd.Series, maturity: float, lag_months: int = 3
) -> pd.Series:
    """Monatsrenditen inflationsindexierter Anleihen aus Realrenditen und Preisindex.

    Zum realen Ertrag kommt der Inflationsausgleich. Er folgt dem Preisindex mit
    ``lag_months`` Verzögerung (Indexierungsverzug), sodass nur bereits veröffentlichte
    Preisdaten einfließen.
    """
    real = synthetic_bond_returns(real_yield_percent, maturity)
    inflation = cpi_index.dropna().sort_index().pct_change(fill_method=None).shift(lag_months - 1)
    joined = pd.concat([real, inflation], axis=1, join="inner").dropna()
    return (joined.iloc[:, 0] + joined.iloc[:, 1]).rename("synthetic_linker")


def blend_returns(components: list[tuple[pd.Series, float]]) -> pd.Series:
    """Gewichtete Mischung von Renditereihen (nur Monate, in denen alle Bestandteile vorliegen)."""
    frame = pd.concat([series for series, _ in components], axis=1, join="inner").dropna()
    weights = np.array([weight for _, weight in components])
    return pd.Series(frame.to_numpy() @ weights, index=frame.index, name="blend")


@dataclass(frozen=True)
class SyntheticCheck:
    """Ergebnis der Prüfung einer synthetischen Reihe gegen echte Fondsrenditen."""

    months: int
    correlation: float
    tracking_error_annual: float
    accepted: bool


def check_against_fund(
    synthetic: pd.Series, fund: pd.Series, threshold: float = CORRELATION_THRESHOLD
) -> SyntheticCheck:
    """Vergleicht synthetische und echte Renditen im überlappenden Zeitraum."""
    joined = pd.concat([synthetic, fund], axis=1, join="inner").dropna()
    if len(joined) < 12:
        return SyntheticCheck(len(joined), float("nan"), float("nan"), False)
    corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
    te = float((joined.iloc[:, 0] - joined.iloc[:, 1]).std() * np.sqrt(12.0))
    return SyntheticCheck(len(joined), corr, te, bool(corr > threshold))
