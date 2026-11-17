"""Vergleich der Methoden A und B, Begründung der Abweichungen, Überzeugung (Abschnitt 5.2–5.4).

- **Getrennte Darstellung:** Übereinstimmungsquote über die Historie und Kreuztabelle (wie oft
  A Regime X sieht, während B Regime Y sieht).
- **Begründung je Monat:** Für A die Beiträge der Indikatoren zum Score; für B die Zerlegung
  der Log-Likelihood-Differenz zwischen den beiden wahrscheinlichsten Zuständen je Merkmal
  (bei diagonaler Kovarianz exakt summierbar). Daraus entsteht ein Satz nach fester Vorlage.
- **Überzeugung:** 1 minus Totalvariationsdistanz der beiden Wahrscheinlichkeitsvektoren.
  Je ähnlicher A und B, desto größer die später zulässigen aktiven Abweichungen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from navigator.config import QUADRANTS
from navigator.features.scores import Scores
from navigator.regimes.hmm import MethodBResult
from navigator.regimes.rules import LABELS

STATE_LABELS = {**LABELS, "financial_stress": "Finanzstress"}

FEATURE_LABELS = {
    "stock_bond_corr_12m": ("Aktien-Anleihen-Korrelation", "steigender", "sinkender"),
    "equity_vol_3m": ("Aktienvolatilität", "hoher", "niedriger"),
    "real_yield_change_6m": ("Realrenditen", "steigender", "fallender"),
    "credit_spread_level": ("Kreditspread-Niveau", "hohen", "niedrigen"),
}


def conviction(probs_a: pd.DataFrame, probs_b: pd.DataFrame) -> pd.Series:
    """1 − Totalvariationsdistanz der Quadranten-Wahrscheinlichkeiten je Monat."""
    a = probs_a[list(QUADRANTS)]
    b = probs_b[list(QUADRANTS)]
    tv = 0.5 * (a - b).abs().sum(axis=1, min_count=4)
    return (1.0 - tv).where(a.notna().all(axis=1) & b.notna().all(axis=1))


def agreement(regime_a: pd.Series, regime_b: pd.Series) -> tuple[float, pd.DataFrame]:
    """Übereinstimmungsquote und Kreuztabelle (Zeilen A, Spalten B) über gemeinsame Monate."""
    joined = pd.concat([regime_a.rename("A"), regime_b.rename("B")], axis=1).dropna()
    if joined.empty:
        return float("nan"), pd.DataFrame()
    rate = float((joined["A"] == joined["B"]).mean())
    table = pd.crosstab(
        joined["A"].map(LABELS).rename("Methode A"), joined["B"].map(LABELS).rename("Methode B")
    )
    return rate, table


def _num(value: float, digits: int) -> str:
    """Zahl mit Vorzeichen und deutschem Dezimalkomma."""
    return f"{value:+.{digits}f}".replace(".", ",")


def feature_name(key: str, names: dict[str, str]) -> str:
    """Kurzer lesbarer Name eines Merkmals (ohne Klammerzusatz)."""
    if key in FEATURE_LABELS:
        return FEATURE_LABELS[key][0]
    return names.get(key, key).split(" (")[0]


def describe(key: str, value: float, names: dict[str, str]) -> str:
    """Merkmal der Methode B mit Richtung, z. B. „steigender Realrenditen" oder „… (z −1,2)"."""
    if key in FEATURE_LABELS:
        label, up, down = FEATURE_LABELS[key]
        return (
            f"{up if value > 0 else down} {label}s"
            if label.endswith("Niveau")
            else f"{up if value > 0 else down} {label}"
        )
    return f"{feature_name(key, names)} (z {_num(value, 1)})"


def describe_a(key: str, axis: str, contribution: float, names: dict[str, str]) -> str:
    """Indikator der Methode A mit Achse und Beitrag zum Score."""
    achse = "Wachstum" if axis == "growth" else "Inflation"
    return f"{feature_name(key, names)} ({achse} {_num(contribution, 2)})"


def b_drivers(result: MethodBResult, when: pd.Timestamp, top: int = 2) -> pd.DataFrame:
    """Merkmale, die den wahrscheinlichsten Zustand gegenüber dem zweiten stützen."""
    fit_date = result.model_of.get(when)
    if fit_date is None or pd.isna(fit_date) or when not in result.features.index:
        return pd.DataFrame()
    params = result.models[fit_date]
    probs = result.state_probs.loc[when].to_numpy(dtype=float)
    order = np.argsort(probs)[::-1]
    first, second = int(order[0]), int(order[1])
    x = result.features.loc[when].to_numpy(dtype=float)
    diff = params.feature_loglik(x, first) - params.feature_loglik(x, second)
    table = pd.DataFrame(
        {
            "Merkmal": result.features.columns,
            "Wert": x,
            "Beitrag": diff,
        }
    ).sort_values("Beitrag", ascending=False)
    table.attrs["first"] = result.names[fit_date][first]
    table.attrs["second"] = result.names[fit_date][second]
    return table.head(top) if top else table


def a_drivers(scores: Scores, when: pd.Timestamp, region: str, top: int = 2) -> pd.DataFrame:
    """Indikatoren mit dem größten Beitrag zu den Scores von Methode A."""
    rows = []
    for axis in ("growth", "inflation"):
        for key, value in scores.contributions(when, region, axis).items():
            rows.append({"Merkmal": key, "Achse": axis, "Beitrag": float(value)})
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table["Betrag"] = table["Beitrag"].abs()
    return table.sort_values("Betrag", ascending=False).head(top)


def explanation(
    when: pd.Timestamp,
    regime_a: str | None,
    scores: Scores,
    result: MethodBResult,
    names: dict[str, str],
    region: str = "US",
) -> str:
    """Begründung als Satz nach fester Vorlage."""
    label_b = result.label.get(when)
    if regime_a is None or label_b is None or pd.isna(label_b):
        return ""
    drivers_b = b_drivers(result, when)
    drivers_a = a_drivers(scores, when, region)
    b_text = " und ".join(
        describe(row.Merkmal, row.Wert, names) for row in drivers_b.itertuples(index=False)
    )
    a_text = " und ".join(
        describe_a(row.Merkmal, row.Achse, row.Beitrag, names)
        for row in drivers_a.itertuples(index=False)
    )
    b_name, a_name = STATE_LABELS[label_b], LABELS[regime_a]
    if result.regime.get(when) == regime_a:
        return f"A und B sehen {a_name}. B stützt sich vor allem auf {b_text}; A auf {a_text}."
    return f"B sieht {b_name} vor allem wegen {b_text}; A sieht {a_name}, getragen von {a_text}."
