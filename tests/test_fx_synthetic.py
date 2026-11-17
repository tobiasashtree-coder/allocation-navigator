"""Währungsumrechnung, Währungssicherung und synthetische Anleiherenditen."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from navigator.config import AppConfig
from navigator.data.fx import (
    FxRates,
    build_cash_returns,
    build_fx_rates,
    decompose,
    hedged_return,
    month_mean,
    to_month_end,
)
from navigator.data.synthetic import (
    blend_returns,
    check_against_fund,
    par_bond_risk,
    synthetic_bond_returns,
    synthetic_linker_returns,
)


def _daily(start: str, end: str, value: float) -> pd.Series:
    index = pd.bdate_range(start, end)
    return pd.Series(value, index=index)


def test_to_month_end_drops_unfinished_month_and_respects_asof() -> None:
    series = pd.Series(
        np.arange(1.0, 54.0), index=pd.bdate_range("2024-01-01", periods=53)
    )  # endet Mitte März
    monthly = to_month_end(series)
    assert list(monthly.index) == list(pd.to_datetime(["2024-01-31", "2024-02-29"]))
    assert monthly.iloc[-1] == series[:"2024-02-29"].iloc[-1]
    assert list(to_month_end(series, pd.Timestamp("2024-01-31")).index) == [
        pd.Timestamp("2024-01-31")
    ]
    fred_monthly = pd.Series(
        [1.0, 2.0, 3.0, 4.0], index=pd.date_range("2024-01-01", periods=4, freq="MS")
    )
    assert to_month_end(fred_monthly).index[0] == pd.Timestamp("2024-01-31")
    assert len(to_month_end(fred_monthly, pd.Timestamp("2024-02-29"))) == 2
    # Mitte Februar ist der Februarwert einer Monatsreihe noch nicht bekannt.
    assert len(to_month_end(fred_monthly, pd.Timestamp("2024-02-15"))) == 1


def test_fx_rates_combine_ecb_with_legacy_dem(config: AppConfig) -> None:
    """Ab 1999 EZB-Referenzkurse, davor der Euro synthetisch über die D-Mark."""

    def load(symbols: dict[str, str], kind: str) -> pd.Series | None:
        symbol = next(iter(symbols.values()))
        table = {
            "EXR/D.USD.EUR.SP00.A": _daily("1999-01-04", "1999-03-31", 1.10),
            "EXR/D.GBP.EUR.SP00.A": _daily("1999-01-04", "1999-03-31", 0.70),
            "DEXGEUS": _daily("1998-10-01", "1998-12-31", 1.70),  # DEM je USD
            "DEXUSUK": _daily("1998-10-01", "1999-03-31", 1.65),  # USD je GBP
            "DEXSZUS": _daily("1998-10-01", "1999-03-31", 1.40),  # CHF je USD
        }
        return table.get(symbol)

    fx = build_fx_rates(config.currency, load)
    usd = fx.usd_per_unit
    assert usd.loc["1998-12-31", "EUR"] == pytest.approx(1.95583 / 1.70)
    assert usd.loc["1999-01-31", "EUR"] == pytest.approx(1.10)
    assert usd.loc["1999-01-31", "GBP"] == pytest.approx(1.10 / 0.70)  # EZB hat Vorrang
    assert usd.loc["1998-12-31", "GBP"] == pytest.approx(1.65)  # davor Fed-Kurse
    assert usd.loc["1998-12-31", "CHF"] == pytest.approx(1 / 1.40)
    assert fx.rate("USD", "EUR").loc["1999-01-31"] == pytest.approx(1 / 1.10)
    assert fx.has("USD") and fx.has("CHF") and not fx.has("JPY")


def test_convert_returns_matches_definition_and_roundtrips() -> None:
    index = pd.date_range("2024-01-31", periods=4, freq="ME")
    fx = FxRates(pd.DataFrame({"EUR": [1.10, 1.21, 1.21, 1.089]}, index=index))
    local = pd.Series([0.0, 0.05, -0.02, 0.01], index=index)
    in_eur = fx.convert_returns(local, "USD", "EUR")
    # Der Euro wertet im Februar 10 % auf: der USD-Anleger verliert in EUR gerechnet.
    assert in_eur.loc["2024-02-29"] == pytest.approx(1.05 / 1.10 - 1.0)
    back = fx.convert_returns(in_eur, "EUR", "USD")
    pd.testing.assert_series_equal(back, local.iloc[1:], check_names=False)
    assert fx.convert_returns(local, "EUR", "EUR").equals(local)
    assert (fx.fx_return("USD", "USD") == 0).all()


def test_hedged_return_adds_rate_differential() -> None:
    index = pd.date_range("2024-01-31", periods=2, freq="ME")
    local = pd.Series([0.01, -0.02], index=index)
    cash_eur = pd.Series([0.03 / 12, 0.03 / 12], index=index)
    cash_usd = pd.Series([0.05 / 12, 0.05 / 12], index=index)
    hedged = hedged_return(local, cash_eur, cash_usd)
    assert hedged.iloc[0] == pytest.approx(0.01 - 0.02 / 12)
    parts = decompose(hedged, hedged - local)
    assert np.allclose(parts["local"] + parts["currency"], parts["total"])


def test_cash_returns_use_monthly_mean_and_segment_order(config: AppConfig) -> None:
    def load(symbols: dict[str, str], kind: str) -> pd.Series | None:
        symbol = next(iter(symbols.values()))
        if symbol == "EST/B.EU000A2X2A25.WT":
            return _daily("2020-01-01", "2020-03-31", 2.4)
        if symbol == "EON/D.EONIA_TO.RATE":
            return _daily("2019-11-01", "2020-03-31", 1.2)
        if symbol == "DFF":
            return _daily("2019-11-01", "2020-03-31", 6.0)
        return None

    cash = build_cash_returns(config.currency, load)
    assert cash.loc["2020-01-31", "EUR"] == pytest.approx(0.002)  # €STR hat Vorrang
    assert cash.loc["2019-12-31", "EUR"] == pytest.approx(0.001)  # davor EONIA
    assert cash.loc["2020-01-31", "USD"] == pytest.approx(0.005)
    assert "CHF" not in cash.columns
    daily = pd.Series([1.0, 3.0], index=pd.to_datetime(["2024-01-02", "2024-01-31"]))
    assert month_mean(pd.concat([daily, _daily("2024-02-01", "2024-02-29", 5.0)])).iloc[0] == 2.0


# ------------------------------------------------------------------------ synthetisch


@pytest.mark.parametrize(
    ("y", "maturity"), [(0.04, 10.0), (0.08, 25.0), (0.005, 2.0), (-0.003, 10.0)]
)
def test_par_bond_risk_matches_numerical_derivatives(y: float, maturity: float) -> None:
    def price(rate: float) -> float:
        n = int(maturity * 2)
        flows = np.full(n, y / 2)
        flows[-1] += 1.0
        return float(np.sum(flows / (1 + rate / 2) ** np.arange(1, n + 1)))

    h = 1e-4
    duration = -(price(y + h) - price(y - h)) / (2 * h)
    convexity = (price(y + h) - 2 * price(y) + price(y - h)) / h**2
    d, c = par_bond_risk(y, maturity)
    assert d[0] == pytest.approx(duration, rel=1e-4)
    assert c[0] == pytest.approx(convexity, rel=1e-3)


def test_par_bond_risk_is_stable_near_zero_yield() -> None:
    d, c = par_bond_risk(np.array([0.0, 1e-6, 2e-4]), 10.0)
    assert d[0] == 10.0 and c[0] == pytest.approx(105.0)
    assert d[2] == pytest.approx(10.0, rel=2e-3) and c[2] == pytest.approx(105.0, rel=5e-3)


def test_synthetic_bond_returns_follow_carry_duration_convexity() -> None:
    index = pd.date_range("2024-01-31", periods=3, freq="ME")
    yields = pd.Series([4.0, 4.5, 4.5], index=index)
    returns = synthetic_bond_returns(yields, 10.0)
    d, c = par_bond_risk(0.04, 10.0)
    assert returns.iloc[0] == pytest.approx(0.04 / 12 - d[0] * 0.005 + 0.5 * c[0] * 0.005**2)
    assert returns.iloc[1] == pytest.approx(0.045 / 12)  # unveränderte Rendite: nur Kupon-Ertrag
    assert returns.iloc[0] < -0.03


def test_synthetic_linker_uses_only_published_inflation() -> None:
    index = pd.date_range("2024-01-31", periods=8, freq="ME")
    real = pd.Series(1.0, index=index)
    cpi = pd.Series([100, 101, 101, 101, 101, 103.02, 103.02, 103.02], index=index, dtype=float)
    returns = synthetic_linker_returns(real, cpi, 10.0, lag_months=3)
    carry = 0.01 / 12
    # Der Preisanstieg vom Februar wirkt erst im April, der vom Juni erst im August.
    assert returns.loc["2024-04-30"] == pytest.approx(carry + 0.01)
    assert returns.loc["2024-06-30"] == pytest.approx(carry)
    assert returns.loc["2024-08-31"] == pytest.approx(carry + 0.02)


def test_blend_and_fund_check() -> None:
    index = pd.date_range("2020-01-31", periods=36, freq="ME")
    rng = np.random.default_rng(3)
    a = pd.Series(rng.normal(0, 0.03, 36), index=index)
    b = pd.Series(rng.normal(0, 0.03, 36), index=index)
    blend = blend_returns([(a, 0.5), (b, 0.5)])
    assert np.allclose(blend, 0.5 * a + 0.5 * b)
    good = check_against_fund(a, a + rng.normal(0, 0.002, 36))
    assert good.accepted and good.months == 36 and good.correlation > 0.95
    assert not check_against_fund(a, b).accepted
    assert not check_against_fund(a.iloc[:6], a.iloc[:6]).accepted  # zu kurze Überlappung
