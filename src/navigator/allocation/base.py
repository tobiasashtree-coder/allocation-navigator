"""Basisallokation (Spezifikation 7.1): Risikoparität über vier Umfeldkörbe.

- Kovarianz: die letzten ``window_months`` Monatsrenditen in Basiswährung, exponentiell
  gewichtet (Halbwertszeit ``halflife_months``), Ledoit-Wolf-Schrumpfung zur skalierten
  Einheitsmatrix (Ledoit und Wolf 2004, wie im Begleitbuch Kapitel 4).
- Innerhalb jedes Korbs gleicher Risikobeitrag (ERC); die vier Korbportfolios tragen
  untereinander ebenfalls gleich viel Risiko (ERC auf der Kovarianz der Korbportfolios).
- Klassen in mehreren Körben erhalten die Summe ihrer Anteile; Obergrenzen (Bitcoin 3 %)
  werden eingehalten, der Überschuss geht anteilig an die übrigen Klassen.
- Cash nimmt nicht teil (E-70): bei fast null Volatilität bekäme es sonst fast das ganze
  Gewicht. Cash ist der Rest für Absicherung und Umschichtung, in der Basis 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from navigator.allocation.overlay import enforce_caps
from navigator.config import AppConfig

EXCLUDED = ("cash",)


def ledoit_wolf(x: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, float]:
    """Gewichtete Ledoit-Wolf-Schätzung (Ziel: mittlere Varianz mal Einheitsmatrix).

    ``x`` sind Renditen (T × N), ``weights`` Beobachtungsgewichte (Summe 1). Liefert die
    geschrumpfte Kovarianz und die Schrumpfungsintensität δ in [0, 1].
    """
    w = weights / weights.sum()
    mean = w @ x
    xc = x - mean
    sample = (xc * w[:, None]).T @ xc
    n = x.shape[1]
    mu = np.trace(sample) / n
    target = mu * np.eye(n)
    d2 = float(np.sum((sample - target) ** 2))
    # effektive Zahl der Beobachtungen bei ungleichen Gewichten
    t_eff = 1.0 / float(np.sum(w**2))
    b2_raw = 0.0
    for t in range(x.shape[0]):
        outer = np.outer(xc[t], xc[t])
        b2_raw += w[t] * float(np.sum((outer - sample) ** 2))
    b2 = min(d2, b2_raw / t_eff)
    delta = 0.0 if d2 == 0 else b2 / d2
    return delta * target + (1 - delta) * sample, delta


def covariance(returns: pd.DataFrame, config: AppConfig) -> tuple[pd.DataFrame, float]:
    """Annualisierte, geschrumpfte Kovarianz aus den letzten Monaten (nur vollständige Zeilen)."""
    cov = config.base.covariance
    window = int(cov.get("window_months", 60))
    halflife = float(cov.get("halflife_months", 30))
    recent = returns.iloc[-window:]
    # Nur Klassen mit lückenlosem Fenster (im Backtest fehlen frühe Klassen, z. B. Bitcoin).
    recent = recent.loc[:, recent.notna().all()].dropna()
    if len(recent) < 24 or recent.shape[1] < 2:
        raise ValueError(f"zu wenige vollständige Monate für die Kovarianz ({len(recent)})")
    age = np.arange(len(recent))[::-1]
    weights = 0.5 ** (age / halflife)
    matrix, delta = ledoit_wolf(recent.to_numpy(dtype=float), weights)
    frame = pd.DataFrame(matrix * 12.0, index=recent.columns, columns=recent.columns)
    return frame, delta


def erc_weights(cov: np.ndarray) -> np.ndarray:
    """Gewichte mit gleichem Risikobeitrag (long only, Summe 1)."""
    n = cov.shape[0]
    if n == 1:
        return np.ones(1)

    def objective(y: np.ndarray) -> float:
        # Spinu (2013): min ½ y'Σy − Σ log y / n, danach normieren
        return float(0.5 * y @ cov @ y - np.sum(np.log(y)) / n)

    def gradient(y: np.ndarray) -> np.ndarray:
        return np.asarray(cov @ y - 1.0 / (n * y))

    start = 1.0 / np.sqrt(np.diag(cov))
    start = start / np.sqrt(start @ cov @ start)
    result = minimize(
        objective,
        start,
        jac=gradient,
        bounds=[(1e-10, None)] * n,
        method="L-BFGS-B",
        options={"ftol": 1e-15, "gtol": 1e-12, "maxiter": 5000},
    )
    y = result.x
    return np.asarray(y / y.sum())


def risk_contributions(weights: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Anteil jeder Klasse am Portfoliorisiko (Summe 1)."""
    w = weights.reindex(cov.index).fillna(0.0).to_numpy()
    sigma = cov.to_numpy()
    total = float(w @ sigma @ w)
    return pd.Series(w * (sigma @ w) / total, index=cov.index)


@dataclass
class BaseAllocation:
    """Risikoparitäts-Basis zum Stichtag."""

    weights: pd.Series
    cov: pd.DataFrame
    shrinkage: float
    basket_weights: pd.Series
    basket_members: dict[str, pd.Series]

    def volatility(self) -> float:
        """Annualisierte Volatilität der Basis."""
        w = self.weights.reindex(self.cov.index).fillna(0.0).to_numpy()
        return float(np.sqrt(w @ self.cov.to_numpy() @ w))


def base_allocation(returns: pd.DataFrame, config: AppConfig) -> BaseAllocation:
    """Risikoparität über die Umfeldkörbe aus ``base.yaml``."""
    assets = [a for a in returns.columns if a not in EXCLUDED]
    cov, delta = covariance(returns[assets], config)
    members: dict[str, pd.Series] = {}
    for name, items in config.base.baskets.items():
        names = [a for a in items if a in cov.index]
        if not names:
            continue
        sub = cov.loc[names, names].to_numpy()
        members[name] = pd.Series(erc_weights(sub), index=names)
    basket_names = list(members)
    loadings = np.zeros((len(basket_names), len(cov)))
    for i, name in enumerate(basket_names):
        loadings[i] = members[name].reindex(cov.index).fillna(0.0).to_numpy()
    basket_cov = loadings @ cov.to_numpy() @ loadings.T
    basket_w = erc_weights(basket_cov)
    weights = pd.Series(basket_w @ loadings, index=cov.index)
    weights = enforce_caps(weights[weights > 0] / weights.sum(), config)
    return BaseAllocation(
        weights=weights.reindex(cov.index).fillna(0.0),
        cov=cov,
        shrinkage=delta,
        basket_weights=pd.Series(basket_w, index=basket_names),
        basket_members=members,
    )


def equal_weight_base(returns: pd.DataFrame, config: AppConfig) -> BaseAllocation:
    """Alternative Basis für Szenarien: Gleichgewichtung aller verfügbaren Klassen (ohne Cash),
    Obergrenzen eingehalten; Kovarianz wie bei der Risikoparität."""
    assets = [a for a in returns.columns if a not in EXCLUDED]
    cov, delta = covariance(returns[assets], config)
    weights = enforce_caps(pd.Series(1.0 / len(cov), index=cov.index), config)
    return BaseAllocation(weights, cov, delta, pd.Series(dtype="float64"), {})


BASE_METHODS = {"risk_parity": base_allocation, "equal_weight": equal_weight_base}
