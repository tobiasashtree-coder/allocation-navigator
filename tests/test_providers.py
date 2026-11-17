"""Provider: Antwortformate der Quellen, Fehlerfälle, Auswahl nach Priorität (ohne Netz)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from navigator.config import AppConfig, SourceConfig
from navigator.data.providers import build_providers, rank_providers
from navigator.data.providers.base import (
    ProviderDisabledError,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
)
from navigator.data.providers.fred import FredProvider, collapse_vintages
from navigator.data.providers.licensed import MsciProvider, SipaProvider
from navigator.data.providers.market import (
    CoinMetricsProvider,
    EodhdProvider,
    TiingoProvider,
    YahooProvider,
)
from navigator.data.providers.sdmx import (
    BundesbankProvider,
    EcbProvider,
    OecdProvider,
    parse_sdmx_csv,
    period_end,
)
from navigator.http import HttpError
from navigator.paths import ProjectPaths
from tests.conftest import FakeHttp

FRED_CFG = SourceConfig(api_key_env="FRED_API_KEY")


def _obs(rows: list[tuple[str, str, str]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "observations": [
            {"realtime_start": rs, "realtime_end": "9999-12-31", "date": d, "value": v}
            for d, v, rs in rows
        ],
    }


# ------------------------------------------------------------------------------ FRED


def test_fred_latest_values_skip_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    http = FakeHttp(
        {
            "series/observations": _obs(
                [
                    ("2024-01-01", "3.9", "2024-06-01"),
                    ("2024-01-02", ".", "2024-06-01"),
                    ("2024-01-03", "4.1", "2024-06-01"),
                ]
            )
        }
    )
    frame = FredProvider(FRED_CFG, http).fetch_series(SeriesRequest("DGS10", "yield"))
    assert list(frame["value"]) == [3.9, 4.1]
    assert http.calls[0][1]["series_id"] == "DGS10" and http.calls[0][1]["api_key"] == "test-key"
    assert "known_from" not in frame.columns


def test_fred_vintages_keep_only_real_revisions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "k")
    rows = [
        ("2024-01-01", "100.0", "2024-02-15"),
        ("2024-01-01", "100.0", "2024-03-15"),  # unverändert: kein neuer Datenstand
        ("2024-01-01", "100.4", "2024-04-15"),
        ("2024-02-01", "101.0", "2024-03-15"),
    ]
    http = FakeHttp({"series/observations": _obs(rows)})
    frame = FredProvider(FRED_CFG, http).fetch_series(
        SeriesRequest("INDPRO", "macro", vintages=True)
    )
    assert http.calls[0][1]["realtime_start"] == "1776-07-04"
    assert len(frame) == 3
    january = frame[frame["obs_date"] == "2024-01-01"]
    assert list(january["known_from"].dt.strftime("%Y-%m-%d")) == ["2024-02-15", "2024-04-15"]


def test_fred_vintages_fall_back_to_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "k")

    def observations(url: str, params: dict[str, Any]) -> Any:
        if params["realtime_start"] == "1776-07-04":
            return HttpError("HTTP 400", status=400, body="exceeds 2000 vintage dates limit")
        return _obs([("2024-01-01", "1.0", params["realtime_start"])])

    http = FakeHttp(
        {
            "series/vintagedates": {"vintage_dates": ["2024-02-15", "2024-03-15"]},
            "series/observations": observations,
        }
    )
    frame = FredProvider(FRED_CFG, http).fetch_series(SeriesRequest("X", "macro", vintages=True))
    assert len(frame) == 1 and frame["known_from"].iloc[0] == pd.Timestamp("2024-02-15")


def test_fred_without_key_uses_csv_but_refuses_vintages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    http = FakeHttp({"fredgraph.csv": "observation_date,DGS10\n2024-01-02,3.95\n2024-01-03,.\n"})
    provider = FredProvider(FRED_CFG, http)
    frame = provider.fetch_series(SeriesRequest("DGS10", "yield"))
    assert list(frame["value"]) == [3.95]
    with pytest.raises(ProviderError, match="API-Key"):
        provider.fetch_series(SeriesRequest("INDPRO", "macro", vintages=True))


def test_collapse_vintages_orders_by_release() -> None:
    frame = pd.DataFrame(
        {
            "obs_date": pd.to_datetime(["2024-01-01"] * 3),
            "value": [2.0, 1.0, 1.0],
            "known_from": pd.to_datetime(["2024-04-01", "2024-02-01", "2024-03-01"]),
        }
    )
    assert list(collapse_vintages(frame)["value"]) == [1.0, 2.0]


# ------------------------------------------------------------------------------ SDMX


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-03-15", "2024-03-15"),
        ("2024-02", "2024-02-29"),
        ("2024-M02", "2024-02-29"),
        ("2024-Q1", "2024-03-31"),
        ("2024-S2", "2024-12-31"),
        ("2023", "2023-12-31"),
        ("2024-W01", "2024-01-07"),
    ],
)
def test_period_end(text: str, expected: str) -> None:
    assert period_end(text) == pd.Timestamp(expected)


def test_sdmx_csv_ecb_style() -> None:
    text = (
        "KEY,FREQ,CURRENCY,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,2024-01-02,1.0956,A\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,2024-01-03,1.0919,A\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,2024-01-04,,H\n"
    )
    frame = parse_sdmx_csv(text)
    assert list(frame["value"]) == [1.0956, 1.0919]


def test_sdmx_csv_semicolon_decimal_comma_and_longest_series() -> None:
    text = (
        "DATAFLOW;FREQ;AREA;TIME_PERIOD;OBS_VALUE\n"
        "X;M;DE;2024-01;2,5\nX;M;DE;2024-02;2,6\nX;M;DE;2024-03;2,7\nX;M;FR;2024-01;9,9\n"
    )
    frame = parse_sdmx_csv(text)
    assert list(frame["value"]) == [2.5, 2.6, 2.7]
    assert frame["obs_date"].iloc[0] == pd.Timestamp("2024-01-31")


def test_sdmx_csv_rejects_unexpected_content() -> None:
    with pytest.raises(ProviderError):
        parse_sdmx_csv("<html>Fehler</html>\n")
    with pytest.raises(SeriesNotFoundError):
        parse_sdmx_csv("KEY,TIME_PERIOD,OBS_VALUE\n")


def test_sdmx_providers_build_urls_from_templates() -> None:
    csv = "KEY,TIME_PERIOD,OBS_VALUE\nk,2024-01-02,1.5\n"
    http = FakeHttp({"": csv})
    EcbProvider(SourceConfig(), http).fetch_series(SeriesRequest("EXR/D.USD.EUR.SP00.A", "fx"))
    assert http.calls[-1][0] == "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    assert http.calls[-1][1]["format"] == "csvdata"
    OecdProvider(SourceConfig(), http).fetch_series(
        SeriesRequest("OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/CHE.M.IR3TIB.PA._Z._Z._Z._Z.N", "rate")
    )
    assert "DSD_STES@DF_FINMARK,4.0/CHE.M.IR3TIB" in http.calls[-1][0]
    custom = SourceConfig(options={"url_template": "https://example.org/{flow}?k={key}"})
    BundesbankProvider(custom, http).fetch_series(SeriesRequest("BBSIS/M.X", "yield"))
    assert http.calls[-1][0] == "https://example.org/BBSIS?k=M.X"
    with pytest.raises(ProviderError):
        EcbProvider(SourceConfig(), http).fetch_series(SeriesRequest("OHNE_SCHRAEGSTRICH", "fx"))


# ----------------------------------------------------------------------------- Markt


def test_yahoo_uses_adjusted_close_and_strips_timezone() -> None:
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="America/New_York")
    history = pd.DataFrame(
        {"Close": [100.0, 101.0], "Adj Close": [98.0, 99.2], "Dividends": [0.0, 0.0]}, index=index
    )
    seen: list[tuple[str, date | None]] = []

    def downloader(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
        seen.append((symbol, start))
        return history

    frame = YahooProvider(SourceConfig(), downloader=downloader).fetch_series(
        SeriesRequest("VFINX", "price")
    )
    assert list(frame["value"]) == [98.0, 99.2] and list(frame["raw"]) == [100.0, 101.0]
    assert frame["obs_date"].dt.tz is None and seen == [("VFINX", None)]


def test_yahoo_empty_or_failing_download_is_an_error() -> None:
    empty = YahooProvider(SourceConfig(), downloader=lambda s, a, b: pd.DataFrame())
    with pytest.raises(SeriesNotFoundError):
        empty.fetch_series(SeriesRequest("NIX", "price"))

    def boom(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
        raise RuntimeError("Yahoo hat die Seite umgebaut")

    with pytest.raises(ProviderError, match="umgebaut"):
        YahooProvider(SourceConfig(), downloader=boom).fetch_series(SeriesRequest("X", "price"))


def test_tiingo_needs_key_and_parses_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = SourceConfig(api_key_env="TIINGO_API_KEY", requires_key=True)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    with pytest.raises(ProviderDisabledError):
        TiingoProvider(cfg, FakeHttp({})).fetch_series(SeriesRequest("SPY", "price"))
    monkeypatch.setenv("TIINGO_API_KEY", "secret")
    rows = [
        {"date": "2024-01-02T00:00:00.000Z", "close": 470.0, "adjClose": 465.5},
        {"date": "2024-01-03T00:00:00.000Z", "close": 468.0, "adjClose": 463.6},
    ]
    http = FakeHttp({"/SPY/prices": rows})
    frame = TiingoProvider(cfg, http).fetch_series(SeriesRequest("SPY", "price"))
    assert list(frame["value"]) == [465.5, 463.6]
    assert "secret" not in http.calls[0][0], "Der Key gehört in den Header, nicht in die URL"


def test_coinmetrics_follows_pages_and_falls_back_to_second_metric() -> None:
    def answer(url: str, params: dict[str, Any]) -> Any:
        if "page=2" in url:
            return {"data": [{"asset": "btc", "time": "2024-01-02T00:00:00Z", "B": "44000"}]}
        if params.get("metrics") == "A":
            return HttpError("HTTP 403", status=403, body="not in community")
        return {
            "data": [{"asset": "btc", "time": "2024-01-01T00:00:00Z", "B": "42000.5"}],
            "next_page_url": "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?page=2",
        }

    http = FakeHttp({"timeseries/asset-metrics": answer})
    cfg = SourceConfig(options={"metrics": ["A", "B"]})
    frame = CoinMetricsProvider(cfg, http).fetch_series(SeriesRequest("btc", "price"))
    assert list(frame["value"]) == [42000.5, 44000.0]


def test_coinmetrics_prefers_metric_with_full_history() -> None:
    """Im Live-Lauf lieferte die Referenzkurs-Metrik ohne Lizenz nur sieben Tage."""
    long_dates = pd.date_range("2010-07-18", periods=800, freq="D")

    def answer(url: str, params: dict[str, Any]) -> Any:
        if params["metrics"] == "ReferenceRateUSD":
            return {
                "data": [
                    {"time": f"2026-11-1{i}T00:00:00Z", "ReferenceRateUSD": "9"} for i in range(7)
                ]
            }
        return {"data": [{"time": d.isoformat(), "PriceUSD": "1.5"} for d in long_dates]}

    http = FakeHttp({"timeseries/asset-metrics": answer})
    cfg = SourceConfig(options={"metrics": ["ReferenceRateUSD", "PriceUSD"]})
    frame = CoinMetricsProvider(cfg, http).fetch_series(SeriesRequest("btc", "price"))
    assert len(frame) == 800 and frame["value"].iloc[0] == 1.5
    default = CoinMetricsProvider(SourceConfig(), http).fetch_series(SeriesRequest("btc", "price"))
    assert len(default) == 800 and len(http.calls) == 3  # Standard fragt zuerst PriceUSD


def test_paid_providers_refuse_while_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    off = SourceConfig(enabled=False, paid=True, api_key_env="EODHD_API_KEY", requires_key=True)
    for provider in (EodhdProvider(off, FakeHttp({})), SipaProvider(off), MsciProvider(off)):
        assert not provider.available()
        with pytest.raises(ProviderDisabledError):
            provider.fetch_series(SeriesRequest("X", "price"))
    monkeypatch.setenv("EODHD_API_KEY", "abo")
    on = off.model_copy(update={"enabled": True})
    rows = [{"date": "2024-01-02", "close": 10.0, "adjusted_close": 9.5}]
    frame = EodhdProvider(on, FakeHttp({"/api/eod/": rows})).fetch_series(
        SeriesRequest("VFINX.US", "price")
    )
    assert list(frame["value"]) == [9.5]


# ---------------------------------------------------------------------------- Registry


def test_priority_and_subscription_takeover(
    config: AppConfig, demo_paths: ProjectPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ein Abo wird nur per Key und Konfiguration aktiviert und übernimmt dann seine Reihen."""
    monkeypatch.setenv("TIINGO_API_KEY", "t")
    monkeypatch.delenv("EODHD_API_KEY", raising=False)
    real = ProjectPaths(root=demo_paths.root, demo=False)
    symbols = config.universe.assets["equity_us"].segments[0].symbols
    providers = build_providers(config.sources, real)
    assert [name for name, _, _ in rank_providers(symbols, providers)] == ["yfinance", "tiingo"]

    monkeypatch.setenv("EODHD_API_KEY", "abo")
    sources = config.sources.model_copy(deep=True)
    sources.sources["eodhd"].enabled = True
    ranked = rank_providers(symbols, build_providers(sources, real))
    assert [name for name, _, _ in ranked] == ["eodhd", "yfinance", "tiingo"]
    assert ranked[0][2] == "VFINX.US"

    monkeypatch.delenv("TIINGO_API_KEY")
    providers = build_providers(config.sources, real)
    assert [name for name, _, _ in rank_providers(symbols, providers)] == ["yfinance"]
    assert "TIINGO_API_KEY" in providers["tiingo"].unavailable_reason()


def test_demo_mode_never_builds_real_providers(config: AppConfig, demo_paths: ProjectPaths) -> None:
    providers = build_providers(config.sources, demo_paths, demo=True)
    assert providers and all(type(p).__name__ == "DemoProvider" for p in providers.values())
    assert "eodhd" not in providers, "ausgeschaltete Quellen bleiben auch im Demo-Modus aus"
