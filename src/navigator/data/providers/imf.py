"""IMF DataMapper (frei, ohne Key): Fiskal- und Makrodaten je Land, jährlich.

Symbol: ``<Indikator>/<ISO3>``, z. B. ``d/USA`` (Bruttoverschuldung in % des BIP aus der
Datenbank „Public Finances in Modern History", FPP) oder ``GGXWDG_NGDP/USA`` (dasselbe aus
dem World Economic Outlook, WEO). Jahreswerte erhalten das Datum 31.12. des Jahres.

Der WEO enthält Prognosen. Jahre ab dem laufenden Kalenderjahr werden deshalb verworfen;
die Veröffentlichungsverzögerung regelt die Konfiguration (Jahreswert bekannt ab Ende April
des Folgejahres). Die DataMapper-Schnittstelle liefert nur den jüngsten Datenstand, nicht
frühere Ausgaben; für die Historie ist das eine Näherung (siehe docs/decisions.md).
"""

from __future__ import annotations

from typing import ClassVar

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
from navigator.runlog import utc_now


class ImfProvider(Provider):
    """IMF DataMapper API v1."""

    name: ClassVar[str] = "imf"

    def capabilities(self) -> Capabilities:
        """Jährliche Fiskal- und Makrodaten (FPP, WEO, Fiscal Monitor)."""
        return Capabilities(
            kinds=frozenset({"macro", "level"}),
            description="Staatsverschuldung, Primärsaldo, Zinsen, Einnahmen, Wachstum, Inflation",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt eine Jahresreihe ``Indikator/ISO3``."""
        self._require_available()
        if "/" not in request.symbol:
            raise ProviderError("imf: Symbol muss 'Indikator/ISO3' sein")
        indicator, country = request.symbol.split("/", 1)
        base = str(
            self.config.options.get("api_url", "https://www.imf.org/external/datamapper/api/v1")
        )
        try:
            payload = self.http.get(
                f"{base}/{indicator}/{country}", min_interval=self.min_interval
            ).json()
        except HttpError as exc:
            raise SeriesNotFoundError(f"imf: {request.symbol} nicht abrufbar ({exc})") from exc
        values = payload.get("values", {}).get(indicator, {}).get(country, {})
        if not values:
            raise SeriesNotFoundError(f"imf: keine Werte für {request.symbol}")
        current_year = utc_now().year
        rows = [
            (pd.Timestamp(int(year), 12, 31), value)
            for year, value in values.items()
            if str(year).isdigit() and int(year) < current_year and value is not None
        ]
        frame = pd.DataFrame(rows, columns=["obs_date", "value"])
        out = clip_dates(normalize_frame(frame), request.start, request.end)
        if out.empty:
            raise SeriesNotFoundError(f"imf: keine Werte vor {current_year} für {request.symbol}")
        return out
