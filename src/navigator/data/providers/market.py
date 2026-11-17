"""Marktdaten: Yahoo Finance (yfinance), Tiingo, Coin Metrics und EODHD.

Alle liefern Tageskurse mit ``value`` = bereinigter Schlusskurs (Total Return) und,
wo vorhanden, ``raw`` = unbereinigter Schlusskurs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)
from navigator.http import HttpClient, HttpError

log = logging.getLogger(__name__)

Downloader = Callable[[str, date | None, date | None], pd.DataFrame]


def _yfinance_download(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
    """Standard-Abruf über die Bibliothek yfinance (inoffizielle Schnittstelle)."""
    import yfinance as yf  # spät importiert: Tests und Demo-Modus brauchen yfinance nicht

    ticker = yf.Ticker(symbol)
    kwargs: dict[str, Any] = {"interval": "1d", "auto_adjust": False, "actions": True}
    if start is None:
        kwargs["period"] = "max"
    else:
        kwargs["start"] = start.isoformat()
    if end is not None:
        kwargs["end"] = (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat()
    return ticker.history(**kwargs)


class YahooProvider(Provider):
    """Yahoo Finance über yfinance: Primärquelle für Kurse von ETFs, Fonds, Indizes, Futures."""

    name: ClassVar[str] = "yfinance"

    def __init__(
        self,
        config: SourceConfig,
        http: HttpClient | None = None,
        downloader: Downloader | None = None,
    ) -> None:
        super().__init__(config, http)
        self._download = downloader or _yfinance_download

    def capabilities(self) -> Capabilities:
        """Bereinigte Tageskurse, auch UCITS-Notierungen (.DE, .L)."""
        return Capabilities(
            kinds=frozenset({"price", "level"}),
            description="Bereinigte Kurse von ETFs, Fonds, Indizes, Futures (inoffiziell)",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt Tageskurse; ``value`` = Adj Close, ``raw`` = Close."""
        self._require_available()
        try:
            history = self._download(request.symbol, request.start, request.end)
        except Exception as exc:  # yfinance wirft je nach Version unterschiedliche Fehler
            raise ProviderError(f"yfinance: Abruf von {request.symbol} gescheitert: {exc}") from exc
        if history is None or len(history) == 0 or "Close" not in history.columns:
            raise SeriesNotFoundError(f"yfinance: keine Kurse für {request.symbol}")
        index = pd.DatetimeIndex(history.index)
        if index.tz is not None:
            index = index.tz_localize(None)
        adjusted = history["Adj Close"] if "Adj Close" in history.columns else history["Close"]
        frame = pd.DataFrame(
            {
                "obs_date": index.normalize(),
                "value": adjusted.to_numpy(),
                "raw": history["Close"].to_numpy(),
            }
        )
        out = clip_dates(normalize_frame(frame), request.start, request.end)
        if out.empty:
            raise SeriesNotFoundError(f"yfinance: keine Kurse für {request.symbol}")
        return out


