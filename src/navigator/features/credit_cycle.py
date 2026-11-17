"""Kurzfristiger Schuldenzyklus (5 bis 8 Jahre) für die USA (Spezifikation Abschnitt 4.3).

Je Stichtag t werden fünf Größen aus dem damals bekannten Datenstand gebildet (Prozent bzw.
Prozentpunkte):

- realer Leitzins = Fed Funds (Monatsende) − Kerninflation über 12 Monate,
- Abstand zum neutralen Zins = realer Leitzins − r* (Laubach-Williams, Echtzeit-Schätzung);
  ohne bekannte Schätzung ersatzweise der Durchschnitt des realen Leitzinses über 10 Jahre,
- Zinskurve 10J.−3M und Kreditspread (Baa − 10J.) mit ihren 6-Monats-Veränderungen,
- Kreditimpuls = Wachstum der Bankkredite über 12 Monate minus dessen Durchschnitt über
  ``credit_trend_years`` Jahre.

Die Phasen und Schwellen stehen in ``config/regime_map.yaml`` (Abschnitt ``credit_cycle``);
eine Phase gilt, wenn mindestens zwei ihrer drei typischen Signale aus der Tabelle in 4.3
vorliegen. Prüfreihenfolge: Kontraktion, späte, frühe, sonst mittlere Expansion. Ein
Phasenwechsel zählt nach ``confirm_months`` Monaten in Folge. Zinskurve und Spread kommen
aus Tagesreihen, davor aus Monatsdurchschnitten (ab 1953).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.config import CreditCycleRules
from navigator.data.pit import PitStore
from navigator.features.scores import TransformFn, derived_series, pit_values

PHASES = ("early", "mid", "late", "contraction")
PHASE_LABELS = {
    "early": "Frühe Expansion",
    "mid": "Mittlere Expansion",
    "late": "Späte Expansion",
    "contraction": "Kontraktion",
}


def _load(
    store: PitStore, key: str, dates: pd.DatetimeIndex, frequency: str, func: TransformFn
) -> pd.Series:
    if key == "us_curve_long":
        series = derived_series(store, "us_gs10", "us_tb3ms", "M")
    else:
        series = store.load(f"indicator.{key}")
    if series is None:
        return pd.Series(np.nan, index=dates)
    values, _ = pit_values(series, dates, frequency, func)
    return values


def _daily_or_monthly(
    store: PitStore,
    daily: str,
    monthly: str,
    dates: pd.DatetimeIndex,
    func: TransformFn,
) -> pd.Series:
    """Tagesreihe, wo vorhanden; davor die längere Monatsreihe."""
    return _load(store, daily, dates, "D", func).combine_first(
        _load(store, monthly, dates, "M", func)
    )


def credit_inputs(
    store: PitStore, dates: pd.DatetimeIndex, rules: CreditCycleRules
) -> pd.DataFrame:
    """Eingangsgrößen des Schuldenzyklus je Stichtag (alle Point-in-Time)."""

    def same(x: pd.Series) -> pd.Series:
        return x

    def diff6(x: pd.Series) -> pd.Series:
        return x - x.shift(6)

    def diff12(x: pd.Series) -> pd.Series:
        return x - x.shift(12)

    def yoy(x: pd.Series) -> pd.Series:
        return (x / x.shift(12) - 1.0) * 100.0

    years = rules.credit_trend_years

    def impulse(x: pd.Series) -> pd.Series:
        growth = (x / x.shift(12) - 1.0) * 100.0
        return growth - growth.rolling(12 * years, min_periods=12 * years // 2).mean()

    def spread_median(x: pd.Series) -> pd.Series:
        return x.rolling(120, min_periods=60).median()

    policy = _load(store, "us_policy_rate", dates, "D", same)
    inflation = _load(store, "us_core_cpi", dates, "M", yoy)
    real = policy - inflation
    rstar = _load(store, "us_rstar", dates, "Q", same)
    fallback = real.rolling(120, min_periods=60).mean()
    neutral = rstar.where(rstar.notna(), fallback)
    return pd.DataFrame(
        {
            "policy_rate": policy,
            "policy_change_6m": _load(store, "us_policy_rate", dates, "D", diff6),
            "policy_change_12m": _load(store, "us_policy_rate", dates, "D", diff12),
            "core_inflation": inflation,
            "real_policy_rate": real,
            "neutral_rate": neutral,
            "neutral_source": np.where(rstar.notna(), "r* (LW)", "Ersatz: Ø 10 J."),
            "real_gap": real - neutral,
            "curve": _daily_or_monthly(store, "us_curve_10y3m", "us_curve_long", dates, same),
            "spread": _daily_or_monthly(
                store, "us_credit_spread", "us_credit_spread_long", dates, same
            ),
            "spread_change_6m": _daily_or_monthly(
                store, "us_credit_spread", "us_credit_spread_long", dates, diff6
            ),
            "spread_median_10y": _daily_or_monthly(
                store, "us_credit_spread", "us_credit_spread_long", dates, spread_median
            ),
            "credit_impulse": _load(store, "us_bank_credit", dates, "D", impulse),
        },
        index=dates,
    )


def phase_signals(row: pd.Series, rules: CreditCycleRules) -> dict[str, int]:
    """Anzahl erfüllter typischer Signale je Phase laut Tabelle in Abschnitt 4.3.

    Fehlende Eingaben zählen als nicht erfüllt.
    """

    def gt(value: float, threshold: float) -> bool:
        return bool(pd.notna(value) and value > threshold)

    def lt(value: float, threshold: float) -> bool:
        return bool(pd.notna(value) and value < threshold)

    tight = bool(
        pd.notna(row["spread"])
        and pd.notna(row["spread_median_10y"])
        and row["spread"] < row["spread_median_10y"]
    )
    return {
        # Spreads weiten sich, Leitzinssenkungen beginnen, Kreditwachstum fällt
        "contraction": int(gt(row["spread_change_6m"], rules.contraction_spread_widening))
        + int(lt(row["policy_change_6m"], -rules.contraction_policy_cut))
        + int(lt(row["credit_impulse"], 0.0)),
        # realer Leitzins über neutralem Zins, Kurve flach oder invers, Spreads sehr eng
        "late": int(gt(row["real_gap"], rules.late_real_gap_min))
        + int(lt(row["curve"], rules.late_curve_max))
        + int(tight),
        # Leitzins sinkt oder tief, Zinskurve steil, Spreads engen ein
        "early": int(
            lt(row["policy_change_12m"], -rules.early_policy_cut_12m)
            or lt(row["real_gap"], rules.early_real_gap_max)
        )
        + int(gt(row["curve"], rules.early_curve_min))
        + int(lt(row["spread_change_6m"], 0.0)),
    }


def raw_phase(row: pd.Series, rules: CreditCycleRules) -> str | None:
    """Phase eines Monats: mindestens zwei von drei typischen Signalen (Mehrheitsregel).

    Prüfreihenfolge Kontraktion, späte, frühe Expansion; sonst mittlere Expansion.
    """
    if pd.isna(row["policy_rate"]) or pd.isna(row["real_gap"]):
        return None
    signals = phase_signals(row, rules)
    for phase in ("contraction", "late", "early"):
        if signals[phase] >= 2:
            return phase
    return "mid"


def classify_credit_cycle(inputs: pd.DataFrame, rules: CreditCycleRules) -> pd.DataFrame:
    """Rohphase und bestätigte Phase je Monat."""
    raw = pd.Series([raw_phase(row, rules) for _, row in inputs.iterrows()], index=inputs.index)
    confirmed = pd.Series(None, index=inputs.index, dtype="object")
    current: str | None = None
    streak, previous = 0, None
    for when, phase in raw.items():
        if phase is None:
            current, streak, previous = None, 0, None
            continue
        streak = streak + 1 if phase == previous else 1
        previous = phase
        if current is None or (phase != current and streak >= rules.confirm_months):
            current = phase
        confirmed[when] = current
    out = inputs.copy()
    out["phase_raw"] = raw
    out["phase"] = confirmed
    return out
