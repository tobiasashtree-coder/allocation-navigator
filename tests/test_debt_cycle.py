"""Langfristiger Schuldenzyklus (M4): Rohreihen, Score, Phasen, Overlay, Look-ahead."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.allocation.overlay import apply_overlay, provisional_base, usd_share
from navigator.config import AppConfig, DebtInput, PublicationLag, SourceConfig
from navigator.data.debt import debt_series_specs
from navigator.data.pit import PitSeries, PitStore
from navigator.data.providers.base import SeriesRequest
from navigator.data.providers.imf import ImfProvider
from navigator.data.providers.static import panel_slice
from navigator.features.debt_stress import (
    ReferencePool,
    annualize,
    component_history,
    phase_distance,
    phase_for,
    run_debt_stress,
)
from navigator.paths import ProjectPaths
from navigator.testing import perturb_parquet_tree
from tests.conftest import FakeHttp

# --------------------------------------------------------------------- Rohreihen


def test_panel_slice_reads_one_country() -> None:
    table = pd.DataFrame(
        {
            "year": [2000, 2001, 2000, 2001],
            "iso": ["USA", "USA", "DEU", "DEU"],
            "debtgdp": [0.5, 0.55, 0.6, 0.62],
        }
    )
    usa = panel_slice(table, "usa", "iso", "year")
    assert list(usa.index) == [pd.Timestamp("2000-12-31"), pd.Timestamp("2001-12-31")]
    assert usa["debtgdp"].tolist() == [0.5, 0.55]


def test_imf_provider_drops_current_and_future_years() -> None:
    now = pd.Timestamp.today().year
    payload = {
        "values": {"d": {"USA": {str(now - 2): 100.0, str(now - 1): 110.0, str(now): 120.0}}}
    }
    http = FakeHttp({"datamapper/api/v1/d/USA": payload})
    provider = ImfProvider(SourceConfig(priority=20), http)  # type: ignore[arg-type]
    frame = provider.fetch_series(SeriesRequest(symbol="d/USA", kind="macro"))
    assert frame["value"].tolist() == [100.0, 110.0]
    assert frame["obs_date"].iloc[-1] == pd.Timestamp(now - 1, 12, 31)


def test_debt_specs_use_panel_once_and_respect_countries(config: AppConfig) -> None:
    specs = debt_series_specs(config)
    keys = [s.key for s in specs]
    assert len(keys) == len(set(keys))
    assert "debt.panel.USA.jst_debtgdp" in keys
    assert "debt.US.jst_debtgdp" not in keys
    assert "debt.US.term_premium" in keys and "debt.DE.term_premium" not in keys
    assert "debt.CN.long_rate" not in keys  # keine freie Langfristzinsreihe für China
    assert sum(k.startswith("debt.global.") for k in keys) == 1


def test_annualize_is_conservative_and_drops_incomplete_years() -> None:
    dates = pd.date_range("2020-01-01", "2022-06-01", freq="MS")
    frame = pd.DataFrame(
        {
            "obs_date": dates,
            "value": np.arange(len(dates), dtype=float),
            "known_from": dates + pd.Timedelta(days=40),
            "approx": True,
        }
    )
    item = DebtInput(source="fred", frequency="M", publication_lag=PublicationLag(months=1))
    annual = annualize(PitSeries("x", frame), item, "US")
    latest = annual.latest()
    assert list(latest.index.year) == [2020, 2021]  # 2022 unvollständig
    assert latest.iloc[0] == pytest.approx(np.mean(np.arange(12)))
    known = annual.frame.set_index("obs_date")["known_from"]
    assert known.iloc[0] >= pd.Timestamp("2021-01-31")
    assert annual.as_of(pd.Timestamp("2021-01-15")).empty


# --------------------------------------------------------------------- Bestandteile


def _years(values: list[float], start: int = 2000) -> pd.Series:
    return pd.Series(values, index=pd.date_range(f"{start}-12-31", periods=len(values), freq="YE"))


def test_component_history_chains_sources_in_order() -> None:
    recent = _years([80.0, 82.0, 84.0], start=2008)
    history = _years([50.0 + i for i in range(11)], start=2000)  # 2000..2010
    data = {"debt_weo": recent, "debt_fpp": history}
    comps = component_history(data)
    assert comps.loc["2009-12-31", "debt_gdp"] == 82.0  # WEO hat Vorrang
    assert comps.loc["2001-12-31", "debt_gdp"] == 51.0  # FPP füllt die Historie
    assert comps.loc["2009-12-31", "debt_change_5y"] == pytest.approx(82.0 - 54.0)


def test_component_history_interest_and_r_minus_g() -> None:
    data = {
        "primary_balance_fm": _years([-2.0, -1.0]),
        "net_lending_weo": _years([-5.0, -4.0]),
        "revenue_fm": _years([30.0, 30.0]),
        "long_rate": _years([4.0, 5.0]),
        "real_growth_weo": _years([2.0, 2.0]),
        "inflation_weo": _years([2.0, 2.0]),
    }
    comps = component_history(data)
    assert comps["interest_revenue"].iloc[-1] == pytest.approx(10.0)  # 3 % BIP / 30 %
    assert comps["primary_deficit"].iloc[-1] == pytest.approx(1.0)
    nominal = (1.02 * 1.02 - 1) * 100
    assert comps["r_minus_g"].iloc[-1] == pytest.approx(np.mean([4 - nominal, 5 - nominal]))


def test_percentile_uses_only_known_reference_values() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2000-12-31"] * 3 + ["2010-12-31"] * 3),
            "value": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
        }
    )
    pool = ReferencePool({"x": frame})
    assert pool.percentile("x", 2.5, pd.Timestamp("2005-01-01"), 3) == pytest.approx(2 / 3)
    assert pool.percentile("x", 2.5, pd.Timestamp("2011-01-01"), 3) == pytest.approx(2 / 6)
    assert np.isnan(pool.percentile("x", 2.5, pd.Timestamp("2005-01-01"), 4))


def test_phase_rules(config: AppConfig) -> None:
    score = config.debt_cycle.score
    t = [35.0, 60.0, 80.0]
    assert phase_for(pd.Series({"score": 20.0}), t, score) == "gesund"
    assert phase_for(pd.Series({"score": 50.0}), t, score) == "Aufbau"
    assert phase_for(pd.Series({"score": 70.0}), t, score) == "Übertreibung"
    assert phase_for(pd.Series({"score": 90.0}), t, score) == "Spätphase (Finanzierungsstress)"
    repression = pd.Series(
        {"score": 70.0, "p:debt_gdp": 0.9, "debt_change_5y": -20.0, "r_minus_g": -2.0}
    )
    assert phase_for(repression, t, score) == "Entschuldung / Monetarisierung"
    repression["r_minus_g"] = 1.0  # Abbau ohne negatives r − g zählt nicht
    assert phase_for(repression, t, score) == "Übertreibung"
    qe = pd.Series({"score": 85.0, "p:debt_gdp": 0.95, "cb_assets_change_3y": 25.0})
    assert phase_for(qe, t, score) == "Entschuldung / Monetarisierung"
    assert phase_for(pd.Series({"score": np.nan}), t, score) is None
    assert phase_distance("gesund", "Spätphase (Finanzierungsstress)") == 3


# --------------------------------------------------------------------- Overlay


def _base(config: AppConfig) -> pd.Series:
    assets = list(config.universe.enabled_assets())
    weights = pd.Series(1.0, index=assets)
    weights["bitcoin"] = 0.3  # unter der Obergrenze von 3 %
    return weights / weights.sum()


def test_overlay_full_strength_in_late_phase(config: AppConfig) -> None:
    base = _base(config)
    scores = {"US": 80.0, "DE": 50.0, "FR": 55.0, "IT": 70.0, "GB": 60.0, "JP": 90.0, "CN": 65.0}
    result = apply_overlay(base, config, {"US": "Spätphase (Finanzierungsstress)"}, scores)
    w = result.weights
    assert w.sum() == pytest.approx(1.0)
    assert (w >= 0).all()
    assert result.lambdas[0].value == pytest.approx(1.0)
    assert w["gold"] == pytest.approx(0.125)
    assert w["bitcoin"] == pytest.approx(0.03)
    assert w["bond_us_long"] < base["bond_us_long"]
    assert w["equity_us"] == pytest.approx(base["equity_us"] * 0.75)
    assert w["equity_europe"] > base["equity_europe"]  # niedrigerer Schuldenstress
    assert w["equity_japan"] < base["equity_japan"]  # höherer Stress: finanziert nur mit
    assert result.usd_cap == pytest.approx(0.30)


def test_overlay_scales_with_lambda_and_vanishes_when_healthy(config: AppConfig) -> None:
    base = _base(config)
    scores = {"US": 80.0}
    healthy = apply_overlay(base, config, {"US": "gesund"}, scores)
    if config.debt_cycle.assessments.get("US", {}).get("phase"):
        # manuelle Einschätzung hat Vorrang (phase_source manual_then_measured)
        assert healthy.lambdas[0].source == "manuell"
    custom = config.model_copy(deep=True)
    custom.debt_cycle.phase_source = "measured"
    healthy = apply_overlay(base, custom, {"US": "gesund"}, scores)
    pd.testing.assert_series_equal(healthy.weights, base / base.sum())
    half = apply_overlay(base, custom, {"US": "Übertreibung"}, scores)
    lam = custom.debt_cycle.lambda_by_phase["Übertreibung"]
    assert half.lambdas[0].value == pytest.approx(lam)
    full = apply_overlay(base, custom, {"US": "Spätphase (Finanzierungsstress)"}, scores)
    assert base["gold"] < half.weights["gold"] < full.weights["gold"]


def test_provisional_base_respects_caps_and_excludes_cash(config: AppConfig) -> None:
    rng = np.random.default_rng(1)
    assets = list(config.universe.enabled_assets())
    returns = pd.DataFrame(
        rng.normal(0.005, 0.03, size=(80, len(assets))),
        index=pd.date_range("2018-01-31", periods=80, freq="ME"),
        columns=assets,
    )
    returns["cash"] = 0.001
    returns["bitcoin"] = rng.normal(0.02, 0.0001, size=80)  # künstlich ruhig: Obergrenze greift
    base = provisional_base(returns, config)
    assert base.sum() == pytest.approx(1.0)
    assert "cash" not in base.index
    assert base["bitcoin"] <= 0.03 + 1e-9
    assert 0 <= usd_share(base, config) <= 1


# --------------------------------------------------------------------- Look-ahead


def _small(config: AppConfig) -> AppConfig:
    custom = config.model_copy(deep=True)
    score = custom.debt_cycle.score
    score.countries = ["US", "DE"]
    score.panel = ["USA", "DEU", "FRA", "ITA"]
    score.panel_start_year = 1975
    score.start = "2000-01"
    score.min_reference = 5
    score.thresholds = [40.0, 55.0, 70.0]  # festgeschrieben, sonst flösse die Kalibrierung ein
    return custom


@pytest.mark.parametrize("when", ["2008-06-30", "2016-12-31"])
def test_no_lookahead_in_debt_stress(
    config: AppConfig, demo_project: ProjectPaths, tmp_path: Path, when: str
) -> None:
    """Alle Daten nach t verändert: Score, Perzentile und Phasen bis t unverändert."""
    custom = _small(config)
    stamp = pd.Timestamp(when)
    changed = perturb_parquet_tree(demo_project.pit, tmp_path / "pit", stamp, seed=11)
    assert changed > 10
    end = pd.Timestamp("2026-10-31")
    original = run_debt_stress(custom, PitStore(demo_project.pit), end)
    perturbed = run_debt_stress(custom, PitStore(tmp_path / "pit"), end)
    for country in custom.debt_cycle.score.countries:
        a, b = original.monthly[country], perturbed.monthly[country]
        assert not a.empty
        pd.testing.assert_frame_equal(a[a.index <= stamp], b[b.index <= stamp])
        ya, yb = original.year_end[country], perturbed.year_end[country]
        pd.testing.assert_frame_equal(ya[ya.index <= stamp], yb[yb.index <= stamp])
    later = original.monthly["US"]["score"]
    assert not later.equals(perturbed.monthly["US"]["score"]), "Gegenprobe: danach verschieden"


def test_identical_country_series_are_reported(config: AppConfig) -> None:
    from navigator.features.debt_stress import OwnerInputs, identical_inputs

    years = pd.date_range("2000-12-31", periods=10, freq="YE")

    def pit(values: np.ndarray) -> PitSeries:
        frame = pd.DataFrame(
            {"obs_date": years, "value": values, "known_from": years, "approx": True}
        )
        return PitSeries("x", frame)

    same = np.arange(10, dtype=float)
    inputs = {
        "US": OwnerInputs("US", {"eer_broad": pit(same), "dsr": pit(same + 1)}),
        "DE": OwnerInputs("DE", {"eer_broad": pit(same), "dsr": pit(same + 2)}),
    }
    issues = identical_inputs(inputs, config.debt_cycle.score)
    assert len(issues) == 1 and "eer_broad" in issues[0]
