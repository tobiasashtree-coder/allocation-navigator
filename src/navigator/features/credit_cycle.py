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
die Prüfreihenfolge ist Kontraktion, späte, frühe, sonst mittlere Expansion. Ein
Phasenwechsel zählt nach ``confirm_months`` Monaten in Folge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.config import CreditCycleRules
from navigator.data.pit import PitStore
from navigator.features.scores import pit_values

PHASES = ("early", "mid", "late", "contraction")
PHASE_LABELS = {
    "early": "Frühe Expansion",
    "mid": "Mittlere Expansion",
    "late": "Späte Expansion",
    "contraction": "Kontraktion",
}


def _load(store: PitStore, key: str, dates: pd.DatetimeIndex, frequency: str, func) -> pd.Series:  # type: ignore[no-untyped-def]
    series = store.load(f"indicator.{key}")
    if series is None:
        return pd.Series(np.nan, index=dates)
    values, _ = pit_values(series, dates, frequency, func)
    return values


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
            "curve": _load(store, "us_curve_10y3m", dates, "D", same),
            "spread": _load(store, "us_credit_spread", dates, "D", same),
            "spread_change_6m": _load(store, "us_credit_spread", dates, "D", diff6),
            "spread_median_10y": _load(store, "us_credit_spread", dates, "D", spread_median),
            "credit_impulse": _load(store, "us_bank_credit", dates, "D", impulse),
        },
        index=dates,
    )


def raw_phase(row: pd.Series, rules: CreditCycleRules) -> str | None:
    """Phase eines Monats nach den dokumentierten Schwellen (ohne Bestätigungsregel)."""
    if pd.isna(row["policy_rate"]) or pd.isna(row["real_gap"]):
        return None

    def gt(value: float, threshold: float) -> bool:
        return bool(pd.notna(value) and value > threshold)

    def lt(value: float, threshold: float) -> bool:
        return bool(pd.notna(value) and value < threshold)

    widening = gt(row["spread_change_6m"], rules.contraction_spread_widening)
    cutting = lt(row["policy_change_6m"], -rules.contraction_policy_cut)
    credit_falling = lt(row["credit_impulse"], 0.0)
    if widening and (cutting or credit_falling):
        return "contraction"
    tight_spread = (
        pd.isna(row["spread"])
        or pd.isna(row["spread_median_10y"])
        or (row["spread"] < row["spread_median_10y"])
    )
    restrictive = gt(row["real_gap"], rules.late_real_gap_min)
    if restrictive and lt(row["curve"], rules.late_curve_max) and tight_spread:
        return "late"
    eased = lt(row["policy_change_12m"], -rules.early_policy_cut_12m)
    loose = lt(row["real_gap"], rules.early_real_gap_max) and gt(
        row["curve"], rules.early_curve_min
    )
    not_widening = pd.isna(row["spread_change_6m"]) or row["spread_change_6m"] <= 0.0
    if (eased or loose) and not_widening:
        return "early"
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
