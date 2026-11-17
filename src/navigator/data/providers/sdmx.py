"""SDMX-Quellen über ihre CSV-Schnittstellen: EZB, Eurostat, OECD, BIS, Bundesbank.

Alle fünf liefern SDMX-CSV mit den Spalten ``TIME_PERIOD`` und ``OBS_VALUE``. Ein
Symbol hat die Form ``<Datenfluss>/<Schlüssel>``, z. B. ``EXR/D.USD.EUR.SP00.A``.
Die URL-Vorlagen stehen in ``config/sources.yaml`` und lassen sich dort ohne
Codeänderung anpassen.
"""

from __future__ import annotations

import io
import logging
import re
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

log = logging.getLogger(__name__)

_NON_DIMENSION = {
    "STRUCTURE",
    "STRUCTURE_ID",
    "STRUCTURE_NAME",
    "ACTION",
    "DATAFLOW",
    "LAST UPDATE",
}


def period_end(period: str) -> pd.Timestamp:
    """Wandelt eine SDMX-Zeitangabe in das Datum des Periodenendes um."""
    text = period.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", text):
        return pd.Timestamp(text[:10])
    if match := re.fullmatch(r"(\d{4})-M?(\d{2})", text):
        return pd.Timestamp(int(match[1]), int(match[2]), 1) + pd.offsets.MonthEnd(0)
    if match := re.fullmatch(r"(\d{4})-?Q([1-4])", text):
        return pd.Timestamp(int(match[1]), int(match[2]) * 3, 1) + pd.offsets.MonthEnd(0)
    if match := re.fullmatch(r"(\d{4})-?[SHB]([12])", text):
        return pd.Timestamp(int(match[1]), int(match[2]) * 6, 1) + pd.offsets.MonthEnd(0)
    if match := re.fullmatch(r"(\d{4})-W(\d{2})", text):
        return pd.Timestamp.fromisocalendar(int(match[1]), int(match[2]), 7)
    if match := re.fullmatch(r"(\d{4})", text):
        return pd.Timestamp(int(match[1]), 12, 31)
    raise ValueError(f"Unbekanntes SDMX-Zeitformat: {period!r}")


def parse_sdmx_csv(text: str) -> pd.DataFrame:
    """Liest SDMX-CSV und liefert genau eine Reihe (``obs_date``, ``value``).

    Enthält die Antwort mehrere Reihen (z. B. wegen Platzhaltern im Schlüssel), wird
    die mit den meisten Beobachtungen gewählt und eine Warnung protokolliert.
    """
    stripped = text.lstrip("﻿ \r\n")
    if not stripped:
        raise SeriesNotFoundError("leere SDMX-Antwort")
    header = stripped.splitlines()[0]
    sep = ";" if header.count(";") > header.count(",") else ","
    table = pd.read_csv(io.StringIO(stripped), sep=sep, dtype=str, keep_default_na=False)
    upper = {c: c.strip().upper() for c in table.columns}
    table = table.rename(columns=upper)
    if "TIME_PERIOD" not in table.columns or "OBS_VALUE" not in table.columns:
        raise ProviderError(f"SDMX-CSV ohne TIME_PERIOD/OBS_VALUE (Spalten: {list(table.columns)})")
    columns = list(table.columns)
    dims = [
        c
        for c in columns[: columns.index("TIME_PERIOD")]
        if c not in _NON_DIMENSION and not c.startswith("OBS_")
    ]
    table = table[table["OBS_VALUE"].str.strip() != ""]
    if table.empty:
        raise SeriesNotFoundError("SDMX-Antwort ohne Beobachtungen")
    if dims:
        groups = table.groupby(dims, sort=False)
        if groups.ngroups > 1:
            sizes = groups.size().sort_values(ascending=False)
            log.warning(
                "SDMX-Antwort enthält %d Reihen, verwende die längste (%s)",
                groups.ngroups,
                sizes.index[0],
            )
            key = sizes.index[0]
            table = groups.get_group(key if isinstance(key, tuple) else (key,))
    values = table["OBS_VALUE"].str.strip()
    if values.str.contains(",").any() and not values.str.contains(r"\.").any():
        values = values.str.replace(",", ".", regex=False)
    frame = pd.DataFrame(
        {
            "obs_date": [period_end(p) for p in table["TIME_PERIOD"]],
            "value": pd.to_numeric(values, errors="coerce").to_numpy(),
        }
    )
    return normalize_frame(frame)


