"""Empfehlungs-Engine (Spezifikation 7.2 bis 7.4).

Kette: Regime-Wahrscheinlichkeiten → erwartete Regime-Renditen je Klasse → Black-Litterman
auf der Risikoparitäts-Basis → drei Ausgabeformen (Ampel, Über-/Untergewichtung,
Zielgewichte) mit Zerlegung in Regime, Overlay und Restriktionen.

Alle Renditen sind Überrenditen gegenüber Cash in Basiswährung, annualisiert.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd

from navigator.allocation.base import BaseAllocation
from navigator.config import QUADRANTS, AppConfig


# --------------------------------------------------------------------- Regime-Renditen
def assumption_returns(config: AppConfig, assets: list[str]) -> pd.DataFrame:
    """Ökonomische Annahme (4.4): Erwartungsvektor × ``assumption_scale`` (Klassen × Quadranten)."""
    scale = float(config.base.black_litterman.get("assumption_scale", 0.025))
    exp = config.regime_map.expectations
    rows = {a: {q: float(exp.get(a, {}).get(q, 0)) * scale for q in QUADRANTS} for a in assets}
    return pd.DataFrame.from_dict(rows, orient="index")[list(QUADRANTS)]


def historical_regime_returns(
    excess: pd.DataFrame, regimes: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mittlere Überrendite je Klasse im Monat nach einem Regime (annualisiert) und Anzahl.

    Das Regime zum Monatsende m wird mit der Rendite des Folgemonats verknüpft; so geht
    nur ein Regime ein, das beim Kauf bekannt war.
    """
    following = excess.shift(-1)
    aligned = regimes.reindex(excess.index)
    means, counts = {}, {}
    for q in QUADRANTS:
        mask = aligned == q
        sub = following[mask.to_numpy()]
        means[q] = sub.mean() * 12.0
        counts[q] = sub.notna().sum()
    return pd.DataFrame(means)[list(QUADRANTS)], pd.DataFrame(counts)[list(QUADRANTS)]


def james_stein(
    historical: pd.DataFrame, counts: pd.DataFrame, target: pd.DataFrame, monthly_var: pd.Series
) -> tuple[pd.DataFrame, pd.Series]:
    """James-Stein: historische Regime-Mittel je Quadrant zur ökonomischen Annahme schrumpfen.

    Schrumpfungsfaktor c = min(1, (k − 2) · mittlere Schätzvarianz / ‖Mittel − Ziel‖²) je
    Quadrant über die k Klassen (Begleitbuch Kapitel 4). Ohne Historie gilt die Annahme.
    """
    out = target.copy()
    factors = {}
    for q in QUADRANTS:
        n = counts[q].reindex(target.index).fillna(0.0)
        hist = historical[q].reindex(target.index)
        valid = (n >= 12) & hist.notna()
        k = int(valid.sum())
        if k < 3:
            factors[q] = 1.0
            continue
        est_var = (monthly_var.reindex(target.index)[valid] * 144.0 / n[valid]).mean()
        diff = hist[valid] - target.loc[valid, q]
        norm = float((diff**2).sum())
        c = 1.0 if norm == 0 else min(1.0, (k - 2) * float(est_var) / norm)
        factors[q] = c
        out.loc[valid, q] = target.loc[valid, q] + (1 - c) * diff
    return out, pd.Series(factors)


# --------------------------------------------------------------------- Black-Litterman
@dataclass
class BlackLitterman:
    """Prior, Sichten und Posterior."""

    prior: pd.Series
    posterior: pd.Series
    posterior_cov: pd.DataFrame
    views: dict[str, pd.Series]
    delta: float


def implied_returns(base: BaseAllocation, config: AppConfig) -> tuple[pd.Series, float]:
    """Reverse Optimization: π = δ Σ w; δ so, dass die Basis Sharpe ``prior_sharpe`` hat."""
    sharpe = float(config.base.black_litterman.get("prior_sharpe", 0.3))
    vol = base.volatility()
    delta = sharpe / vol if vol > 0 else 1.0
    w = base.weights.reindex(base.cov.index).fillna(0.0)
    return pd.Series(delta * (base.cov.to_numpy() @ w.to_numpy()), index=base.cov.index), delta


