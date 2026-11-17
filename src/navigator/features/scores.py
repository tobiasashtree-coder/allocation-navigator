"""Wachstums- und Inflationsscore je Region (Spezifikation Abschnitt 4.1).

Für jeden Monatsende-Stichtag t gilt:

1. Je Indikator wird der Datenstand verwendet, der zu t bekannt war (Point-in-Time-Speicher).
2. Transformation: 6-Monats-Veränderung (bzw. bei der Kerninflation die Differenz aus
   3-Monats-Rate annualisiert und 12-Monats-Rate), dann z-Wert gegen das rollierende
   10-Jahres-Fenster bis einschließlich der jüngsten Beobachtung, begrenzt auf ±3.
3. Der Score einer Achse ist der Mittelwert der z-Werte ihrer Indikatoren.

Ein Indikator fällt zu t aus, wenn seine jüngste bekannte Beobachtung zu alt ist (siehe
``MAX_AGE_MONTHS``). So fließen keine veralteten Daten stillschweigend ein.

Rechenweg: Reihen ohne Revisionen werden einmal transformiert; ihr Wert zu t ist der z-Wert
der jüngsten zu t bekannten Beobachtung. Das ist exakt, weil alle Fenster nach hinten
gerichtet sind. Reihen mit echten Vintages werden für jeden Stichtag aus dem damaligen
Datenstand neu berechnet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from navigator.config import Indicator, IndicatorDefaults, IndicatorsConfig
from navigator.data.pit import PitSeries, PitStore

log = logging.getLogger(__name__)

AXES = ("growth", "inflation")
PERIODS_PER_YEAR = {"D": 12, "M": 12, "Q": 4, "A": 1}
MAX_AGE_MONTHS = {"D": 1, "M": 4, "Q": 9, "A": 18}
MIN_INDICATORS = 2


def period_index(dates: pd.Series | pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    """Periodenende einer Beobachtung (Tagesreihen: Monatsende des Tages)."""
    index = pd.DatetimeIndex(dates).normalize()
    if frequency == "Q":
        return pd.DatetimeIndex(index + pd.offsets.QuarterEnd(0))
    if frequency == "A":
        return pd.DatetimeIndex(index + pd.offsets.YearEnd(0))
    return pd.DatetimeIndex(index + pd.offsets.MonthEnd(0))


def to_periods(series: pd.Series, frequency: str) -> pd.Series:
    """Ordnet Beobachtungen ihrer Periode zu; bei Tagesreihen zählt der letzte Wert im Monat."""
    clean = series.dropna().sort_index()
    if clean.empty:
        return clean
    periods = period_index(clean.index, frequency)
    out = pd.Series(clean.to_numpy(), index=periods)
    return out[~out.index.duplicated(keep="last")]


def transform(series: pd.Series, indicator: Indicator, defaults: IndicatorDefaults) -> pd.Series:
    """Veränderung laut Konfiguration und rollierender z-Wert (Formel aus Abschnitt 4.1)."""
    per_year = PERIODS_PER_YEAR[indicator.frequency]
    lag = max(1, round(defaults.change_months * per_year / 12))
    x = series.astype("float64")
    if indicator.change == "pct":
        change = x / x.shift(lag) - 1.0
    elif indicator.change == "diff":
        change = x - x.shift(lag)
    elif indicator.change == "core_momentum":
        three = max(1, round(3 * per_year / 12))
        change = (x / x.shift(three)) ** (per_year / three) - 1.0 - (x / x.shift(per_year) - 1.0)
    else:
        change = x
    if indicator.invert:
        change = -change
    window = max(2, round(defaults.zscore_window_months * per_year / 12))
    minimum = max(2, round(defaults.zscore_min_months * per_year / 12))
    rolling = change.rolling(window, min_periods=minimum)
    z = (change - rolling.mean()) / rolling.std()
    return z.clip(-defaults.clip, defaults.clip).replace([np.inf, -np.inf], np.nan)


def _known_period(frame: pd.DataFrame, frequency: str) -> pd.Series:
    """Für Reihen ohne Revisionen: ab welchem Monatsende jede Periode bekannt ist."""
    periods = period_index(frame["obs_date"], frequency)
    known = pd.DatetimeIndex(frame["known_from"]).normalize()
    table = pd.DataFrame({"period": periods, "known": known})
    # Ein Monatswert einer Tagesreihe ist bekannt, sobald der letzte Tag des Monats bekannt ist.
    return table.groupby("period")["known"].max()


@dataclass
class IndicatorValues:
    """z-Werte eines Indikators je Stichtag sowie das Datum der verwendeten Beobachtung."""

    key: str
    z: pd.Series
    observation: pd.Series


TransformFn = Callable[[pd.Series], pd.Series]


def pit_values(
    series: PitSeries, dates: pd.DatetimeIndex, frequency: str, func: TransformFn
) -> tuple[pd.Series, pd.Series]:
    """Wert von ``func`` zur jüngsten zu t bekannten Periode, für jeden Stichtag t.

    ``func`` bildet eine Periodenreihe auf eine gleich indizierte Reihe ab und darf nur
    nach hinten schauen (rollierende Fenster, Verschiebungen). Liefert die Werte und die
    Periode der verwendeten Beobachtung; zu alte Beobachtungen ergeben NaN.
    """
    values = pd.Series(np.nan, index=dates)
    obs = pd.Series(pd.NaT, index=dates, dtype="datetime64[ns]")
    if series.frame.empty:
        return values, obs
    if series.revision_count() == 0:
        full = func(to_periods(series.latest(), frequency))
        known = _known_period(series.frame, frequency).reindex(full.index).dropna()
        known_sorted = known.sort_values()
        stamps = known_sorted.to_numpy()
        running_max = pd.Series(known_sorted.index, index=known_sorted.index).cummax()
        positions = np.searchsorted(stamps, dates.to_numpy(), side="right") - 1
        for i, pos in enumerate(positions):
            if pos < 0:
                continue
            period = running_max.iloc[pos]
            values.iloc[i] = full.get(period, np.nan)
            obs.iloc[i] = period
    else:
        for i, when in enumerate(dates):
            vintage = series.as_of(when)
            if vintage.empty:
                continue
            full = func(to_periods(vintage, frequency))
            values.iloc[i] = full.iloc[-1]
            obs.iloc[i] = full.index[-1]
    age = (dates.year - obs.dt.year) * 12 + (dates.month - obs.dt.month)
    values[age.to_numpy() > MAX_AGE_MONTHS[frequency]] = np.nan
    return values, obs


def indicator_values(
    key: str,
    indicator: Indicator,
    series: PitSeries,
    dates: pd.DatetimeIndex,
    defaults: IndicatorDefaults,
) -> IndicatorValues:
    """Point-in-Time-z-Werte eines Indikators für alle Stichtage ``dates``."""
    z, obs = pit_values(
        series, dates, indicator.frequency, lambda x: transform(x, indicator, defaults)
    )
    return IndicatorValues(key, z, obs)


def derived_series(store: PitStore, a: str, b: str, frequency: str) -> PitSeries | None:
    """Differenz zweier Reihen ohne Revisionen (z. B. Zinskurve = 10J.-Rendite − 3M-Satz)."""
    first, second = store.load(f"indicator.{a}"), store.load(f"indicator.{b}")
    if first is None or second is None or first.frame.empty or second.frame.empty:
        return None
    left = to_periods(first.latest(), frequency)
    right = to_periods(second.latest(), frequency)
    joined = pd.concat([left, right], axis=1, join="inner").dropna()
    known = pd.concat(
        [_known_period(first.frame, frequency), _known_period(second.frame, frequency)],
        axis=1,
        sort=True,
    ).max(axis=1)
    frame = pd.DataFrame(
        {
            "obs_date": joined.index,
            "value": (joined.iloc[:, 0] - joined.iloc[:, 1]).to_numpy(),
            "known_from": known.reindex(joined.index).to_numpy(),
        }
    )
    return PitSeries(f"{a}-{b}", frame.dropna())


@dataclass
class Scores:
    """Scores je Region und Achse sowie die Beiträge der Indikatoren."""

    dates: pd.DatetimeIndex
    region_scores: pd.DataFrame  # Spalten (Region, Achse)
    global_scores: pd.DataFrame  # Spalten growth, inflation
    z: pd.DataFrame  # Spalten = Indikator
    observation: pd.DataFrame
    members: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    def contributions(self, when: pd.Timestamp, region: str, axis: str) -> pd.Series:
        """Beitrag jedes Indikators zum Score (z-Wert / Anzahl verfügbarer Indikatoren)."""
        keys = self.members.get((region, axis), [])
        values = self.z.loc[when, keys].dropna() if keys else pd.Series(dtype="float64")
        return values / len(values) if len(values) else values


def compute_scores(
    config: IndicatorsConfig,
    store: PitStore,
    dates: pd.DatetimeIndex,
    regions: tuple[str, ...] = ("US", "EA"),
) -> Scores:
    """Berechnet alle Scores für die Stichtage ``dates`` (Monatsenden)."""
    defaults = config.defaults
    z_cols: dict[str, pd.Series] = {}
    obs_cols: dict[str, pd.Series] = {}
    members: dict[tuple[str, str], list[str]] = {}
    for key, indicator in config.indicators.items():
        if indicator.axis not in AXES:
            continue
        if indicator.derived_from:
            first, second = indicator.derived_from
            series = derived_series(store, first, second, indicator.frequency)
        else:
            series = store.load(f"indicator.{key}")
        if series is None:
            log.warning("Indikator %s fehlt im Point-in-Time-Speicher", key)
            continue
        values = indicator_values(key, indicator, series, dates, defaults)
        z_cols[key], obs_cols[key] = values.z, values.observation
        targets = regions if indicator.region == "GLOBAL" else (indicator.region,)
        for region in targets:
            if region in regions:
                members.setdefault((region, indicator.axis), []).append(key)
    z = pd.DataFrame(z_cols, index=dates)
    observation = pd.DataFrame(obs_cols, index=dates)
    region_cols: dict[tuple[str, str], pd.Series] = {}
    for region in regions:
        for axis in AXES:
            keys = [k for k in members.get((region, axis), []) if k in z.columns]
            block = z[keys] if keys else pd.DataFrame(index=dates)
            count = block.notna().sum(axis=1)
            score = block.mean(axis=1).where(count >= MIN_INDICATORS)
            region_cols[(region, axis)] = score
    region_scores = pd.DataFrame(region_cols, index=dates)
    region_scores.columns = pd.MultiIndex.from_tuples(region_scores.columns)
    weights = {r: config.region_weights.get(r, 0.0) for r in regions}
    global_cols = {}
    for axis in AXES:
        values = pd.DataFrame({r: region_scores[(r, axis)] for r in regions})
        w = pd.DataFrame({r: np.where(values[r].notna(), weights[r], 0.0) for r in regions})
        w.index = values.index
        total = w.sum(axis=1)
        global_cols[axis] = (values.fillna(0.0) * w).sum(axis=1) / total.where(total > 0)
    return Scores(
        dates=dates,
        region_scores=region_scores,
        global_scores=pd.DataFrame(global_cols, index=dates),
        z=z,
        observation=observation,
        members=members,
    )