class SdmxProvider(Provider):
    """Gemeinsame Logik aller SDMX-CSV-Quellen."""

    default_template: ClassVar[str] = ""
    default_params: ClassVar[dict[str, str]] = {}
    description: ClassVar[str] = ""
    kinds: ClassVar[frozenset[str]] = frozenset({"macro", "rate", "yield", "fx", "level"})

    def capabilities(self) -> Capabilities:
        """Makro- und Zinsreihen ohne Vintages."""
        return Capabilities(kinds=self.kinds, vintages=False, description=self.description)

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt ``<Datenfluss>/<Schlüssel>`` als SDMX-CSV."""
        self._require_available()
        if "/" not in request.symbol:
            raise ProviderError(f"{self.name}: Symbol muss 'Datenfluss/Schlüssel' sein")
        flow, key = request.symbol.split("/", 1)
        template = str(self.config.options.get("url_template", self.default_template))
        params: dict[str, Any] = dict(self.config.options.get("params", self.default_params))
        if request.start is not None:
            params["startPeriod"] = request.start.strftime("%Y-%m-%d" if key[:1] == "D" else "%Y")
        response = self.http.get(
            template.format(flow=flow, key=key),
            params=params,
            headers={"Accept": "text/csv, application/vnd.sdmx.data+csv, */*"},
            min_interval=self.min_interval,
        )
        frame = parse_sdmx_csv(response.text)
        out = clip_dates(frame, request.start, request.end)
        if out.empty:
            raise SeriesNotFoundError(f"{self.name}: keine Werte für {request.symbol}")
        return out


class EcbProvider(SdmxProvider):
    """EZB Data Portal: €STR, Euribor, HVPI, Geldmenge, Kredite, EUR-Wechselkurse."""

    name: ClassVar[str] = "ecb"
    default_template = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}"
    default_params: ClassVar[dict[str, str]] = {"format": "csvdata"}
    description = "€STR, Euribor, HVPI, Geldmenge, Kredite, EUR-Referenzkurse"


class EurostatProvider(SdmxProvider):
    """Eurostat: BIP, Industrieproduktion, Arbeitsmarkt, Preise."""

    name: ClassVar[str] = "eurostat"
    default_template = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{flow}/{key}"
    default_params: ClassVar[dict[str, str]] = {"format": "SDMX-CSV"}
    description = "BIP, Industrieproduktion, Arbeitsmarkt, Preise der Eurozone"


class OecdProvider(SdmxProvider):
    """OECD: Composite Leading Indicators, Kurz- und Langfristzinsen weiterer Währungen."""

    name: ClassVar[str] = "oecd"
    default_template = "https://sdmx.oecd.org/public/rest/data/{flow}/{key}"
    default_params: ClassVar[dict[str, str]] = {
        "dimensionAtObservation": "AllDimensions",
        "format": "csvfile",
    }
    description = "Composite Leading Indicators, Kurz- und Langfristzinsen"


class BisProvider(SdmxProvider):
    """BIS Data Portal: Kredit/BIP-Lücke, Schuldendienstquoten, Verschuldung, Wechselkurse."""

    name: ClassVar[str] = "bis"
    default_template = "https://stats.bis.org/api/v1/data/{flow}/{key}"
    default_params: ClassVar[dict[str, str]] = {"format": "csv"}
    description = "Kredit/BIP-Lücke, Schuldendienstquoten, Staatsverschuldung"


class BundesbankProvider(SdmxProvider):
    """Deutsche Bundesbank: Zinsstruktur der Bundeswertpapiere, Goldpreis London."""

    name: ClassVar[str] = "bundesbank"
    default_template = "https://api.statistiken.bundesbank.de/rest/data/{flow}/{key}"
    default_params: ClassVar[dict[str, str]] = {"format": "sdmx_csv", "lang": "en"}
    description = "Bund-Renditen nach Restlaufzeit (ab 1972), Goldpreis London (ab 1968)"