def black_litterman(
    base: BaseAllocation,
    config: AppConfig,
    regime_view: pd.Series | None,
    conviction: float,
    overlay_weights: pd.Series | None,
) -> BlackLitterman:
    """Posterior aus Prior und Sichten (je Klasse eine absolute Sicht, P = Einheitsmatrix).

    Ω der Regime-Sicht = τ · diag(Σ) / Überzeugung (5.4): stimmen A und B überein, wirkt die
    Sicht stärker. Die Overlay-Sicht sind die impliziten Renditen der Overlay-Gewichte für die
    vom Overlay veränderten Klassen, mit Ω = τ · diag(Σ).
    """
    tau = float(config.base.black_litterman.get("tau", 0.05))
    prior, delta = implied_returns(base, config)
    sigma = base.cov.to_numpy()
    assets = list(base.cov.index)
    rows_p, rows_q, rows_o = [], [], []
    views: dict[str, pd.Series] = {}
    floor = float(config.base.black_litterman.get("min_conviction", 0.05))
    if regime_view is not None:
        q = regime_view.reindex(assets)
        mask = q.notna().to_numpy()
        eye = np.eye(len(assets))[mask]
        rows_p.append(eye)
        rows_q.append(q.to_numpy()[mask])
        rows_o.append(tau * np.diag(sigma)[mask] / max(conviction, floor))
        views["regime"] = q
    if overlay_weights is not None:
        w_ov = overlay_weights.reindex(assets).fillna(0.0)
        w_base = base.weights.reindex(assets).fillna(0.0)
        changed = (w_ov - w_base).abs().to_numpy() > 1e-6
        if changed.any():
            implied = delta * (sigma @ w_ov.to_numpy())
            rows_p.append(np.eye(len(assets))[changed])
            rows_q.append(implied[changed])
            rows_o.append(tau * np.diag(sigma)[changed])
            views["overlay"] = pd.Series(np.where(changed, implied, np.nan), index=assets)
    if not rows_p:
        return BlackLitterman(prior, prior.copy(), base.cov + tau * base.cov, views, delta)
    p = np.vstack(rows_p)
    qv = np.concatenate(rows_q)
    omega_inv = np.diag(1.0 / np.concatenate(rows_o))
    ts_inv = np.linalg.inv(tau * sigma)
    m = np.linalg.inv(ts_inv + p.T @ omega_inv @ p)
    mu = m @ (ts_inv @ prior.to_numpy() + p.T @ omega_inv @ qv)
    post_cov = sigma + m
    return BlackLitterman(
        prior,
        pd.Series(mu, index=assets),
        pd.DataFrame(post_cov, index=assets, columns=assets),
        views,
        delta,
    )


# --------------------------------------------------------------------- Ausgabeformen
def ampel(signal: pd.Series, threshold_sd: float) -> pd.Series:
    """Grün / gelb / rot nach ±``threshold_sd`` Standardabweichungen des Signals."""
    z = (signal - signal.mean()) / (signal.std(ddof=0) or 1.0)
    return pd.Series(
        np.where(z > threshold_sd, "grün", np.where(z < -threshold_sd, "rot", "gelb")),
        index=signal.index,
    )


def tilts(signal: pd.Series, conviction: float, base: pd.Series, config: AppConfig) -> pd.Series:
    """Aktive Abweichung in Prozentpunkten: Skalierung × Überzeugung × z-Wert des Signals.

    Ein z-Wert von 1 bei voller Überzeugung entspricht der halben Grenze. Begrenzung je Klasse
    (±10 Pp., kleine Klassen ±5 Pp.), nie unter null Gewicht, Summe null (E-73).
    """
    out = config.base.outputs["tilts"]
    scale = float(out.get("scale", 1.0))
    limit = float(out.get("limit_pp", 10.0))
    small = float(out.get("limit_small_pp", 5.0))
    small_set = set(out.get("small_classes", []))
    z = (signal - signal.mean()) / (signal.std(ddof=0) or 1.0)
    caps = pd.Series([small if a in small_set else limit for a in z.index], index=z.index)
    lower = -np.minimum(caps, base.reindex(z.index).fillna(0.0) * 100.0)
    raw = scale * conviction * z * caps / 2.0
    tilt = raw.clip(lower, caps)
    for _ in range(50):
        excess = float(tilt.sum())
        if abs(excess) < 1e-10:
            break
        free = (tilt > lower + 1e-12) if excess > 0 else (tilt < caps - 1e-12)
        if not free.any():
            break
        tilt[free] -= excess / int(free.sum())
        tilt = tilt.clip(lower, caps)
    return tilt


