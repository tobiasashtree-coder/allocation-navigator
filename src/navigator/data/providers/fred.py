"""FRED und ALFRED (Federal Reserve Bank of St. Louis).

ALFRED liefert Datenstände zu früheren Zeitpunkten (Vintages): zu jedem Wert das
Datum, ab dem er öffentlich bekannt war. Das ist die Grundlage der
Point-in-Time-Korrektheit für US-Makrodaten.
"""

from __future__ import annotations

import io
import logging
from typing import Any, ClassVar

import pandas as pd

from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)
from navigator.http import HttpError

log = logging.getLogger(__name__)

REALTIME_MIN = "1776-07-04"
REALTIME_MAX = "9999-12-31"
PAGE_LIMIT = 100_000
VINTAGE_CHUNK = 1500


class FredProvider(Provider):
    """Zugriff auf FRED (aktueller Stand) und ALFRED (alle Vintages)."""

    name: ClassVar[str] = "fred"

    def capabilities(self) -> Capabilities:
        """US-Makro, Renditen, Spreads, Wechselkurse; mit Vintages."""
        return Capabilities(
            kinds=frozenset({"macro", "yield", "rate", "fx", "level"}),
            vintages=True,
            needs_key=False,
            description="US-Makro, Renditen, Spreads, Inflationserwartungen; Vintages über ALFRED",
        )

    # ------------------------------------------------------------------ Abruf
    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt eine FRED-Reihe; mit ``vintages=True`` alle Datenstände."""
        self._require_available()
        if self.api_key is None:
            if request.vintages:
                raise ProviderError(
                    f"fred: Vintages für {request.symbol} brauchen einen API-Key (FRED_API_KEY)"
                )
            log.warning(
                "fred: kein API-Key gesetzt, lade %s über den CSV-Abruf ohne Vintages",
                request.symbol,
            )
            return self._fetch_csv(request)
        if request.vintages:
            return self._fetch_vintages(request)
        rows = self._observations(request, {})
        frame = pd.DataFrame(
            {"obs_date": [r["date"] for r in rows], "value": [_num(r["value"]) for r in rows]}
        )
        return self._finish(frame, request)

    def _finish(self, frame: pd.DataFrame, request: SeriesRequest) -> pd.DataFrame:
        out = clip_dates(normalize_frame(frame), request.start, request.end)
        if out.empty:
            raise SeriesNotFoundError(f"fred: keine Werte für {request.symbol}")
        return out

    def _observations(self, request: SeriesRequest, extra: dict[str, Any]) -> list[dict[str, Any]]:
        base = str(self.config.options.get("api_url", "https://api.stlouisfed.org/fred"))
        params: dict[str, Any] = {
            "series_id": request.symbol,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "asc",
            "limit": PAGE_LIMIT,
            **extra,
        }
        if request.start is not None:
            params["observation_start"] = request.start.isoformat()
        if request.end is not None:
            params["observation_end"] = request.end.isoformat()
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            params["offset"] = offset
            payload = self.http.get(
                f"{base}/series/observations", params=params, min_interval=self.min_interval
            ).json()
            page = payload.get("observations", [])
            rows.extend(page)
            offset += len(page)
            if len(page) < PAGE_LIMIT or offset >= int(payload.get("count", offset)):
                return rows

    def _fetch_vintages(self, request: SeriesRequest) -> pd.DataFrame:
        try:
            rows = self._observations(
                request, {"realtime_start": REALTIME_MIN, "realtime_end": REALTIME_MAX}
            )
        except HttpError as exc:
            if exc.status != 400 or "vintage" not in exc.body.lower():
                raise
            log.info("fred: %s hat zu viele Vintages, lade in Abschnitten", request.symbol)
            rows = self._vintages_chunked(request)
        frame = pd.DataFrame(
            {
                "obs_date": [r["date"] for r in rows],
                "value": [_num(r["value"]) for r in rows],
                "known_from": [r["realtime_start"] for r in rows],
            }
        )
        out = self._finish(frame, request)
        return collapse_vintages(out)

    def _vintages_chunked(self, request: SeriesRequest) -> list[dict[str, Any]]:
        base = str(self.config.options.get("api_url", "https://api.stlouisfed.org/fred"))
        dates: list[str] = []
        offset = 0
        while True:
            payload = self.http.get(
                f"{base}/series/vintagedates",
                params={
                    "series_id": request.symbol,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "limit": 10_000,
                    "offset": offset,
                },
                min_interval=self.min_interval,
            ).json()
            page = payload.get("vintage_dates", [])
            dates.extend(page)
            offset += len(page)
            if len(page) < 10_000:
                break
        rows: list[dict[str, Any]] = []
        for i in range(0, len(dates), VINTAGE_CHUNK):
            chunk = dates[i : i + VINTAGE_CHUNK]
            rows.extend(
                self._observations(request, {"realtime_start": chunk[0], "realtime_end": chunk[-1]})
            )
        return rows

    def _fetch_csv(self, request: SeriesRequest) -> pd.DataFrame:
        url = str(
            self.config.options.get("csv_url", "https://fred.stlouisfed.org/graph/fredgraph.csv")
        )
        params: dict[str, Any] = {"id": request.symbol}
        if request.start is not None:
            params["cosd"] = request.start.isoformat()
        text = self.http.get(url, params=params, min_interval=self.min_interval).text
        table = pd.read_csv(io.StringIO(text), dtype=str)
        if table.shape[1] < 2:
            raise SeriesNotFoundError(f"fred: unerwartetes CSV-Format für {request.symbol}")
        frame = pd.DataFrame(
            {"obs_date": table.iloc[:, 0], "value": [_num(v) for v in table.iloc[:, 1]]}
        )
        return self._finish(frame, request)


def _num(value: Any) -> float:
    """FRED kennzeichnet fehlende Werte mit einem Punkt."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def collapse_vintages(frame: pd.DataFrame) -> pd.DataFrame:
    """Behält je Beobachtung nur Datenstände, die den Wert tatsächlich ändern (Revisionen)."""
    ordered = frame.sort_values(["obs_date", "known_from"]).reset_index(drop=True)
    previous = ordered.groupby("obs_date")["value"].shift(1)
    changed = previous.isna() | (ordered["value"] != previous)
    return ordered[changed].reset_index(drop=True)
