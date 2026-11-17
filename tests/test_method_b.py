"""Methode B: gefilterte HMM-Wahrscheinlichkeiten, Benennung, Vergleich, Look-ahead."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import AppConfig, HmmConfig
from navigator.data.pit import PitStore
from navigator.paths import ProjectPaths
from navigator.regimes.compare import agreement, b_drivers, conviction
from navigator.regimes.hmm import (
    GaussianParams,
    fit_hmm,
    forward_filter,
    name_states,
    prepare,
    refit_dates,
    run_method_b,
)
from navigator.regimes.method_a import month_ends, run_method_a
from navigator.regimes.method_b import run_comparison
from navigator.testing import perturb_parquet_tree

QUADRANT_MEANS = {  # (Wachstum, Inflation) je wahrem Zustand
    "disinflationary_boom": (1.2, -1.2),
    "reflation": (1.2, 1.2),
    "deflationary_bust": (-1.2, -1.2),
    "stagflation": (-1.2, 1.2),
}


def _synthetic(n: int = 480, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    """Regimewechsel-Daten: zwei Wachstums-, zwei Inflationsmerkmale, Markov-Kette."""
    rng = np.random.default_rng(seed)
    states = list(QUADRANT_MEANS)
    path = [0]
    for _ in range(n - 1):
        path.append(path[-1] if rng.random() < 0.95 else int(rng.integers(0, 4)))
    truth = pd.Series(
        [states[s] for s in path], index=pd.date_range("1980-01-31", periods=n, freq="ME")
    )
    g = np.array([QUADRANT_MEANS[s][0] for s in truth])
    i = np.array([QUADRANT_MEANS[s][1] for s in truth])
    noise = rng.normal(0, 0.6, (n, 4))
    features = pd.DataFrame(
        {
            "g1": g + noise[:, 0],
            "g2": g + noise[:, 1],
            "i1": i + noise[:, 2],
            "i2": i + noise[:, 3],
        },
        index=truth.index,
    )
    return features, truth


FAST = HmmConfig(n_starts=4, max_iter=100, min_train_months=120, refit_month=12)


def test_forward_filter_matches_last_row_of_smoothing_on_truncated_data() -> None:
    """Gefiltert zu t = geglättet auf den Daten bis t (letzte Zeile); nie Daten nach t."""
    from hmmlearn.hmm import GaussianHMM

    features, _ = _synthetic(240)
    x = features.to_numpy()
    params = fit_hmm(x[:200], 4, FAST)
    model = GaussianHMM(n_components=4, covariance_type="diag")
    model.startprob_, model.transmat_ = params.weights, params.transmat
    model.means_, model.covars_ = params.means, params.variances
    filtered = forward_filter(x, params)
    for t in (10, 99, 239):
        assert np.allclose(filtered[t], model.predict_proba(x[: t + 1])[-1], atol=1e-8)
    smoothed = model.predict_proba(x)
    assert not np.allclose(filtered[:-1], smoothed[:-1]), (
        "Filter darf nicht der Glättung entsprechen"
    )
    changed = x.copy()
    changed[150:] += 5.0
    assert np.allclose(forward_filter(changed, params)[:150], filtered[:150])


def test_states_are_named_by_hungarian_assignment() -> None:
    means = np.array([[-1.0, -1.1, 0.0], [1.0, -0.9, 0.0], [-0.8, 1.2, 0.0], [0.9, 1.1, 0.0]])
    params = GaussianParams(means=means, variances=np.ones_like(means), weights=np.full(4, 0.25))
    assigned, names = name_states(params, ["g", "i", "equity_vol_change_6m"], ["g"], ["i"], 0.75)
    assert assigned == ["deflationary_bust", "disinflationary_boom", "stagflation", "reflation"]
    assert names == assigned
    # B und D liegen beide bei Stagflation; einer muss den Aufschwung-Platz nehmen und
    # widerspricht ihm auf beiden Achsen. Mit hoher Volatilität heißt er „Finanzstress".
    stressed = np.array([[-1.0, -1.0, 0.0], [-1.0, 1.0, 2.0], [1.0, 1.0, 0.0], [-1.1, 1.1, 2.0]])
    p2 = GaussianParams(means=stressed, variances=np.ones_like(stressed), weights=np.full(4, 0.25))
    assigned2, names2 = name_states(p2, ["g", "i", "equity_vol_change_6m"], ["g"], ["i"], 0.75)
    assert sorted(assigned2) == sorted(QUADRANT_MEANS)
    assert names2.count("financial_stress") == 1
    assert assigned2[names2.index("financial_stress")] == "disinflationary_boom"
    calm = stressed.copy()
    calm[:, 2] = 0.0
    p3 = GaussianParams(means=calm, variances=np.ones_like(calm), weights=np.full(4, 0.25))
    assert (
        "financial_stress"
        not in name_states(p3, ["g", "i", "equity_vol_change_6m"], ["g"], ["i"], 0.75)[1]
    )


def test_refit_dates_are_yearly_after_minimum_history() -> None:
    index = pd.date_range("1980-01-31", periods=300, freq="ME")
    dates = refit_dates(index, FAST)
    assert dates[0] == index[119] and all(d.month == 12 for d in dates[1:])
    assert refit_dates(index[:100], FAST) == []


def test_prepare_fills_missing_with_neutral_value() -> None:
    frame = pd.DataFrame({"a": [1.0, np.nan, np.nan], "b": [2.0, 3.0, np.nan]})
    out = prepare(frame, 0.5)
    assert out.index.tolist() == [0, 1] and out.loc[1, "a"] == 0.0


def test_method_b_recovers_synthetic_regimes() -> None:
    features, truth = _synthetic(480, seed=3)
    result = run_method_b(features, FAST, ["g1", "g2"], ["i1", "i2"])
    joined = pd.concat([result.regime.rename("b"), truth.rename("t")], axis=1).dropna()
    assert len(joined) == 480 - 119
    assert (joined["b"] == joined["t"]).mean() > 0.85
    probs = result.probs.dropna()
    assert np.allclose(probs.sum(axis=1), 1.0)
    duration = result.expected_duration()
    assert (duration > 5).all()  # Persistenz p = 0,95 + 0,05/4 ⇒ rund 17 Monate
    matrix = result.transition_matrix()
    assert np.allclose(matrix.sum(axis=1), 1.0)
    assert set(result.bic_table["Zustände"]) == {3, 4, 5, 6}
    best = result.bic_table.loc[result.bic_table["BIC"].idxmin(), "Zustände"]
    assert best in (4, 5)
    gmm_rate, _ = agreement(result.gmm_regime, truth)
    assert gmm_rate > 0.7


def test_b_drivers_decompose_loglik_difference() -> None:
    features, _ = _synthetic(300, seed=5)
    result = run_method_b(features, FAST, ["g1", "g2"], ["i1", "i2"])
    when = result.regime.last_valid_index()
    table = b_drivers(result, when, top=0)
    params = result.models[result.model_of[when]]
    probs = result.state_probs.loc[when].to_numpy(dtype=float)
    first, second = np.argsort(probs)[::-1][:2]
    x = result.features.loc[when].to_numpy(dtype=float)[None, :]
    total = params.log_densities(x)[0, first] - params.log_densities(x)[0, second]
    assert table["Beitrag"].sum() == pytest.approx(total)


def test_conviction_and_agreement() -> None:
    index = pd.date_range("2020-01-31", periods=2, freq="ME")
    a = pd.DataFrame(
        [[1, 0, 0, 0], [0.25] * 4],
        index=index,
        columns=["disinflationary_boom", "reflation", "deflationary_bust", "stagflation"],
        dtype=float,
    )
    b = pd.DataFrame([[1, 0, 0, 0], [1, 0, 0, 0]], index=index, columns=a.columns, dtype=float)
    assert conviction(a, b).tolist() == pytest.approx([1.0, 0.25])
    rate, table = agreement(
        pd.Series(["reflation", "stagflation"], index=index),
        pd.Series(["reflation", "reflation"], index=index),
    )
    assert rate == 0.5 and table.to_numpy().sum() == 2


# ------------------------------------------------------------------- Ende zu Ende


def _fast_config(config: AppConfig) -> AppConfig:
    hmm = config.regime_map.hmm.model_copy(
        update={"n_starts": 1, "max_iter": 50, "start": "1985-01"}
    )
    regime_map = config.regime_map.model_copy(update={"hmm": hmm})
    return config.model_copy(update={"regime_map": regime_map})


def test_comparison_end_to_end_on_demo(config: AppConfig, demo_project: ProjectPaths) -> None:
    cfg = _fast_config(config)
    dates = month_ends("1980-01", pd.Timestamp("2026-10-31"))
    cmp = run_comparison(cfg, PitStore(demo_project.pit), dates)
    assert cmp.b.regime.notna().sum() > 200
    assert 0.0 <= cmp.agreement_rate <= 1.0
    assert cmp.conviction.dropna().between(0, 1).all()
    assert cmp.explanations.dropna().str.len().min() > 20
    assert set(cmp.b.features.columns) >= {
        "stock_bond_corr_change_6m",
        "equity_vol_change_6m",
        "us_cli",
    }


def test_no_lookahead_in_method_b(
    config: AppConfig, demo_project: ProjectPaths, tmp_path: Path
) -> None:
    """Look-ahead-Test: Daten nach t verändert, Merkmale und gefilterte B-Werte bis t gleich."""
    cfg = _fast_config(config)
    stamp = pd.Timestamp("2012-06-30")
    perturb_parquet_tree(demo_project.pit, tmp_path / "pit", stamp, seed=11)
    dates = month_ends("1980-01", stamp)
    first = run_comparison(cfg, PitStore(demo_project.pit), dates)
    second = run_comparison(cfg, PitStore(tmp_path / "pit"), dates)
    pd.testing.assert_frame_equal(first.b.features, second.b.features)
    pd.testing.assert_frame_equal(first.b.probs, second.b.probs)
    pd.testing.assert_frame_equal(first.b.gmm_probs, second.b.gmm_probs)
    pd.testing.assert_series_equal(first.conviction, second.conviction)
    full = month_ends("1980-01", pd.Timestamp("2026-10-31"))
    a_full = run_method_a(cfg, PitStore(demo_project.pit), full)
    later = run_comparison(cfg, PitStore(demo_project.pit), full, a_full)
    # Gleiche Daten, längere Historie: Werte bis t bleiben gleich (expandierendes Fenster)
    pd.testing.assert_frame_equal(later.b.probs.loc[:stamp], first.b.probs)
