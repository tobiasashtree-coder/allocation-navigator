"""Methode A: regelbasierte Regime-Erkennung (Spezifikation Abschnitt 4.2).

Aus den Scores für Wachstum und Inflation entstehen Wahrscheinlichkeiten,

    P(Achse steigt) = 1 / (1 + exp(−k · S)),  k = 1,5,

und daraus die vier Quadranten-Wahrscheinlichkeiten als Produkt der Achsen.

Gegen hektisches Hin- und Herspringen gelten zwei Regeln:

- **Neutrales Band:** Liegt ein Score zwischen −0,25 und +0,25, behält die Achse ihre
  bisherige Richtung. Erst ein Score jenseits des Bands kehrt die Richtung um. Daraus folgt
  der Kandidat für das Regime.
- **Bestätigung:** Das Regime wechselt erst, wenn derselbe Kandidat zwei Monate in Folge
  vorliegt oder seine Wahrscheinlichkeit 60 % übersteigt.

Jeder Wert zu t hängt nur von Scores bis t ab.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.config import QUADRANTS, RegimeRules

# Quadrant aus den Richtungen (Wachstum, Inflation)
QUADRANT_OF = {
    (1, -1): "disinflationary_boom",
    (1, 1): "reflation",
    (-1, -1): "deflationary_bust",
    (-1, 1): "stagflation",
}
LABELS = {
    "disinflationary_boom": "Disinflationärer Aufschwung",
    "reflation": "Reflation / Überhitzung",
    "deflationary_bust": "Deflationäre Rezession",
    "stagflation": "Stagflation",
}


def logistic(score: pd.Series, k: float) -> pd.Series:
    """Wahrscheinlichkeit, dass die Achse steigt."""
    return 1.0 / (1.0 + np.exp(-k * score))


def quadrant_probabilities(growth: pd.Series, inflation: pd.Series, k: float) -> pd.DataFrame:
    """Wahrscheinlichkeit je Quadrant als Produkt der Achsen-Wahrscheinlichkeiten."""
    pg, pi = logistic(growth, k), logistic(inflation, k)
    return pd.DataFrame(
        {
            "disinflationary_boom": pg * (1.0 - pi),
            "reflation": pg * pi,
            "deflationary_bust": (1.0 - pg) * (1.0 - pi),
            "stagflation": (1.0 - pg) * pi,
        }
    )[list(QUADRANTS)]


def _directions(score: pd.Series, band: float) -> pd.Series:
    """Richtung je Monat mit neutralem Band (Hysterese); NaN, solange kein Score vorliegt."""
    out = pd.Series(np.nan, index=score.index)
    current = np.nan
    for when, value in score.items():
        if np.isnan(value):
            out[when] = np.nan
            current = np.nan
            continue
        if value > band:
            current = 1.0
        elif value < -band:
            current = -1.0
        elif np.isnan(current):
            current = 1.0 if value >= 0 else -1.0
        out[when] = current
    return out


def classify(growth: pd.Series, inflation: pd.Series, rules: RegimeRules) -> pd.DataFrame:
    """Wahrscheinlichkeiten, führender Quadrant, Kandidat und bestätigtes Regime je Monat."""
    probs = quadrant_probabilities(growth, inflation, rules.logistic_k)
    g_dir = _directions(growth, rules.neutral_band)
    i_dir = _directions(inflation, rules.neutral_band)
    candidate = pd.Series(
        [
            QUADRANT_OF.get((int(g), int(i))) if not (np.isnan(g) or np.isnan(i)) else None
            for g, i in zip(g_dir, i_dir, strict=True)
        ],
        index=growth.index,
        dtype="object",
    )
    complete = probs.notna().all(axis=1)
    leading = pd.Series(None, index=probs.index, dtype="object")
    if complete.any():
        leading[complete] = probs[complete].idxmax(axis=1)
    regime = pd.Series(None, index=growth.index, dtype="object")
    current: str | None = None
    streak = 0
    previous_candidate: str | None = None
    for when in growth.index:
        cand = candidate[when]
        if cand is None:
            current, streak, previous_candidate = None, 0, None
            continue
        streak = streak + 1 if cand == previous_candidate else 1
        previous_candidate = cand
        if current is None:
            current = cand
        elif cand != current:
            strong = probs.loc[when, cand] > rules.switch_probability
            if streak >= rules.confirm_months or strong:
                current = cand
        regime[when] = current
    out = probs.add_prefix("p_")
    out.insert(0, "inflation", inflation)
    out.insert(0, "growth", growth)
    out["leading"] = leading
    out["candidate"] = candidate
    out["regime"] = regime
    out["growth_neutral"] = growth.abs() <= rules.neutral_band
    out["inflation_neutral"] = inflation.abs() <= rules.neutral_band
    return out
