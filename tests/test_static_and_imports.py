"""Statische Datensätze, Emittenten-NAVs und Eckwerte privater Infrastruktur."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    ProviderDisabledError,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
)
from navigator.data.providers.issuer_nav import IssuerNavProvider, parse_nav_table
from navigator.data.providers.private_infra import (
    PrivateInfraProvider,
    PrivateInfraStore,
    geltner_unsmooth,
    parse_infra300,
    parse_msci_results,
    parse_nav_per_share,
)
from navigator.data.providers.static import (
    StaticProvider,
    looks_like_level,
    parse_french_csv,
    parse_french_dat,
    pick_column,
)
from navigator.http import HttpError
from tests.conftest import FakeHttp

FRENCH_CSV = """This file was created by CMPT_ME_BEME_RETS using the 202609 CRSP database.
The 1-month TBill return is from Ibbotson and Associates, Inc.

,Mkt-RF,SMB,HML,RF
192607,    2.96,   -2.56,   -2.43,    0.22
192608,    2.64,   -1.17,    3.82,    0.25
192609,  -99.99,   -1.40,    0.13,    0.23

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
  1927,   29.47,   -2.04,   -4.54,    3.12
"""

FRENCH_DAT = """  Value-Weight Dollar Returns: All 4 Data Items Required
            --B/M--   --E/P--
     Mkt    High Low  High Low
197501   14.20  15.1 13.9 16.0 12.5
197502    5.31   6.0  4.9  7.1  4.2

  Annual
