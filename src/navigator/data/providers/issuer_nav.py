"""NAV-Downloads der ETF-Emittenten als Zweitquelle für EUR-notierte Proxies.

Emittenten wie iShares bieten die NAV-Historie ihrer UCITS-ETFs als Excel/CSV an.
Aus NAV und Ausschüttungen entsteht eine Total-Return-Reihe. Ob eine Seite
automatisch abgerufen werden darf, legt ``automated_access`` in der Konfiguration
fest; ohne ausdrückliche Erlaubnis verwendet der Provider nur manuell abgelegte
Dateien unter ``data/static/issuer_nav/<Fonds>.csv|xls|xlsx``.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from bs4 import BeautifulSoup

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderDisabledError,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)
from navigator.http import HttpClient

DATE_HEADERS = ("as of", "date", "datum", "stand per", "per")
NAV_HEADERS = ("nav per share", "nav pro anteil", "nettoinventarwert", "nav")
DIST_HEADERS = ("ex-dividend", "ex dividend", "ausschüttung", "distribution", "dividend")


def spreadsheetml_rows(content: bytes) -> list[list[str]]:
    """Liest alle Zeilen einer „XML Spreadsheet 2003"-Datei (so liefern Emittenten ``.xls``)."""
    soup = BeautifulSoup(content, "xml")
    rows: list[list[str]] = []
    for row in soup.find_all("Row"):
        rows.append([cell.get_text(strip=True) for cell in row.find_all("Cell")])
    return rows


def _table_rows(content: bytes) -> list[list[str]]:
    """Erkennt das Format am Inhalt (Excel, XML-Tabelle oder CSV) und liefert alle Zeilen."""
    head = content[:200].lstrip().lower()
    if head.startswith(b"<?xml") or b"<workbook" in head:
        return spreadsheetml_rows(content)
    if content[:2] == b"PK" or content[:4] == b"\xd0\xcf\x11\xe0":
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=str)
        rows = []
        for sheet in sheets.values():
            rows.extend(sheet.fillna("").astype(str).to_numpy().tolist())
        return rows
    text = content.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text.strip() else ""
    sep = ";" if first.count(";") > first.count(",") else ","
    return [[c.strip().strip('"') for c in line.split(sep)] for line in text.splitlines()]


def _find(header: list[str], candidates: tuple[str, ...]) -> int | None:
    lowered = [h.strip().lower() for h in header]
    for candidate in candidates:
        for i, name in enumerate(lowered):
            if name == candidate or (len(candidate) > 3 and candidate in name):
                return i
    return None


def _number(text: str) -> float:
    cleaned = text.replace("\xa0", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def parse_nav_table(content: bytes) -> pd.DataFrame:
    """Liest Datum, NAV und Ausschüttung aus einer Emittenten-Datei.

    Liefert ``obs_date``, ``raw`` (NAV) und ``value`` (Total-Return-Index, Ausschüttungen
    am Ex-Tag reinvestiert).
    """
    rows = _table_rows(content)
    for start, header in enumerate(rows):
        date_col = _find(header, DATE_HEADERS)
        nav_col = _find(header, NAV_HEADERS)
        if date_col is None or nav_col is None or date_col == nav_col:
            continue
        dist_col = _find(header, DIST_HEADERS)
        records: list[tuple[pd.Timestamp, float, float]] = []
        for row in rows[start + 1 :]:
            if len(row) <= max(date_col, nav_col):
                continue
            stamp = pd.to_datetime(row[date_col], errors="coerce", dayfirst=True)
            nav = _number(row[nav_col])
            if pd.isna(stamp) or pd.isna(nav) or nav <= 0:
                continue
            dist = _number(row[dist_col]) if dist_col is not None and len(row) > dist_col else 0.0
            records.append((stamp, nav, 0.0 if pd.isna(dist) else dist))
        if len(records) >= 2:
            frame = pd.DataFrame(records, columns=["obs_date", "raw", "dist"])
            frame = frame.drop_duplicates("obs_date").sort_values("obs_date").reset_index(drop=True)
            growth = (frame["raw"] + frame["dist"]) / frame["raw"].shift(1)
            frame["value"] = growth.fillna(1.0).cumprod() * frame["raw"].iloc[0]
            return normalize_frame(frame[["obs_date", "value", "raw"]])
    raise ProviderError("Emittenten-Datei: keine Tabelle mit Datum und NAV gefunden")


class IssuerNavProvider(Provider):
    """Historische NAVs von UCITS-ETFs aus Emittenten-Dateien."""

    name: ClassVar[str] = "issuer_nav"

    def __init__(
        self,
        config: SourceConfig,
        http: HttpClient | None = None,
        static_dir: Path | None = None,
    ) -> None:
        super().__init__(config, http)
        self.static_dir = static_dir or Path("data/static")

    def capabilities(self) -> Capabilities:
        """Zweitquelle für EUR-notierte Proxies."""
        return Capabilities(
            kinds=frozenset({"price"}),
            description="Historische NAVs von UCITS-ETFs (iShares, Xtrackers, Amundi)",
        )

    def _funds(self) -> dict[str, dict[str, Any]]:
        return dict(self.config.options.get("funds", {}))

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Liefert die Total-Return-Reihe eines konfigurierten Fonds."""
        self._require_available()
        funds = self._funds()
        if request.symbol not in funds:
            raise SeriesNotFoundError(f"issuer_nav: Fonds {request.symbol} nicht konfiguriert")
        manual = sorted((self.static_dir / "issuer_nav").glob(f"{request.symbol}.*"))
        if manual:
            frame = parse_nav_table(manual[0].read_bytes())
        else:
            url = str(funds[request.symbol].get("url", ""))
            access = str(self.config.options.get("automated_access", "unknown"))
            if not url or access != "allowed":
                raise ProviderDisabledError(
                    f"issuer_nav: kein erlaubter automatischer Abruf für {request.symbol} "
                    f"(automated_access={access}). NAV-Datei des Emittenten bitte unter "
                    f"{self.static_dir / 'issuer_nav'} als '{request.symbol}.xls' ablegen."
                )
            if not self.http.robots_allowed(url):
                raise ProviderDisabledError(
                    f"issuer_nav: robots.txt erlaubt den Abruf für {request.symbol} nicht"
                )
            content = self.http.get(url, min_interval=self.min_interval).content
            frame = parse_nav_table(content)
        return clip_dates(frame, request.start, request.end)
