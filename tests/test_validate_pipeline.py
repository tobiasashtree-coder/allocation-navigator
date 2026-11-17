"""Prüfungen, Abruf mit Ersatzquelle, Snapshot, Laufprotokoll und Validierungsbericht."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import AppConfig, SourceConfig
from navigator.data.cache import CacheMeta
from navigator.data.pipeline import (
    collect_specs,
    make_providers,
    results_frame,
    run_validation,
    update_data,
)
from navigator.data.pit import PitStore
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderError,
    SeriesRequest,
)
from navigator.data.validate import (
    ValidationReport,
    check_dividends,
    check_gaps,
    check_jumps,
    check_splits,
    check_staleness,
    check_start,
    check_universe,
    cross_check,
    markdown_table,
    summarize_cross_check,
)
from navigator.paths import ProjectPaths


def _prices(n: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n)
    value = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, n)))
    return pd.DataFrame({"obs_date": dates, "value": value, "raw": value})


def test_clean_series_has_no_findings() -> None:
    frame = _prices()
    assert check_gaps(frame, "x") == [] and check_jumps(frame, "x") == []
    assert check_splits(frame, "x") == []


def test_gap_jump_and_split_are_detected() -> None:
    frame = _prices()
    gappy = pd.concat([frame.iloc[:100], frame.iloc[130:]])
    assert "Lücken über 10 Tage: 1" in check_gaps(gappy, "x")[0].message
    jumpy = frame.copy()
    jumpy.loc[300:, "value"] *= 1.4
    assert check_jumps(jumpy, "x")[0].check == "Sprünge"
    split = frame.copy()
    split.loc[300:, "value"] *= 0.5  # 2:1-Split nicht bereinigt
    finding = check_splits(split, "x")[0]
    assert finding.severity == "Fehler" and "Split-Verhältnis" in finding.message


def test_missing_dividends_are_detected_for_distributing_funds() -> None:
    frame = _prices(1300)
    assert check_dividends(frame, "x")[0].check == "Dividenden"  # bereinigt == unbereinigt
    paying = frame.copy()
    paying["raw"] = paying["value"] * np.exp(-np.arange(len(paying)) * 0.0001)[::-1]
    assert check_dividends(paying, "x") == []
    no_raw = frame.drop(columns="raw")
    assert check_dividends(no_raw, "x")[0].severity == "Hinweis"


def test_cross_check_reports_months_above_tolerance() -> None:
    first = _prices()
    second = first.copy()
    assert cross_check(first, second, 0.005).empty
    second.loc[second["obs_date"] >= "2023-06-01", "value"] *= 1.02
    deviations = cross_check(first, second, 0.005)
    assert list(deviations.index.strftime("%Y-%m")) == ["2023-06"]
    finding = summarize_cross_check(deviations, "x", ("yfinance", "tiingo"), 0.005)[0]
    assert "yfinance gegen tiingo: 1 Monate" in finding.message


def test_staleness_start_and_universe_checks() -> None:
    now = datetime(2026, 11, 16, tzinfo=UTC)
    meta = CacheMeta("p", "s", "price", "2026-11-01T00:00:00+00:00", "2000-01-03", "2026-10-01", 9)
    assert "46 Tage alt" in check_staleness(meta, "x", now)[0].message
    meta.stale, meta.error = True, "Timeout"
    assert len(check_staleness(meta, "x", now)) == 2
    # Abgeschlossene Reihen (Backfill, EONIA) werden nicht auf ihr Alter geprüft,
    # ein Quellenausfall aber weiterhin gemeldet.
    assert len(check_staleness(meta, "x", now, historical=True)) == 1
    monthly = pd.DataFrame({"obs_date": pd.date_range("2026-01-31", periods=9, freq="ME")})
    fresh = CacheMeta("p", "s", "yield", "2026-11-01T00:00:00+00:00", "2026-01-31", "2026-09-30", 9)
    assert check_staleness(fresh, "x", now, monthly) == []  # Monatsreihe: 47 Tage sind normal
    assert check_staleness(fresh, "x", now) != []
    assert check_start("2010-07", pd.Timestamp("2026-11-11"), "x")[0].severity == "Warnung"
    assert check_start("2000-01", pd.Timestamp("2000-06-01"), "x") == []
    assert "+60 Monate" in check_start("2000-01", pd.Timestamp("2005-01-03"), "x")[0].message
    index = pd.date_range("2020-01-31", periods=24, freq="ME")
    returns = pd.DataFrame({"a": 0.01, "b": 0.01}, index=index)
    returns.loc[index[5], "b"] = np.nan
    findings = check_universe(returns, ["a", "b", "c"], "EUR")
    assert {(f.scope, f.severity) for f in findings} == {("EUR/b", "Warnung"), ("EUR/c", "Fehler")}


def test_report_renders_markdown_and_html(tmp_path: Path) -> None:
    report = ValidationReport("2026-11-16T12:00:00+00:00", "abc123" * 6, demo=True)
    report.tables["Tabelle"] = pd.DataFrame({"a|b": [1.23456, float("nan")], "t": ["x", "y"]})
    report.notes.append("Hinweistext")
    markdown = report.to_markdown()
    assert "DEMO-DATEN" in markdown and "| 1.235 | x |" in markdown and "a|b" in markdown
    md_path, html_path = report.write(tmp_path)
    assert md_path.exists() and "<table" in html_path.read_text(encoding="utf-8")
    assert markdown_table(pd.DataFrame()) == "_keine Einträge_\n"


# ----------------------------------------------------------------------------- Abruf


class Flaky(Provider):
    """Quelle, die wahlweise ausfällt."""

    def __init__(self, name: str, priority: int, fail: bool) -> None:
        super().__init__(SourceConfig(priority=priority))
        self.name = name  # type: ignore[misc]
        self.fail = fail
        self.calls = 0

    def capabilities(self) -> Capabilities:
        return Capabilities(kinds=frozenset({"price"}))

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        self.calls += 1
        if self.fail:
            raise ProviderError("HTTP 503")
        return _prices(300, seed=1)


def test_spec_collection_covers_everything(config: AppConfig) -> None:
    specs = collect_specs(config)
    keys = [s.key for s in specs]
    assert len(keys) == len(set(keys))
    for prefix in ("asset.equity_us.vfinx", "asset.cash", "fx.USD.per_eur", "rate.EUR.estr"):
        assert any(k.startswith(prefix) for k in keys) or prefix == "asset.cash"
    assert not any(k.startswith("asset.cash") for k in keys), "Cash kommt aus den Kurzfristzinsen"
    indpro = next(s for s in specs if s.key == "indicator.us_indpro")
    assert indpro.vintages and indpro.pit and indpro.lag().months == 1
    vfinx = next(s for s in specs if s.key == "asset.equity_us.vfinx")
    assert vfinx.cross_check and vfinx.expected_start == "1976-08" and not vfinx.historical
    closed = {s.key for s in specs if s.historical}
    assert {"rate.EUR.eonia", "fx.EUR.dem_per_usd", "asset.equity_us.french_us_market"} <= closed
    assert "rate.EUR.estr" not in closed and "rate.CHF.ch_3m_interbank" not in closed


def test_fallback_to_second_source_is_reported(config: AppConfig, demo_paths: ProjectPaths) -> None:
    """Fällt die Erstquelle aus, greift die Zweitquelle; das Ergebnis vermerkt es."""
    providers: dict[str, Provider] = {
        "yfinance": Flaky("yfinance", 20, fail=True),
        "tiingo": Flaky("tiingo", 30, fail=False),
    }
    results = update_data(
        config, demo_paths, providers=providers, only="asset.equity_us.vfinx", snapshot=False
    )
    main = next(r for r in results if r.key == "asset.equity_us.vfinx")
    assert (main.status, main.provider) == ("ersatzquelle", "tiingo")
    assert "yfinance: HTTP 503" in main.message
    assert results_frame(results).loc[0, "rows"] == 300


def test_no_usable_source_fails_loudly(config: AppConfig, demo_paths: ProjectPaths) -> None:
    providers: dict[str, Provider] = {"yfinance": Flaky("yfinance", 20, fail=True)}
    results = update_data(
        config, demo_paths, providers=providers, only="asset.equity_japan.ewj", snapshot=False
    )
    assert results[0].status == "fehlgeschlagen" and "HTTP 503" in results[0].message
    static_only = update_data(
        config, demo_paths, providers=providers, only="asset.reits.nareit", snapshot=False
    )
    assert "keine nutzbare Quelle" in static_only[0].message


def test_update_writes_pit_store_snapshot_and_run_log(
    config: AppConfig, demo_project: ProjectPaths
) -> None:
    pit = PitStore(demo_project.pit)
    indpro = pit.load("indicator.us_indpro")
    assert indpro is not None and indpro.revision_count() > 0  # Demo liefert Vintages
    lagged = pit.load("indicator.us_cli")
    assert lagged is not None and lagged.frame["approx"].all()
    # Verzögerungsregel: Der Septemberwert ist Ende Oktober noch nicht bekannt (Lag 2 Monate).
    assert lagged.as_of("2026-10-31").index.max() == pd.Timestamp("2026-08-31")
    snapshots = sorted(demo_project.snapshots.iterdir())
    manifest = json.loads((snapshots[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_hash"] == config.config_hash and manifest["demo"] is True
    assert len(manifest["files"]) > 150 and all(len(v) == 64 for v in manifest["files"].values())
    runs = (demo_project.runs / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(runs[0])
    assert entry["command"] == "data update" and entry["config_hash"] == config.config_hash
    assert entry["summary"]["fehlgeschlagen"] == 0


def test_second_update_uses_cache(config: AppConfig, demo_project: ProjectPaths) -> None:
    providers = make_providers(config, demo_project)
    calls = {"n": 0}
    for provider in providers.values():
        original = provider.fetch_series

        def counted(request: SeriesRequest, _original=original) -> pd.DataFrame:  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return _original(request)

        provider.fetch_series = counted  # type: ignore[method-assign]
    update_data(config, demo_project, providers=providers, snapshot=False)
    assert calls["n"] == 0, "frische Reihen dürfen nicht erneut abgerufen werden"


def test_validation_report_on_demo_data(config: AppConfig, demo_project: ProjectPaths) -> None:
    report = run_validation(config, demo_project)
    assert report.demo and report.count("Fehler") == 0
    assert "EUR: 18/18, USD: 18/18, CHF: 18/18, GBP: 18/18" in report.notes[0]
    for title in (
        "Universum in EUR",
        "Universum in GBP",
        "Point-in-Time-Speicher (Makroreihen)",
        "Quellen",
        "Rohreihen je Quelle",
        "Synthetische Reihen gegen Fonds",
    ):
        assert title in report.tables, title
    sources = report.tables["Quellen"].set_index("Quelle")
    assert sources.loc["eodhd", "eingeschaltet"] == "nein"
    assert len(report.tables["Universum in EUR"]) == 18


def test_missing_data_is_an_error_not_silence(config: AppConfig, demo_paths: ProjectPaths) -> None:
    report = run_validation(config, demo_paths)  # leerer Cache
    assert report.count("Fehler") > 50
    assert any(f.check == "Abdeckung" and f.scope == "EUR/equity_us" for f in report.findings)
    with pytest.raises(AssertionError):
        assert report.count("Fehler") == 0
