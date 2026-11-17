"""Schuldenzyklus-Overlay auf die Basisallokation (Spezifikation 6.4).

Die Basisgewichte werden um den Overlay-Vektor des Landes verschoben, skaliert mit
λ = ``lambda_by_phase[Phase]`` × ``overlay_strength`` (begrenzt auf 0 bis 1). Arten von
Verschiebungen in ``debt_cycle.yaml``:

- ``target_range``: Gewicht auf die Mitte der Spanne anheben, wenn es darunter liegt,
- ``shift_pp``: Verschiebung in Prozentpunkten (nie unter 0),
- ``lift_to_cap``: bis zur Obergrenze der Klasse anheben,
- ``shift_to_low_stress``: Anteil des Gewichts auf Aktienklassen von Ländern mit
  niedrigerem Schuldenstress umschichten (nach Basisgewicht),
- ``cap`` (``unhedged_usd_cap``): Obergrenze für ungesichertes USD-Exposure; sie sinkt mit λ
  von 100 % auf den Wert der Konfiguration. Durchgesetzt wird sie mit der Währungssicherung
  der Empfehlungs-Engine (M5); hier wird sie ausgewiesen.

Der Saldo aller Verschiebungen wird anteilig aus den Klassen ohne eigene Regel finanziert,
damit die Summe 1 bleibt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from navigator.config import AppConfig


@dataclass
class CountryLambda:
    """Phase und Skalierung des Overlays für ein Land."""

    country: str
    phase: str | None
    source: str
    value: float


@dataclass
class OverlayResult:
    """Gewichte mit und ohne Overlay samt Begründung."""

    base: pd.Series
    weights: pd.Series
    lambdas: list[CountryLambda]
    reasons: dict[str, str] = field(default_factory=dict)
    usd_cap: float | None = None
    notes: list[str] = field(default_factory=list)

    def table(self, config: AppConfig) -> pd.DataFrame:
        """Gegenüberstellung je Klasse in Prozent."""
        names = {k: a.name for k, a in config.universe.assets.items()}
        frame = pd.DataFrame(
            {
                "Klasse": [names.get(k, k) for k in self.base.index],
                "ohne Overlay": self.base.to_numpy() * 100,
                "mit Overlay": self.weights.reindex(self.base.index).to_numpy() * 100,
            },
            index=self.base.index,
        )
        frame["Δ Pp."] = frame["mit Overlay"] - frame["ohne Overlay"]
        frame["Grund"] = [self.reasons.get(k, "") for k in self.base.index]
        return frame


def choose_phase(
    config: AppConfig, country: str, measured: str | None
) -> tuple[str | None, str]:
    """Phase für das Overlay laut ``phase_source`` (manuell, gemessen oder manuell vor gemessen)."""
    manual = config.debt_cycle.assessments.get(country, {}).get("phase")
    source = config.debt_cycle.phase_source
    if source == "manual":
        return manual, "manuell"
    if source == "measured":
        return measured, "gemessen"
    if manual is not None:
        return manual, "manuell"
    return measured, "gemessen"


def country_lambdas(config: AppConfig, measured: dict[str, str | None]) -> list[CountryLambda]:
    """λ je Land mit Overlay-Vektor."""
    cycle = config.debt_cycle
    out = []
    for country in cycle.overlay_vectors:
        phase, source = choose_phase(config, country, measured.get(country))
        lam = 0.0 if phase is None else cycle.lambda_by_phase[phase] * cycle.overlay_strength
        out.append(CountryLambda(country, phase, source, float(np.clip(lam, 0.0, 1.0))))
    return out


def _cap(config: AppConfig, asset: str) -> float | None:
    spec = config.universe.assets[asset]
    caps = dict(config.base.constraints.get("max_weight", {}) or {})
    values = [v for v in (spec.max_weight, caps.get(asset)) if v is not None]
    return float(min(values)) if values else None


def apply_overlay(
    base: pd.Series,
    config: AppConfig,
    measured: dict[str, str | None],
    scores: dict[str, float],
) -> OverlayResult:
    """Verschiebt die Basisgewichte um die Overlay-Vektoren (λ je Land)."""
    base = base.astype("float64") / float(base.sum())
    weights = base.copy()
    reasons: dict[str, str] = {}
    explicit: set[str] = set()
    notes: list[str] = []
    usd_cap: float | None = None
    lambdas = country_lambdas(config, measured)
    for entry in lambdas:
        lam = entry.value
        vector = config.debt_cycle.overlay_vectors[entry.country]
        if lam <= 0:
            notes.append(f"{entry.country}: Phase {entry.phase or 'unbekannt'}, λ = 0, kein Overlay")
            continue
        for asset, rule in vector.items():
            kind = rule.get("type")
            if asset == "unhedged_usd_cap" or kind == "cap":
                cap = 1.0 - lam * (1.0 - float(rule["value"]))
                usd_cap = cap if usd_cap is None else min(usd_cap, cap)
                continue
            if asset not in weights.index:
                notes.append(f"{asset}: nicht in der Basis, Regel übersprungen")
                continue
            before = float(weights[asset])
            if kind == "target_range":
                target = (float(rule["min"]) + float(rule["max"])) / 2.0
                if before < target:
                    weights[asset] = before + lam * (target - before)
                reasons[asset] = f"auf {target:.1%} anheben (Spanne {rule['min']:.0%}–{rule['max']:.0%})"
            elif kind == "shift_pp":
                weights[asset] = max(0.0, before + lam * float(rule["value"]) / 100.0)
                reasons[asset] = f"{float(rule['value']):+.1f} Pp. × λ"
            elif kind == "lift_to_cap":
                cap = _cap(config, asset)
                if cap is None:
                    notes.append(f"{asset}: keine Obergrenze, 'lift_to_cap' übersprungen")
                    continue
                weights[asset] = before + lam * max(0.0, cap - before)
                reasons[asset] = f"bis zur Obergrenze {cap:.0%} anheben"
            elif kind == "shift_to_low_stress":
                moved = lam * float(rule["share"]) * before
                receivers = _low_stress_receivers(config, asset, scores, weights)
                if not receivers:
                    notes.append(f"{asset}: kein Land mit niedrigerem Schuldenstress, keine Umschichtung")
                    continue
                weights[asset] = before - moved
                split = base.reindex(receivers).fillna(0.0)
                split = split / split.sum() if split.sum() > 0 else pd.Series(1.0 / len(receivers), index=receivers)
                for receiver, share in split.items():
                    weights[receiver] += moved * float(share)
                    reasons[receiver] = f"erhält aus {asset} (niedrigerer Schuldenstress)"
                    explicit.add(str(receiver))
                reasons[asset] = f"{float(rule['share']):.0%} × λ zu {', '.join(receivers)}"
            else:
                notes.append(f"{asset}: unbekannte Regel {kind!r}")
                continue
            explicit.add(asset)
    excess = float(weights.sum()) - 1.0
    funders = [a for a in weights.index if a not in explicit and weights[a] > 0]
    pool = float(weights[funders].sum()) if funders else 0.0
    if abs(excess) > 1e-12:
        if pool > 0 and excess <= pool:
            for asset in funders:
                weights[asset] -= excess * float(weights[asset]) / pool
                reasons.setdefault(asset, "finanziert die Verschiebungen (anteilig)")
        else:
            notes.append("Verschiebungen nicht aus den übrigen Klassen finanzierbar; alle Gewichte skaliert")
            weights = weights.clip(lower=0.0)
    weights = weights.clip(lower=0.0)
    weights = weights / float(weights.sum())
    return OverlayResult(base, weights, lambdas, reasons, usd_cap, notes)


def _low_stress_receivers(
    config: AppConfig, asset: str, scores: dict[str, float], weights: pd.Series
) -> list[str]:
    """Aktienklassen, deren Länder im Mittel weniger Schuldenstress haben als die Quelle."""
    mapping = config.debt_cycle.equity_countries

    def stress(key: str) -> float:
        values = [scores[c] for c in mapping.get(key, []) if c in scores and pd.notna(scores[c])]
        return float(np.mean(values)) if values else float("nan")

    own = stress(asset)
    if np.isnan(own):
        return []
    return [
        key
        for key in mapping
        if key != asset and key in weights.index and not np.isnan(stress(key)) and stress(key) < own
    ]


def usd_share(weights: pd.Series, config: AppConfig) -> float:
    """Anteil ungesicherten USD-Exposures (nach ``fx_exposure`` und ``hedged``)."""
    total = 0.0
    for asset, weight in weights.items():
        spec = config.universe.assets.get(str(asset))
        if spec is None or spec.hedged:
            continue
        total += float(weight) * float(spec.fx_exposure.get("USD", 0.0))
    return total


def provisional_base(returns: pd.DataFrame, config: AppConfig, window: int = 60) -> pd.Series:
    """Vorläufige Basis bis M5: inverse Volatilität je Korb, Körbe nach inverser Korbvolatilität.

    Das ist eine einfache Näherung der Risikoparität aus 7.1 (ohne Korrelationen innerhalb
    der Körbe). Klassen in mehreren Körben erhalten die Summe ihrer Anteile. Obergrenzen
    (z. B. Bitcoin 3 %) werden eingehalten, der Rest anteilig verteilt.
    """
    recent = returns.dropna(how="all").iloc[-window:]
    vol = recent.std() * np.sqrt(12)
    weights = pd.Series(0.0, index=returns.columns)
    baskets = config.base.baskets
    basket_weights: dict[str, pd.Series] = {}
    basket_vol: dict[str, float] = {}
    for name, members in baskets.items():
        members = [m for m in members if m in vol.index and pd.notna(vol[m]) and vol[m] > 0]
        if not members:
            continue
        inv = 1.0 / vol[members]
        w = inv / inv.sum()
        basket_weights[name] = w
        series = (recent[members].fillna(0.0) * w).sum(axis=1)
        basket_vol[name] = float(series.std() * np.sqrt(12))
    inv_basket = {k: 1.0 / v for k, v in basket_vol.items() if v > 0}
    total = sum(inv_basket.values())
    for name, w in basket_weights.items():
        if name in inv_basket:
            weights = weights.add(w * inv_basket[name] / total, fill_value=0.0)
    weights = weights[weights > 0]
    for _ in range(10):
        capped = False
        for asset in weights.index:
            cap = _cap(config, str(asset))
            if cap is not None and weights[asset] > cap + 1e-12:
                excess = weights[asset] - cap
                weights[asset] = cap
                others = [a for a in weights.index if a != asset]
                weights[others] += excess * weights[others] / weights[others].sum()
                capped = True
        if not capped:
            break
    return weights / weights.sum()