class TiingoProvider(Provider):
    """Tiingo: dividendenbereinigte Kurse von US-Aktien, ETFs und Investmentfonds."""

    name: ClassVar[str] = "tiingo"

    def capabilities(self) -> Capabilities:
        """Zweitquelle für US-Proxies."""
        return Capabilities(
            kinds=frozenset({"price"}),
            needs_key=True,
            description="US-Aktien, ETFs, Investmentfonds, dividendenbereinigt",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt Tageskurse; ``value`` = adjClose, ``raw`` = close."""
        self._require_available()
        base = str(self.config.options.get("api_url", "https://api.tiingo.com/tiingo/daily"))
        params: dict[str, Any] = {
            "format": "json",
            "resampleFreq": "daily",
            "startDate": (request.start or date(1960, 1, 1)).isoformat(),
        }
        if request.end is not None:
            params["endDate"] = request.end.isoformat()
        try:
            rows = self.http.get(
                f"{base}/{request.symbol}/prices",
                params=params,
                headers={"Authorization": f"Token {self.api_key}"},
                min_interval=self.min_interval,
            ).json()
        except HttpError as exc:
            if exc.status == 404:
                raise SeriesNotFoundError(f"tiingo: {request.symbol} unbekannt") from exc
            raise
        if not isinstance(rows, list) or not rows:
            raise SeriesNotFoundError(f"tiingo: keine Kurse für {request.symbol}")
        frame = pd.DataFrame(
            {
                "obs_date": [str(r["date"])[:10] for r in rows],
                "value": [r.get("adjClose") for r in rows],
                "raw": [r.get("close") for r in rows],
            }
        )
        return clip_dates(normalize_frame(frame), request.start, request.end)


class CoinMetricsProvider(Provider):
    """Coin Metrics Community API: Referenzkurse für Bitcoin mit voller Tageshistorie."""

    name: ClassVar[str] = "coinmetrics"

    def capabilities(self) -> Capabilities:
        """Primärquelle für Bitcoin."""
        return Capabilities(
            kinds=frozenset({"price"}),
            description="Bitcoin-Referenzkurse (Community-Daten, ohne Key)",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt Tageskurse eines Assets (z. B. ``btc``) in USD."""
        self._require_available()
        base = str(self.config.options.get("api_url", "https://community-api.coinmetrics.io/v4"))
        metrics = list(self.config.options.get("metrics", ["ReferenceRateUSD", "PriceUSD"]))
        last_error: Exception | None = None
        for metric in metrics:
            try:
                rows = self._fetch_metric(base, request, metric)
            except HttpError as exc:
                last_error = exc
                log.warning("coinmetrics: Metrik %s nicht abrufbar (%s)", metric, exc)
                continue
            if rows:
                frame = pd.DataFrame(
                    {
                        "obs_date": [str(r["time"])[:10] for r in rows],
                        "value": [r.get(metric) for r in rows],
                    }
                )
                return clip_dates(normalize_frame(frame), request.start, request.end)
        raise SeriesNotFoundError(f"coinmetrics: keine Kurse für {request.symbol} ({last_error})")

    def _fetch_metric(self, base: str, request: SeriesRequest, metric: str) -> list[dict[str, Any]]:
        params: dict[str, Any] | None = {
            "assets": request.symbol,
            "metrics": metric,
            "frequency": "1d",
            "page_size": 10_000,
            "paging_from": "start",
        }
        assert params is not None
        if request.start is not None:
            params["start_time"] = request.start.isoformat()
        if request.end is not None:
            params["end_time"] = request.end.isoformat()
        url: str | None = f"{base}/timeseries/asset-metrics"
        rows: list[dict[str, Any]] = []
        while url:
            payload = self.http.get(url, params=params, min_interval=self.min_interval).json()
            rows.extend(payload.get("data", []))
            url = payload.get("next_page_url")
            params = None  # die Folgeseite trägt alle Parameter in der URL
        return rows


class EodhdProvider(Provider):
    """EODHD (kostenpflichtig): vorbereitet, standardmäßig deaktiviert."""

    name: ClassVar[str] = "eodhd"

    def capabilities(self) -> Capabilities:
        """Weltweite Kurse und Indizes; nur mit Abo."""
        return Capabilities(
            kinds=frozenset({"price", "level"}),
            needs_key=True,
            description="Weltweite Kurse und Indizes (Abo erforderlich)",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt Tageskurse; ``value`` = adjusted_close, ``raw`` = close."""
        self._require_available()
        base = str(self.config.options.get("api_url", "https://eodhd.com/api/eod"))
        params: dict[str, Any] = {"api_token": self.api_key, "fmt": "json", "period": "d"}
        if request.start is not None:
            params["from"] = request.start.isoformat()
        if request.end is not None:
            params["to"] = request.end.isoformat()
        rows = self.http.get(
            f"{base}/{request.symbol}", params=params, min_interval=self.min_interval
        ).json()
        if not isinstance(rows, list) or not rows:
            raise SeriesNotFoundError(f"eodhd: keine Kurse für {request.symbol}")
        frame = pd.DataFrame(
            {
                "obs_date": [r["date"] for r in rows],
                "value": [r.get("adjusted_close") for r in rows],
                "raw": [r.get("close") for r in rows],
            }
        )
        return clip_dates(normalize_frame(frame), request.start, request.end)
