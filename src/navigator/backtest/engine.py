"""Backtest (Spezifikation 8): monatlicher Walk-Forward, quartalsweise Umschichtung.

Entscheidung am Quartalsende t nur mit Daten bis t; die neuen Gewichte gelten ab dem
Folgemonat (Umsetzung zum Schluss des ersten Handelstags von t+1, mit Monatsdaten als
Rendite des Folgemonats genähert). Zwischen den Umschichtungen treiben die Gewichte mit den
Renditen. Kosten: Summe |Δw| × Kostensatz je Klasse. Alle Renditen in Basiswährung.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd

from navigator.allocation.base import BaseAllocation, base_allocation, covariance
from navigator.allocation.engine import (
    assumption_returns,
    black_litterman,
    historical_regime_returns,
    james_stein,
    target_weights,
    tilts,
)
from navigator.allocation.overlay import apply_overlay, enforce_caps
from navigator.allocation.recommend import excess_returns, regime_view
from navigator.config import QUADRANTS, AppConfig

WeightFn = Callable[[pd.Timestamp, pd.Series], pd.Series]


@dataclass
class Inputs:
    """Alle Eingaben des Backtests (Point-in-Time je Stichtag)."""

    returns: pd.DataFrame  # Monatsrenditen in Basiswährung, inkl. cash
    probs: dict[str, pd.DataFrame]  # "a", "b": Spalten p_<Quadrant>
    conviction: pd.Series
    regimes: pd.Series  # Methode A, für historische Regime-Renditen
    debt_phase: pd.Series = field(default_factory=pd.Series)  # US, gemessen, je Monatsende
    debt_scores: pd.DataFrame = field(default_factory=pd.DataFrame)  # Länder je Monatsende


@dataclass
class StrategyResult:
    """Wertentwicklung einer Strategie."""

    name: str
    returns: pd.Series  # nach Kosten
    gross: pd.Series
    weights: pd.DataFrame  # Gewichte zu Monatsbeginn
    turnover: pd.Series
    costs: pd.Series
    implementable: bool = True
    note: str = ""


def rebalance_dates(index: pd.DatetimeIndex, start: str, frequency: str) -> list[pd.Timestamp]:
    """Entscheidungstermine: Quartalsenden (oder jedes Monatsende) ab ``start``."""
    dates = [d for d in index if d >= pd.Timestamp(start) + pd.offsets.MonthEnd(0)]
    if frequency == "quarterly":
        dates = [d for d in dates if d.month in (3, 6, 9, 12)]
    return dates


def simulate(
    name: str,
    returns: pd.DataFrame,
    decide: WeightFn,
    dates: list[pd.Timestamp],
    costs_bps: dict[str, float],
    band: float,
    implementable: bool = True,
    note: str = "",
) -> StrategyResult:
    """Läuft die Strategie über die Historie; ``decide(t, aktuelle Gewichte)`` sieht nur ≤ t."""
    index = returns.index
    start = dates[0]
    months = [d for d in index if d > start]
    current = pd.Series(dtype="float64")
    decision_set = set(dates)
    gross, net, turn, cost, rows = {}, {}, {}, {}, {}
    pending: pd.Series | None = None
    t = start
    target = decide(t, current)
    pending = target
    for month in months:
        if pending is not None:
            new = pending.reindex(pending.index.union(current.index)).fillna(0.0)
            old = current.reindex(new.index).fillna(0.0)
            delta = new - old
            if band > 0 and not current.empty:
                keep = delta.abs() < band
                if keep.any() and (~keep).any():
                    new[keep] = old[keep]
                    movers = new[~keep]
                    new[~keep] = movers + (1.0 - new.sum()) * movers / movers.sum()
                    delta = new - old
            c = float(sum(abs(v) * costs_bps.get(str(k), 0.0) / 1e4 for k, v in delta.items()))
            turn[month] = 0.5 * float(delta.abs().sum())
            cost[month] = c
            current = new[new > 1e-12]
            pending = None
        else:
            turn[month], cost[month] = 0.0, 0.0
        r = returns.loc[month].reindex(current.index)
        r = r.fillna(returns.loc[month].get("cash", 0.0))
        port = float((current * r).sum())
        rows[month] = current
        gross[month] = port
        net[month] = port - cost[month]
        grown = current * (1 + r)
        current = grown / grown.sum()
        if month in decision_set:
            pending = decide(month, current)
    return StrategyResult(
        name,
        pd.Series(net),
        pd.Series(gross),
        pd.DataFrame(rows).T.fillna(0.0),
        pd.Series(turn),
        pd.Series(cost),
        implementable,
        note,
    )


# --------------------------------------------------------------------- Entscheidungsregeln
class Decider:
    """Gemeinsame Bausteine der Strategien je Stichtag (Cache für die Basis)."""

    def __init__(self, config: AppConfig, inputs: Inputs, simulations: int) -> None:
        self.config = config
        self.inputs = inputs
        self.simulations = simulations
        self._base: dict[pd.Timestamp, BaseAllocation] = {}
        self._tables: dict[pd.Timestamp, pd.DataFrame] = {}

    def known_returns(self, t: pd.Timestamp) -> pd.DataFrame:
        return self.inputs.returns[self.inputs.returns.index <= t]

    def base(self, t: pd.Timestamp) -> BaseAllocation:
        if t not in self._base:
            self._base[t] = base_allocation(self.known_returns(t), self.config)
        return self._base[t]

    def probs(self, method: str, t: pd.Timestamp) -> pd.Series | None:
        frames = []
        for m in ("a", "b") if method == "ab" else (method,):
            frame = self.inputs.probs.get(m)
            if frame is None:
                continue
            known = frame[frame.index <= t].dropna(how="all")
            if known.empty:
                continue
            row = known.iloc[-1]
            frames.append(pd.Series({q: float(row.get(f"p_{q}", np.nan)) for q in QUADRANTS}))
        if not frames:
            return None
        return sum(frames[1:], frames[0]) / len(frames)

    def conviction(self, t: pd.Timestamp) -> float:
        known = self.inputs.conviction[self.inputs.conviction.index <= t].dropna()
        return float(known.iloc[-1]) if not known.empty else 0.0

    def regime_table(self, t: pd.Timestamp, base: BaseAllocation) -> pd.DataFrame:
        if t in self._tables:
            return self._tables[t]
        self._tables[t] = self._regime_table(t, base)
        return self._tables[t]

    def _regime_table(self, t: pd.Timestamp, base: BaseAllocation) -> pd.DataFrame:
        assets = list(base.cov.index)
        excess = excess_returns(self.known_returns(t)).reindex(columns=assets)
        regimes = self.inputs.regimes[self.inputs.regimes.index <= t]
        hist, counts = historical_regime_returns(excess, regimes)
        target = assumption_returns(self.config, assets)
        table, _ = james_stein(hist, counts, target, excess.var())
        weight = float(self.config.base.black_litterman.get("bitcoin_prior_weight", 0.8))
        if "bitcoin" in table.index:
            table.loc["bitcoin"] = target.loc["bitcoin"] + (1 - weight) * (
                table.loc["bitcoin"] - target.loc["bitcoin"]
            )
        return table

    def overlay_weights(
        self, t: pd.Timestamp, base: BaseAllocation
    ) -> tuple[pd.Series, float | None]:
        phase = self.inputs.debt_phase[self.inputs.debt_phase.index <= t].dropna()
        measured = {"US": str(phase.iloc[-1]) if not phase.empty else None}
        scores_frame = self.inputs.debt_scores[self.inputs.debt_scores.index <= t]
        scores = scores_frame.iloc[-1].to_dict() if not scores_frame.empty else {}
        custom = self.config.model_copy(deep=True)
        custom.debt_cycle.phase_source = "measured"  # E-80: manuelle Einschätzung erst ab 2026
        result = apply_overlay(base.weights, custom, measured, scores)
        return result.weights, result.usd_cap

    # -- Strategien -------------------------------------------------------------------------
    def static_base(self, t: pd.Timestamp, current: pd.Series) -> pd.Series:
        return self.base(t).weights

    def regime(
        self, method: str, with_overlay: bool, probs_override: pd.Series | None = None
    ) -> WeightFn:
        def decide(t: pd.Timestamp, current: pd.Series) -> pd.Series:
            base = self.base(t)
            probs = probs_override if probs_override is not None else self.probs(method, t)
            if probs is None:
                return base.weights
            view = regime_view(probs, self.regime_table(t, base))
            overlay_w, usd_cap = (None, None)
            if with_overlay:
                overlay_w, usd_cap = self.overlay_weights(t, base)
            bl = black_litterman(base, self.config, view, self.conviction(t), overlay_w)
            cur = current.reindex(base.cov.index).fillna(0.0) if not current.empty else None
            if cur is not None and cur.sum() > 0:
                cur = cur / cur.sum()
            target = target_weights(bl, base, self.config, cur, usd_cap, self.simulations)
            return target.weights

        return decide

    def tilt_strategy(self, probs_at: Callable[[pd.Timestamp], pd.Series | None]) -> WeightFn:
        """Form (ii): Basis + Tilts. Schnell genug für Placebo und Sensitivität."""

        def decide(t: pd.Timestamp, current: pd.Series) -> pd.Series:
            base = self.base(t)
            probs = probs_at(t)
            if probs is None:
                return base.weights
            view = regime_view(probs, self.regime_table(t, base))
            conv = self.conviction(t)
            bl = black_litterman(base, self.config, view, conv, None)
            tilt = tilts(bl.posterior - bl.prior, conv, base.weights, self.config)
            weights = (base.weights + tilt.reindex(base.weights.index).fillna(0.0) / 100).clip(0)
            return weights / weights.sum()

        return decide

    def sixty_forty(self, t: pd.Timestamp, current: pd.Series) -> pd.Series:
        spec = self.config.backtest.benchmarks.get("sixty_forty", {})
        eq, bonds = spec.get("weights", [0.6, 0.4])
        world = {"equity_us": 0.62, "equity_europe": 0.22, "equity_japan": 0.06, "equity_em": 0.10}
        known = self.known_returns(t).iloc[-1]
        world = {k: v for k, v in world.items() if pd.notna(known.get(k))}
        total = sum(world.values())
        weights = {k: eq * v / total for k, v in world.items()}
        weights[str(spec.get("bonds", "bond_eur_long"))] = bonds
        return pd.Series(weights)

    def equal_weight(self, t: pd.Timestamp, current: pd.Series) -> pd.Series:
        known = self.known_returns(t).iloc[-36:]
        assets = [a for a in known.columns if a != "cash" and known[a].notna().all()]
        return enforce_caps(pd.Series(1.0 / len(assets), index=assets), self.config)

    def minimum_variance(self, t: pd.Timestamp, current: pd.Series) -> pd.Series:
        cov, _ = covariance(
            self.known_returns(t).drop(columns=["cash"], errors="ignore"), self.config
        )
        n = len(cov)
        w = cp.Variable(n)
        caps = np.array(
            [self.config.base.constraints.get("max_weight", {}).get(a, 1.0) for a in cov.index]
        )
        problem = cp.Problem(
            cp.Minimize(cp.quad_form(w, cp.psd_wrap(cov.to_numpy()))),
            [cp.sum(w) == 1, w >= 0, w <= caps],
        )
        problem.solve(solver=cp.CLARABEL)
        values = np.clip(np.asarray(w.value, dtype=float), 0, None)
        return pd.Series(values / values.sum(), index=cov.index)


def one_hot(regime: str) -> pd.Series:
    """Wahrscheinlichkeit 1 für einen Quadranten."""
    return pd.Series({q: 1.0 if q == regime else 0.0 for q in QUADRANTS})


def placebo_sequences(regimes: pd.Series, n: int, seed: int) -> list[pd.Series]:
    """Zufällige Regimefolgen mit gleicher Verteilung der Verweildauern (Blöcke gemischt).

    Die beobachteten Episoden (Regime und Länge) werden in zufälliger Reihenfolge neu
    aneinandergereiht; die Labels werden zufällig neu gezogen, ihre Häufigkeit bleibt
    ungefähr erhalten.
    """
    clean = regimes.dropna()
    spells: list[int] = []
    labels: list[str] = []
    last, length = None, 0
    for value in clean:
        if value == last:
            length += 1
        else:
            if last is not None:
                spells.append(length)
                labels.append(str(last))
            last, length = value, 1
    if last is not None:
        spells.append(length)
        labels.append(str(last))
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        order = rng.permutation(len(spells))
        seq: list[str] = []
        for i in order:
            seq += [labels[rng.integers(len(labels))]] * spells[i]
        out.append(pd.Series(seq[: len(clean)], index=clean.index))
    return out
