"""Empfehlungs-Engine (M5): Basis, Black-Litterman, Ausgabeformen, Zerlegung, Look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from navigator.allocation.base import base_allocation, erc_weights, ledoit_wolf, risk_contributions
from navigator.allocation.engine import black_litterman, tilts
from navigator.allocation.overlay import apply_overlay
from navigator.allocation.recommend import run_recommendation
from navigator.config import QUADRANTS, AppConfig


def _returns(config: AppConfig, months: int = 120, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    assets = list(config.universe.enabled_assets())
    vols = rng.uniform(0.01, 0.06, size=len(assets))
    factor = rng.normal(0, 0.02, size=(months, 1))
    data = rng.normal(0.004, 1.0, size=(months, len(assets))) * vols + factor * 0.5
    frame = pd.DataFrame(
        data, index=pd.date_range("2015-01-31", periods=months, freq="ME"), columns=assets
    )
    frame["cash"] = 0.001
    return frame


def _probs(index: pd.DatetimeIndex, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    raw = rng.dirichlet(np.ones(4), size=len(index))
    return pd.DataFrame(raw, index=index, columns=[f"p_{q}" for q in QUADRANTS])


def test_erc_gives_equal_risk_contributions() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=(5, 5))
    cov = a @ a.T + np.eye(5) * 0.5
    w = erc_weights(cov)
    rc = w * (cov @ w)
    assert w.sum() == pytest.approx(1.0)
    assert np.allclose(rc / rc.sum(), 0.2, atol=1e-5)


def test_ledoit_wolf_shrinks_and_stays_positive_definite() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(40, 10))
    matrix, delta = ledoit_wolf(x, np.ones(40))
    assert 0.0 <= delta <= 1.0
    assert np.linalg.eigvalsh(matrix).min() > 0


def test_base_allocation_respects_caps_and_excludes_cash(config: AppConfig) -> None:
    base = base_allocation(_returns(config), config)
    assert base.weights.sum() == pytest.approx(1.0)
    assert "cash" not in base.weights.index
    assert base.weights["bitcoin"] <= 0.03 + 1e-9
    assert (base.weights >= 0).all()
    assert risk_contributions(base.weights, base.cov).sum() == pytest.approx(1.0)
    assert base.basket_weights.sum() == pytest.approx(1.0)


def test_black_litterman_without_views_returns_prior(config: AppConfig) -> None:
    base = base_allocation(_returns(config), config)
    bl = black_litterman(base, config, None, 0.5, None)
    pd.testing.assert_series_equal(bl.prior, bl.posterior)


def test_stronger_conviction_moves_posterior_further(config: AppConfig) -> None:
    base = base_allocation(_returns(config), config)
    view = pd.Series(0.05, index=base.cov.index)
    low = black_litterman(base, config, view, 0.1, None)
    high = black_litterman(base, config, view, 0.9, None)
    dist_low = float(((low.posterior - view) ** 2).sum())
    dist_high = float(((high.posterior - view) ** 2).sum())
    assert dist_high < dist_low


def test_tilts_sum_to_zero_and_respect_limits(config: AppConfig) -> None:
    base = base_allocation(_returns(config), config)
    rng = np.random.default_rng(4)
    signal = pd.Series(rng.normal(size=len(base.weights)), index=base.weights.index)
    tilt = tilts(signal, 1.0, base.weights, config)
    small = set(config.base.outputs["tilts"]["small_classes"])
    assert tilt.sum() == pytest.approx(0.0, abs=1e-8)
    for asset, value in tilt.items():
        cap = 5.0 if asset in small else 10.0
        assert -cap - 1e-9 <= value <= cap + 1e-9
        assert value >= -base.weights[asset] * 100 - 1e-9


@pytest.fixture(scope="module")
def recommendation(config: AppConfig):  # type: ignore[no-untyped-def]
    returns = _returns(config)
    probs = {"a": _probs(returns.index, 1), "b": _probs(returns.index, 2)}
    regimes = probs["a"].idxmax(axis=1).str.removeprefix("p_")
    conviction = pd.Series(0.6, index=returns.index)
    base = base_allocation(returns, config)
    overlay = apply_overlay(base.weights, config, {"US": "Spätphase (Finanzierungsstress)"}, {})
    when = returns.index[-1]
    rec = run_recommendation(
        config, returns, returns * 0.0, probs, conviction, regimes, when, overlay, simulations=40
    )
    return rec, returns, probs, regimes, conviction, overlay


def test_all_restrictions_hold(recommendation) -> None:  # type: ignore[no-untyped-def]
    rec = recommendation[0]
    assert set(rec.variants) == {"a", "b", "ab", "a+overlay", "b+overlay", "ab+overlay"}
    for variant in rec.variants.values():
        assert all(variant.target.checks.values()), variant.target.checks
        assert variant.target.tracking_error <= 0.03 + 1e-4


def test_decomposition_sums_exactly(recommendation) -> None:  # type: ignore[no-untyped-def]
    rec = recommendation[0]
    for variant in rec.variants.values():
        parts = variant.parts
        total = parts["Basis"] + parts["Regime"] + parts["Overlay"] + parts["Restriktionen"]
        pd.testing.assert_series_equal(total, parts["Ziel"], check_names=False, atol=1e-12)
    assert rec.variants["a"].parts["Overlay"].abs().max() == pytest.approx(0.0, abs=1e-12)
    assert rec.variants["a+overlay"].parts["Overlay"].abs().max() > 0


def test_no_lookahead_in_recommendation(  # type: ignore[no-untyped-def]
    config: AppConfig, recommendation
) -> None:
    """Renditen, Wahrscheinlichkeiten und Überzeugung nach t verändert: Empfehlung zu t gleich."""
    _, returns, probs, regimes, conviction, overlay = recommendation
    when = returns.index[100]
    later = returns.index > when

    def run(r: pd.DataFrame, p: dict[str, pd.DataFrame], c: pd.Series, g: pd.Series):  # type: ignore[no-untyped-def]
        return run_recommendation(config, r, r * 0.0, p, c, g, when, overlay, simulations=20)

    original = run(returns, probs, conviction, regimes)
    rng = np.random.default_rng(9)
    changed = returns.copy()
    changed.loc[later] = rng.normal(0.0, 0.1, size=changed.loc[later].shape)
    probs2 = {k: v.copy() for k, v in probs.items()}
    for frame in probs2.values():
        frame.loc[later] = rng.dirichlet(np.ones(4), size=int(later.sum()))
    conv2 = conviction.copy()
    conv2[later] = 0.01
    regimes2 = regimes.copy()
    regimes2[later] = "stagflation"
    perturbed = run(changed, probs2, conv2, regimes2)
    for key, variant in original.variants.items():
        pd.testing.assert_series_equal(
            variant.target.weights, perturbed.variants[key].target.weights
        )
        pd.testing.assert_series_equal(variant.signal, perturbed.variants[key].signal)
    pd.testing.assert_frame_equal(original.base.cov, perturbed.base.cov)


def test_every_light_has_a_reason(recommendation) -> None:  # type: ignore[no-untyped-def]
    rec = recommendation[0]
    for variant in rec.variants.values():
        assert set(variant.reasons.index) == set(variant.lights.index)
        for asset, light in variant.lights.items():
            text = variant.reasons[asset]
            assert text.startswith("Signal ")
            expected = {
                "grün": "über dem Mittel",
                "rot": "unter dem Mittel",
                "gelb": "nahe am Mittel",
            }
            assert expected[light] in text
    assert any("Overlay" in t for t in rec.variants["ab+overlay"].reasons)
