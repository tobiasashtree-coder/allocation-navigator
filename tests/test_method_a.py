"""Methode A: Transformation, Regime-Regeln, Schuldenzyklus und Look-ahead-Tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import AppConfig, CreditCycleRules, Indicator, IndicatorDefaults, RegimeRules
from navigator.data.pit import PitSeries, PitStore
from navigator.features.credit_cycle import raw_phase
from navigator.features.scores import indicator_values, pit_values, transform
from navigator.paths import ProjectPaths
from navigator.regimes.method_a import month_ends, run_method_a
from navigator.regimes.rules import classify, quadrant_probabilities
from navigator.testing import perturb_parquet_tree

DEFAULTS = IndicatorDefaults()


def _indicator(**kwargs: object) -> Indicator:
    base: dict[str, object] = {
        "name": "x",
        "region": "US",
        "axis": "growth",
        "symbols": {"fred": "X"},
    }
    base.update(kwargs)
    return Indicator(**base)  # type: ignore[arg-type]


def test_transform_follows_spec_formula() -> None:
    index = pd.date_range("1990-01-31", periods=240, freq="ME")
    rng = np.random.default_rng(0)
    x = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.01, 240))), index=index)
    z = transform(x, _indicator(change="pct"), DEFAULTS)
    change = x / x.shift(6) - 1
    window = change.iloc[100:220]
    expected = (change.iloc[219] - window.mean()) / window.std()
    assert z.iloc[219] == pytest.approx(np.clip(expected, -3, 3))
    assert z.iloc[:65].isna().all()  # 6 Monate Veränderung + mindestens 60 Monate Fenster
    assert z.abs().max() <= 3.0
    inverted = transform(x, _indicator(change="pct", invert=True), DEFAULTS)
    assert inverted.iloc[219] == pytest.approx(-z.iloc[219])


def test_core_momentum_is_three_month_annualized_minus_twelve_month() -> None:
    index = pd.date_range("1990-01-31", periods=200, freq="ME")
    rng = np.random.default_rng(1)
    x = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.003, 200))), index=index)
    z = transform(x, _indicator(change="core_momentum", axis="inflation"), DEFAULTS)
    change = (x / x.shift(3)) ** 4 - 1 - (x / x.shift(12) - 1)
    window = change.iloc[80:200]
    assert z.iloc[199] == pytest.approx(
        np.clip((change.iloc[199] - window.mean()) / window.std(), -3, 3)
    )


def test_quarterly_series_uses_quarterly_windows() -> None:
    index = pd.date_range("1980-03-31", periods=120, freq="QE")
    x = pd.Series(np.cumsum(np.random.default_rng(2).normal(0, 1, 120)), index=index)
    z = transform(x, _indicator(change="diff", frequency="Q"), DEFAULTS)
    assert z.first_valid_index() == index[2 + 20 - 1]  # 2 Quartale Veränderung, 20 Quartale Minimum


def test_pit_values_respect_publication_and_staleness() -> None:
    obs = pd.date_range("2000-01-31", periods=30, freq="ME")
    frame = pd.DataFrame(
        {"obs_date": obs, "value": np.arange(30.0), "known_from": obs + pd.offsets.MonthEnd(1)}
    )
    series = PitSeries("x", frame)
    dates = pd.date_range("2000-01-31", "2003-12-31", freq="ME")
    values, seen = pit_values(series, dates, "M", lambda s: s)
    assert np.isnan(values["2000-01-31"])  # Januarwert erst Ende Februar bekannt
    assert values["2000-02-29"] == 0.0 and seen["2000-02-29"] == pd.Timestamp("2000-01-31")
    assert values["2002-07-31"] == 29.0
    # letzte Beobachtung 06/2002: ab 11/2002 (älter als 4 Monate) fällt der Indikator aus
    assert values["2002-10-31"] == 29.0 and np.isnan(values["2002-11-30"])


def test_revised_series_uses_vintage_known_at_each_date() -> None:
    obs = pd.date_range("1990-01-31", periods=200, freq="ME")
    first = pd.DataFrame(
        {
            "obs_date": obs,
            "value": np.linspace(100, 200, 200),
            "known_from": obs + pd.Timedelta(days=15),
        }
    )
    revised = first.iloc[-50:].copy()
    revised["value"] = revised["value"] * 1.5
    revised["known_from"] = pd.Timestamp("2010-06-15")
    series = PitSeries("x", pd.concat([first, revised]))
    dates = pd.DatetimeIndex([pd.Timestamp("2010-05-31"), pd.Timestamp("2010-06-30")])
    before = indicator_values("x", _indicator(change="pct"), series, dates, DEFAULTS).z
    assert before.iloc[0] != pytest.approx(before.iloc[1])  # Revision ab 15.06. wirkt erst danach


# ------------------------------------------------------------------------- Regeln


def test_quadrant_probabilities_multiply_axes() -> None:
    probs = quadrant_probabilities(pd.Series([0.0, 2.0]), pd.Series([0.0, -2.0]), 1.5)
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert probs.iloc[0].tolist() == pytest.approx([0.25] * 4)
    pg = 1 / (1 + np.exp(-3.0))
    assert probs.loc[1, "disinflationary_boom"] == pytest.approx(pg * pg)


def test_regime_switch_needs_two_months_or_strong_signal() -> None:
    index = pd.date_range("2020-01-31", periods=8, freq="ME")
    growth = pd.Series([1.0, 1.0, -0.5, 1.0, -0.5, -0.5, -0.5, -0.1], index=index)
    inflation = pd.Series([-1.0] * 8, index=index)
    out = classify(growth, inflation, RegimeRules())
    regimes = out["regime"].tolist()
    assert regimes[:4] == ["disinflationary_boom"] * 4  # ein Monat Ausreißer reicht nicht
    assert regimes[4] == "disinflationary_boom" and regimes[5] == "deflationary_bust"
    # -0,1 liegt im neutralen Band: die Wachstumsrichtung bleibt "fällt"
    assert regimes[7] == "deflationary_bust" and bool(out["growth_neutral"].iloc[7])
    strong = classify(
        pd.Series([1.0, -2.5], index=index[:2]),
        pd.Series([-2.5, -2.5], index=index[:2]),
        RegimeRules(),
    )
    assert strong["regime"].tolist() == ["disinflationary_boom", "deflationary_bust"]


def test_missing_scores_give_no_regime() -> None:
    index = pd.date_range("2020-01-31", periods=3, freq="ME")
    out = classify(
        pd.Series([np.nan, 1.0, 1.0], index=index),
        pd.Series([1.0, 1.0, np.nan], index=index),
        RegimeRules(),
    )
    assert out["regime"].isna().tolist() == [True, False, True]


def test_credit_cycle_majority_rule() -> None:
    rules = CreditCycleRules()
    base = {
        "policy_rate": 3.0,
        "policy_change_6m": 0.0,
        "policy_change_12m": 0.0,
        "real_gap": -0.2,
        "curve": 1.0,
        "spread": 3.0,
        "spread_change_6m": 0.1,
        "spread_median_10y": 2.5,
        "credit_impulse": 1.0,
    }
    assert raw_phase(pd.Series(base), rules) == "mid"
    # Kontraktion: zwei von drei Signalen
    assert (
        raw_phase(pd.Series({**base, "spread_change_6m": 0.8, "policy_change_6m": -0.5}), rules)
        == "contraction"
    )
    assert (
        raw_phase(pd.Series({**base, "policy_change_6m": -0.5, "credit_impulse": -2.0}), rules)
        == "contraction"
    )
    assert raw_phase(pd.Series({**base, "spread_change_6m": 0.8}), rules) == "mid"
    # Spät: realer Abstand positiv und Kurve flach
    assert raw_phase(pd.Series({**base, "real_gap": 0.5, "curve": 0.2}), rules) == "late"
    assert raw_phase(pd.Series({**base, "real_gap": 0.5}), rules) == "mid"
    # Früh: Leitzins gesenkt und Kurve steil
    assert raw_phase(pd.Series({**base, "policy_change_12m": -1.0, "curve": 2.0}), rules) == "early"
    assert raw_phase(pd.Series({**base, "curve": 2.0, "spread_change_6m": -0.2}), rules) == "early"
    # fehlende Eingaben zählen nicht als Signal
    assert (
        raw_phase(pd.Series({**base, "curve": np.nan, "real_gap": 0.5, "spread": np.nan}), rules)
        == "mid"
    )
    assert raw_phase(pd.Series({**base, "policy_rate": np.nan}), rules) is None


def test_month_ends_exclude_unfinished_month() -> None:
    dates = month_ends("2026-01", pd.Timestamp("2026-11-17"))
    assert dates[0] == pd.Timestamp("2026-01-31") and dates[-1] == pd.Timestamp("2026-10-31")
    assert month_ends("2026-01", pd.Timestamp("2026-10-31"))[-1] == pd.Timestamp("2026-10-31")


# ------------------------------------------------------------------- Ende zu Ende


@pytest.fixture(scope="module")
def method_a(config: AppConfig, demo_project: ProjectPaths):  # type: ignore[no-untyped-def]
    dates = month_ends("1990-01", pd.Timestamp("2026-10-31"))
    return run_method_a(config, PitStore(demo_project.pit), dates)


def test_method_a_end_to_end_on_demo(method_a, config: AppConfig) -> None:  # type: ignore[no-untyped-def]
    table = method_a.regimes["GLOBAL"]
    assert set(table["regime"].dropna()) <= set(config.regime_map.quadrants)
    assert table["regime"].notna().mean() > 0.8
    assert len(method_a.episodes) == len(config.regime_map.episodes)
    assert set(method_a.credit["phase"].dropna()) <= {"early", "mid", "late", "contraction"}
    when = table.index[-1]
    contrib = method_a.scores.contributions(when, "US", "growth")
    assert contrib.sum() == pytest.approx(method_a.scores.region_scores.loc[when, ("US", "growth")])


@pytest.mark.parametrize("when", ["2004-06-30", "2015-11-30", "2025-12-31"])
def test_no_lookahead_in_method_a(
    config: AppConfig, demo_project: ProjectPaths, tmp_path: Path, when: str
) -> None:
    """Look-ahead-Test: Alle Daten nach t verändert, Scores, Regime und Schuldenzyklus bis t gleich."""
    stamp = pd.Timestamp(when)
    changed = perturb_parquet_tree(demo_project.pit, tmp_path / "pit", stamp, seed=7)
    assert changed > 10
    dates = month_ends("1995-01", stamp)
    original = run_method_a(config, PitStore(demo_project.pit), dates)
    perturbed = run_method_a(config, PitStore(tmp_path / "pit"), dates)
    pd.testing.assert_frame_equal(original.scores.z, perturbed.scores.z)
    for name in ("GLOBAL", "US", "EA"):
        pd.testing.assert_frame_equal(original.regimes[name], perturbed.regimes[name])
    pd.testing.assert_frame_equal(original.credit, perturbed.credit)
    later = month_ends("1995-01", pd.Timestamp("2026-10-31"))
    full_a = run_method_a(config, PitStore(demo_project.pit), later).scores.z
    full_b = run_method_a(config, PitStore(tmp_path / "pit"), later).scores.z
    assert not full_a.equals(full_b), "Gegenprobe: ohne Stichtag unterscheiden sich die Ergebnisse"