def _active_unconstrained(mu: pd.Series, cov: pd.DataFrame, te: float) -> pd.Series:
    """Aktive Gewichte ohne Restriktionen (Summe 0) mit Tracking Error ``te``.

    max μ'a − ½λ a'Σa unter 1'a = 0; λ so gewählt, dass √(a'Σa) = te.
    """
    sigma_inv = np.linalg.pinv(cov.to_numpy())
    ones = np.ones(len(mu))
    m = mu.to_numpy()
    raw = sigma_inv @ m - sigma_inv @ ones * (ones @ sigma_inv @ m) / (ones @ sigma_inv @ ones)
    risk = float(np.sqrt(max(raw @ cov.to_numpy() @ raw, 0.0)))
    a = raw * (te / risk) if risk > 1e-12 else np.zeros_like(raw)
    return pd.Series(a, index=mu.index)


@dataclass
class TargetResult:
    """Zielgewichte samt Bandbreite und Restriktionsprüfung."""

    weights: pd.Series
    low: pd.Series
    high: pd.Series
    tracking_error: float
    turnover: float
    checks: dict[str, bool]
    notes: list[str] = field(default_factory=list)


def _usd_vector(assets: list[str], config: AppConfig) -> np.ndarray:
    out = []
    for a in assets:
        spec = config.universe.assets[a]
        out.append(0.0 if spec.hedged else float(spec.fx_exposure.get("USD", 0.0)))
    return np.array(out)


def _caps(assets: list[str], config: AppConfig) -> np.ndarray:
    caps = dict(config.base.constraints.get("max_weight", {}) or {})
    out = []
    for a in assets:
        values = [v for v in (config.universe.assets[a].max_weight, caps.get(a)) if v is not None]
        out.append(min(values) if values else 1.0)
    return np.array(out, dtype=float)


def _solve(
    mu: np.ndarray,
    sigma: np.ndarray,
    base: np.ndarray,
    current: np.ndarray,
    caps: np.ndarray,
    te: float,
    turnover: float,
    usd: np.ndarray | None,
    usd_cap: float | None,
) -> np.ndarray | None:
    n = len(mu)
    w = cp.Variable(n)
    chol = np.linalg.cholesky(sigma + 1e-10 * np.eye(n))
    constraints = [
        cp.sum(w) == 1,
        w >= 0,
        w <= caps,
        cp.norm(chol.T @ (w - base), 2) <= te,
        0.5 * cp.norm(w - current, 1) <= turnover,
    ]
    if usd is not None and usd_cap is not None:
        constraints.append(usd @ w <= usd_cap)
    problem = cp.Problem(cp.Maximize(mu @ w), constraints)
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.SolverError:
        return None
    if problem.status not in ("optimal", "optimal_inaccurate") or w.value is None:
        return None
    return np.clip(np.asarray(w.value, dtype=float), 0.0, None)