1975   30.1  35.2 28.0 36.1 27.5
"""


def _zip(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def test_french_csv_first_monthly_table_and_missing_codes() -> None:
    table = parse_french_csv(FRENCH_CSV)
    assert list(table.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert list(table.index) == list(pd.to_datetime(["1926-07-31", "1926-08-31", "1926-09-30"]))
    assert np.isnan(table.loc["1926-09-30", "Mkt-RF"])
    market = pick_column(table, "Mkt-RF+RF")
    assert market.iloc[0] == pytest.approx(3.18)


def test_french_dat_market_is_first_value_column() -> None:
    table = parse_french_dat(FRENCH_DAT)
    assert list(table["Mkt"]) == [14.20, 5.31]
    assert table.index[0] == pd.Timestamp("1975-01-31")


def test_pick_column_requires_unique_match() -> None:
    table = pd.DataFrame({"TSMOM": [1.0], "TSMOM^EQ": [2.0], "Other": [3.0]})
    assert pick_column(table, "tsmom").iloc[0] == 1.0  # exakter Treffer hat Vorrang
    with pytest.raises(SeriesNotFoundError):
        pick_column(table, "TSM")
    with pytest.raises(SeriesNotFoundError):
        pick_column(table, "fehlt")


def test_static_provider_downloads_once_and_scales_percent(tmp_path: Path) -> None:
    cfg = SourceConfig(
        options={
            "datasets": {
                "french_us_factors": {
                    "url": "https://example.org/F-F_Research_Data_Factors_CSV.zip",
                    "format": "french_csv",
                    "scale": 0.01,
                }
            }
        }
    )
    http = FakeHttp({"F-F_Research": _zip("F-F_Research_Data_Factors.CSV", FRENCH_CSV)})
    provider = StaticProvider(cfg, http, tmp_path)
    frame = provider.fetch_series(SeriesRequest("french_us_factors:Mkt-RF+RF", "returns"))
    assert list(frame["value"].round(4)) == [0.0318, 0.0289]
    StaticProvider(cfg, http, tmp_path).fetch_series(
        SeriesRequest("french_us_factors:SMB", "returns")
    )
    assert len(http.calls) == 1, "frische Datei wird nicht erneut geladen"


def test_static_provider_explains_manual_fallback(tmp_path: Path) -> None:
    cfg = SourceConfig(
        options={
            "datasets": {"aqr_tsmom": {"url": "https://example.org/t.xlsx", "format": "excel"}}
        }
    )
    http = FakeHttp({"t.xlsx": HttpError("HTTP 403", status=403)})
    with pytest.raises(ProviderError, match="von Hand"):
        StaticProvider(cfg, http, tmp_path).fetch_series(
            SeriesRequest("aqr_tsmom:TSMOM", "returns")
        )
    # Manuell abgelegte Datei hat Vorrang vor dem Download.
    sheet = pd.DataFrame(
        [["AQR", None, None]] * 2
        + [["Date", "TSMOM", "TSMOM^EQ"], ["01/31/1985", 0.02, 0.01], ["02/28/1985", -0.01, 0.0]]
    )
    manual = tmp_path / "manual"
    manual.mkdir()
    sheet.to_excel(manual / "aqr_tsmom.xlsx", header=False, index=False)
    cfg.options["datasets"]["aqr_tsmom"]["skiprows"] = 2
    frame = StaticProvider(cfg, http, tmp_path).fetch_series(
        SeriesRequest("aqr_tsmom:TSMOM", "returns")
    )
    assert list(frame["value"]) == [0.02, -0.01]
    assert frame["obs_date"].iloc[1] == pd.Timestamp("1985-02-28")


def test_static_positional_excel_detects_index_levels(tmp_path: Path) -> None:
    rows = [["Kopf"] * 3] * 3 + [
        [pd.Timestamp("1972-01-31"), 1.0, 100.0],
        [pd.Timestamp("1972-02-29"), 2.0, 102.0],
        [pd.Timestamp("1972-03-31"), 3.0, 99.96],
    ]
    manual = tmp_path / "manual"
    manual.mkdir()
    pd.DataFrame(rows).to_excel(manual / "nareit.xlsx", header=False, index=False)
    cfg = SourceConfig(
        options={
            "datasets": {
                "nareit": {
                    "format": "excel_positional",
                    "skiprows": 3,
                    "columns": {"all_equity": 2},
                    "value_type": "auto",
                }
            }
        }
    )
    frame = StaticProvider(cfg, FakeHttp({}), tmp_path).fetch_series(
        SeriesRequest("nareit:all_equity", "returns")
    )
    assert list(frame["value"].round(4)) == [0.02, -0.02]
    assert not looks_like_level(pd.Series([1.2, -0.8, 2.1, -3.0]))


def test_manual_csv_reports_missing_file(tmp_path: Path) -> None:
    cfg = SourceConfig(
        options={"datasets": {"gold_manual": {"format": "manual_csv", "value_type": "level"}}}
    )
    provider = StaticProvider(cfg, FakeHttp({}), tmp_path)
    with pytest.raises(SeriesNotFoundError, match="manuelle Datei fehlt"):
        provider.fetch_series(SeriesRequest("gold_manual:USD", "level"))
    (tmp_path / "manual").mkdir()
    (tmp_path / "manual" / "gold_manual.csv").write_text(
        "Datum;USD\n1978-01-31;175,75\n1978-02-28;182,25\n", encoding="utf-8"
    )
    with pytest.raises(SeriesNotFoundError):  # deutsche Dezimalkommas werden nicht erraten
        StaticProvider(cfg, FakeHttp({}), tmp_path).fetch_series(
            SeriesRequest("gold_manual:USD", "level")
        )
    (tmp_path / "manual" / "gold_manual.csv").write_text(
        "date,USD\n1978-01-31,175.75\n1978-02-28,182.25\n", encoding="utf-8"
    )
    frame = StaticProvider(cfg, FakeHttp({}), tmp_path).fetch_series(
        SeriesRequest("gold_manual:USD", "level")
    )
    assert list(frame["value"]) == [175.75, 182.25]


# ----------------------------------------------------------------------- Emittenten-NAV

NAV_CSV = "As Of,NAV per Share,Ex-Dividends\n02/Jan/2024,100.00,\n03/Jan/2024,99.00,2.00\n04/Jan/2024,99.99,\n"
NAV_XML = """<?xml version="1.0"?><ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<ss:Worksheet ss:Name="Historisch"><ss:Table>
<ss:Row><ss:Cell><ss:Data>Stand per</ss:Data></ss:Cell><ss:Cell><ss:Data>NAV pro Anteil</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data>02.01.2024</ss:Data></ss:Cell><ss:Cell><ss:Data>141,50</ss:Data></ss:Cell></ss:Row>
<ss:Row><ss:Cell><ss:Data>03.01.2024</ss:Data></ss:Cell><ss:Cell><ss:Data>141,64</ss:Data></ss:Cell></ss:Row>
</ss:Table></ss:Worksheet></ss:Workbook>"""


def test_nav_table_reinvests_distributions() -> None:
    frame = parse_nav_table(NAV_CSV.encode())
    assert list(frame["raw"]) == [100.0, 99.0, 99.99]
    returns = frame["value"].pct_change().dropna()
    assert returns.iloc[0] == pytest.approx(0.01)  # (99 + 2) / 100 - 1
    assert returns.iloc[1] == pytest.approx(0.01)


def test_nav_table_reads_spreadsheetml_with_german_headers() -> None:
    frame = parse_nav_table(NAV_XML.encode())
    assert list(frame["raw"]) == [141.50, 141.64]
    assert frame["obs_date"].iloc[0] == pd.Timestamp("2024-01-02")
    with pytest.raises(ProviderError):
        parse_nav_table(b"irgendwas,ohne\n1,2\n")


def test_issuer_nav_requires_permission_or_manual_file(tmp_path: Path) -> None:
    cfg = SourceConfig(
        options={"automated_access": "unknown", "funds": {"fonds": {"url": "https://x.org/nav"}}}
    )
    http = FakeHttp({"x.org": NAV_CSV})
    with pytest.raises(ProviderDisabledError, match="ablegen"):
        IssuerNavProvider(cfg, http, tmp_path).fetch_series(SeriesRequest("fonds", "price"))
    assert http.calls == [], "ohne Erlaubnis wird die Seite nicht abgerufen"
    (tmp_path / "issuer_nav").mkdir()
    (tmp_path / "issuer_nav" / "fonds.csv").write_text(NAV_CSV, encoding="utf-8")
    frame = IssuerNavProvider(cfg, http, tmp_path).fetch_series(SeriesRequest("fonds", "price"))
    assert len(frame) == 3 and http.calls == []
    allowed = SourceConfig(
        options={"automated_access": "allowed", "funds": {"f2": {"url": "https://x.org/nav"}}}
    )
    assert len(IssuerNavProvider(allowed, http, tmp_path).fetch_series(SeriesRequest("f2"))) == 3
    blocked = FakeHttp({"x.org": NAV_CSV}, robots=False)
    with pytest.raises(ProviderDisabledError, match="robots"):
        IssuerNavProvider(allowed, blocked, tmp_path).fetch_series(SeriesRequest("f2"))


# ------------------------------------------------------------- private Infrastruktur


def test_parsers_find_published_key_values() -> None:
    msci = parse_msci_results(
        "MSCI Global Quarterly Private Infrastructure Asset Index Q1 2026 results: "
        "The index posted a 12-month total return of 8.4% and a quarterly return of 1.9%."
    )
    assert {(c.unit, c.value, c.period) for c in msci} == {
        ("pct_12m", 8.4, "2026-Q1"),
        ("pct_quarter", 1.9, "2026-Q1"),
    }
    infra = parse_infra300("The infra300 index returned 1.25% in September 2026, its best month.")
    assert [(c.period, c.value, c.unit) for c in infra] == [("2026-09", 1.25, "pct_month")]
    nav = parse_nav_per_share(
        "As at 30 September 2026 the unaudited NAV per ordinary share was 153.3p."
    )
    assert [(c.period, c.value, c.unit) for c in nav] == [("2026-09", 153.3, "pence")]
    assert parse_msci_results("Kein Wert in diesem Text.") == []


def test_values_are_used_only_after_confirmation(tmp_path: Path) -> None:
    store = PrivateInfraStore(tmp_path / "infra.json")
    entry = store.add("msci_private_infra_12m", "2026-Q1", 8.4, "pct_12m", "https://msci.example")
    assert entry is not None and entry.status == "pending"
    assert store.add("msci_private_infra_12m", "2026-Q1", 8.4, "pct_12m", "x") is None
    provider = PrivateInfraProvider(SourceConfig(), store_path=tmp_path / "infra.json")
    with pytest.raises(SeriesNotFoundError):
        provider.fetch_series(SeriesRequest("msci_private_infra_12m", "returns"))
    store.set_status(entry.id, "confirmed")
    frame = provider.fetch_series(SeriesRequest("msci_private_infra_12m", "returns"))
    assert frame["obs_date"].iloc[0] == pd.Timestamp("2026-03-31") and frame["value"].iloc[0] == 8.4
    with pytest.raises(KeyError):
        store.set_status("9999", "confirmed")


def test_import_creates_reminder_unless_access_is_allowed(tmp_path: Path) -> None:
    page = {"series": "infra300_monthly", "url": "https://news.example/infra300"}
    html = "<html><body><p>infra300 returned 1.25% in September 2026.</p></body></html>"
    http = FakeHttp({"news.example": html})
    cfg = SourceConfig(options={"pages": {"infra300": {**page, "automated_access": "unknown"}}})
    provider = PrivateInfraProvider(cfg, http, tmp_path / "a.json")
    assert "Erinnerung" in provider.import_published()[0]
    assert http.calls == [] and provider.store.load()[0].status == "reminder"

    cfg = SourceConfig(options={"pages": {"infra300": {**page, "automated_access": "allowed"}}})
    blocked = PrivateInfraProvider(
        cfg, FakeHttp({"news.example": html}, robots=False), tmp_path / "b.json"
    )
    assert "robots.txt" in blocked.import_published()[0]

    allowed = PrivateInfraProvider(cfg, http, tmp_path / "c.json")
    assert "1 neue Werte" in allowed.import_published()[0]
    value = allowed.store.load()[0]
    assert (value.status, value.period, value.value) == ("pending", "2026-09", 1.25)
    assert value.source_url == page["url"] and value.fetched_at


def test_geltner_unsmoothing_restores_volatility() -> None:
    rng = np.random.default_rng(1)
    true = pd.Series(rng.normal(0.02, 0.05, 400))
    smoothed = true.copy()
    for i in range(1, len(true)):
        smoothed.iloc[i] = 0.6 * smoothed.iloc[i - 1] + 0.4 * true.iloc[i]
    restored = geltner_unsmooth(smoothed, rho=0.6)
    assert restored.std() == pytest.approx(true.iloc[1:].std(), rel=1e-6)
    assert smoothed.std() < 0.7 * true.std()
    assert geltner_unsmooth(smoothed).std() > 1.5 * smoothed.std()
