"""Merkmale für Methode B (Spezifikation Abschnitt 5.1).

Zu den Rohindikatoren aus 4.1 (als Point-in-Time-z-Werte, ohne Handgewichtung) kommen vier
Marktmerkmale, jeweils zum Monatsende t aus Daten bis t und **als 6-Monats-Veränderung** wie
alle Indikatoren aus 4.1 (Entscheidung am Prüfpunkt M3, E-56):

- ``stock_bond_corr_change_6m``: Veränderung der Korrelation täglicher S&P-500-Renditen mit
  den täglichen Anleiherenditen (≈ −Veränderung der 10J.-Rendite) über 252 Handelstage,
- ``equity_vol_change_6m``: Veränderung der realisierten S&P-500-Volatilität über 63 Tage,
- ``real_yield_change_6m``: Veränderung der Realrendite (10J.-Rendite minus Kerninflation über
  12 Monate, beide zum jeweiligen Stichtag bekannt),
- ``credit_spread_change_6m``: Veränderung des Kreditspreads Baa minus 10J.

Alle Merkmale werden wie in 4.1 standardisiert: z-Wert gegen das rollierende 10-Jahres-Fenster
der damals bekannten Werte, begrenzt auf ±3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.config import CreditCycleRules, IndicatorDefaults
from navigator.data.pit import PitStore
from navigator.features.credit_cycle import credit_inputs
from navigator.features.scores import Scores, pit_values

MARKET_FEATURES = (
    "stock_bond_corr_change_6m",
    "equity_vol_change_6m",
    "real_yield_change_6m",
    "credit_spread_change_6m",
)


def rolling_z(series: pd.Series, defaults: IndicatorDefaults) -> pd.Series:
    """z-Wert gegen das rollierende Fenster der bisherigen Werte (nur nach hinten)."""
    rolling = series.rolling(defaults.zscore_window_months, min_periods=defaults.zscore_min_months)
    z = (series - rolling.mean()) / rolling.std()
    return z.clip(-defaults.clip, defaults.clip).replace([np.inf, -np.inf], np.nan)


def _daily(store: PitStore, key: str) -> pd.Series:
    series = store.load(f"indicator.{key}")
    if series is None or series.frame.empty:
        return pd.Series(dtype="float64")
    out = series.latest()
    out.index = pd.DatetimeIndex(out.index).normalize()
    return out.sort_index()


def _at_month_ends(daily: pd.Series, dates: pd.DatetimeIndex, max_gap_days: int = 7) -> pd.Series:
    """Letzter Tageswert bis zum Monatsende; zu alte Werte ergeben NaN."""
    if daily.empty:
        return pd.Series(np.nan, index=dates)
    positions = np.searchsorted(daily.index.to_numpy(), dates.to_numpy(), side="right") - 1
    out = pd.Series(np.nan, index=dates)
    for i, pos in enumerate(positions):
        if pos >= 0 and (dates[i] - daily.index[pos]).days <= max_gap_days:
            out.iloc[i] = daily.iloc[pos]
    return out


def _change(series: pd.Series, months: int = 6) -> pd.Series:
    """6-Monats-Veränderung einer Monatsreihe (nur nach hinten)."""
    return series - series.shift(months)


def market_features(
    store: PitStore,
    dates: pd.DatetimeIndex,
    defaults: IndicatorDefaults,
    credit_rules: CreditCycleRules,
) -> pd.DataFrame:
    """Marktmerkmale je Stichtag als 6-Monats-Veränderung (noch nicht standardisiert)."""
    equity = _daily(store, "us_equity_price")
    yields = _daily(store, "us_dgs10")
    eq_ret = np.log(equity).diff()
    bond_ret = -(yields.diff()) / 100.0
    joined = pd.concat([eq_ret, bond_ret], axis=1, join="inner").dropna()
    joined.columns = ["equity", "bond"]
    corr = joined["equity"].rolling(252, min_periods=200).corr(joined["bond"])
    vol = eq_ret.rolling(63, min_periods=50).std() * np.sqrt(252.0)

    core = store.load("indicator.us_core_cpi")
    if core is None:
        inflation = pd.Series(np.nan, index=dates)
    else:
        inflation, _ = pit_values(core, dates, "M", lambda x: (x / x.shift(12) - 1.0) * 100.0)
    real = _at_month_ends(yields, dates) - inflation
    spread = credit_inputs(store, dates, credit_rules)["spread"]
    return pd.DataFrame(
        {
            "stock_bond_corr_change_6m": _change(_at_month_ends(corr.dropna(), dates)),
            "equity_vol_change_6m": _change(_at_month_ends(vol.dropna(), dates)),
            "real_yield_change_6m": _change(real),
            "credit_spread_change_6m": _change(spread),
        },
        index=dates,
    )


def feature_matrix(
    scores: Scores,
    store: PitStore,
    indicator_features: list[str],
    market: list[str],
    defaults: IndicatorDefaults,
    credit_rules: CreditCycleRules,
) -> pd.DataFrame:
    """Standardisierte Merkmale der Methode B je Stichtag (Point-in-Time)."""
    dates = scores.dates
    columns = {key: scores.z[key] for key in indicator_features if key in scores.z.columns}
    raw = market_features(store, dates, defaults, credit_rules) if market else pd.DataFrame()
    for key in market:
        if key in raw.columns:
            columns[key] = rolling_z(raw[key], defaults)
    return pd.DataFrame(columns, index=dates)