def target_weights(
    bl: BlackLitterman,
    base: BaseAllocation,
    config: AppConfig,
    current: pd.Series | None = None,
    usd_cap: float | None = None,
    simulations: int | None = None,
    seed: int = 20261118,
) -> TargetResult:
    """Zielgewichte (7.3 iii) mit Michaud-Resampling.

    Je Simulation werden 60 Monatsrenditen aus N(μ, Σ) gezogen, μ daraus neu geschätzt und
    das Problem gelöst: maximiere μ'w, Summe 1, nur long, Obergrenzen, Tracking Error zur
    Basis ≤ 3 % p. a. (mit der Posterior-Kovarianz), Umschlag ≤ 20 % (halbe Summe der
    absoluten Änderungen gegenüber dem aktuellen Portfolio bzw. der Basis), optional
    ungesichertes USD-Exposure ≤ Obergrenze. Alle Restriktionen sind konvex; das Mittel der
    Lösungen hält sie daher ebenfalls ein. Danach No-Trade-Band (±2 Pp.).
    """
    out = config.base.outputs["target_weights"]
    sims = int(simulations or out.get("resampling_simulations", 500))
    te = float(out.get("tracking_error_max", 0.03))
    turnover = float(out.get("turnover_max_quarter", 0.20))
    band = float(out.get("no_trade_band_pp", 2.0)) / 100.0
    assets = list(base.cov.index)
    sigma = bl.posterior_cov.loc[assets, assets].to_numpy()
    b = base.weights.reindex(assets).fillna(0.0).to_numpy()
    cur = b if current is None else current.reindex(assets).fillna(0.0).to_numpy()
    caps = _caps(assets, config)
    usd = _usd_vector(assets, config) if usd_cap is not None else None
    notes: list[str] = []
    if usd is not None and usd_cap is not None and float(usd @ b) > usd_cap:
        notes.append(f"Basis über der USD-Obergrenze ({float(usd @ b):.1%}); Grenze nicht bindend")
        usd = None
    rng = np.random.default_rng(seed)
    mu = bl.posterior.reindex(assets).to_numpy()
    monthly_cov = sigma / 12.0
    solutions = []
    for _ in range(sims):
        draws = rng.multivariate_normal(mu / 12.0, monthly_cov, size=60)
        sol = _solve(draws.mean(axis=0) * 12.0, sigma, b, cur, caps, te, turnover, usd, usd_cap)
        if sol is not None:
            solutions.append(sol)
    if not solutions:
        notes.append("keine zulässige Lösung; Zielgewichte = aktuelles Portfolio")
        stack = np.array([cur])
    else:
        stack = np.array(solutions)
        if len(solutions) < sims:
            notes.append(f"{sims - len(solutions)} von {sims} Simulationen ohne Lösung")
    mean = stack.mean(axis=0)
    weights = pd.Series(mean / mean.sum(), index=assets)
    # No-Trade-Band: kleine Änderungen unterbleiben, der Rest wird anteilig angepasst.
    diff = weights - pd.Series(cur, index=assets)
    small = diff.abs() < band
    if small.any() and (~small).any():
        weights[small] = cur[small.to_numpy()]
        gap = 1.0 - float(weights.sum())
        movers = weights[~small]
        weights[~small] = movers + gap * movers / movers.sum()
    active = weights.to_numpy() - b
    te_value = float(np.sqrt(active @ sigma @ active))
    turn = 0.5 * float(np.abs(weights.to_numpy() - cur).sum())
    checks = {
        "Summe 1": abs(float(weights.sum()) - 1.0) < 1e-6,
        "nur long": bool((weights >= -1e-9).all()),
        "Obergrenzen": bool((weights.to_numpy() <= caps + 1e-6).all()),
        "Tracking Error ≤ Grenze": te_value <= te + 1e-4,
        "Umschlag ≤ Grenze": turn <= turnover + 1e-4,
    }
    if usd is not None and usd_cap is not None:
        checks["USD-Obergrenze"] = float(usd @ weights.to_numpy()) <= usd_cap + 1e-4
    low = pd.Series(np.percentile(stack, 5, axis=0), index=assets)
    high = pd.Series(np.percentile(stack, 95, axis=0), index=assets)
    return TargetResult(weights, low, high, te_value, turn, checks, notes)


def decomposition(
    base: BaseAllocation,
    bl_regime: BlackLitterman,
    bl_full: BlackLitterman,
    target: pd.Series,
    config: AppConfig,
) -> pd.DataFrame:
    """Zerlegung der Abweichung Ziel − Basis in Regime, Overlay und Restriktionen (7.4).

    Regime = unbeschränkte aktive Gewichte aus den Regime-Sichten; Overlay = Zuwachs durch
    die Overlay-Sicht; Restriktionen = Rest bis zu den Zielgewichten. Die Summe ergibt per
    Konstruktion exakt Ziel − Basis.
    """
    te = float(config.base.outputs["target_weights"].get("tracking_error_max", 0.03))
    assets = list(base.cov.index)
    regime = _active_unconstrained(
        (bl_regime.posterior - bl_regime.prior).reindex(assets), base.cov, te
    )
    full = _active_unconstrained((bl_full.posterior - bl_full.prior).reindex(assets), base.cov, te)
    total = target.reindex(assets).fillna(0.0) - base.weights.reindex(assets).fillna(0.0)
    frame = pd.DataFrame(
        {
            "Basis": base.weights.reindex(assets).fillna(0.0),
            "Regime": regime,
            "Overlay": full - regime,
            "Restriktionen": total - full,
            "Ziel": target.reindex(assets).fillna(0.0),
        }
    )
    return frame
