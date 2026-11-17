"""Gemeinsame Provider-Schnittstelle (Spezifikation Abschnitt 3).

Jede Quelle implementiert ``fetch_series``, ``capabilities`` und ``license``. Dadurch
bleiben Quellen austauschbar; ein späteres Abo wird nur in der Konfiguration
eingeschaltet.

Einheitliches Rückgabeformat von ``fetch_series`` (ein DataFrame):

- ``obs_date``   Beobachtungsdatum bzw. Periodenende (datetime64[ns])
- ``value``      Wert (bei Kursen: um Ausschüttungen und Splits bereinigt)
- ``raw``        optional: unbereinigter Schlusskurs (für Dividenden- und Split-Prüfung)
- ``known_from`` optional: Zeitpunkt, ab dem der Wert öffentlich bekannt war (Vintages)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from navigator.config import SeriesKind, SourceConfig
from navigator.http import HttpClient

FRAME_COLUMNS = ("obs_date", "value", "raw", "known_from")


class ProviderError(RuntimeError):
    """Allgemeiner Fehler einer Datenquelle."""


class ProviderDisabledError(ProviderError):
    """Quelle ist ausgeschaltet oder ihr fehlt der API-Key bzw. die Lizenz."""


class SeriesNotFoundError(ProviderError):
    """Die Quelle kennt die angefragte Reihe nicht oder liefert keine Werte."""


@dataclass(frozen=True)
class SeriesRequest:
    """Anfrage nach einer Reihe."""

    symbol: str
    kind: SeriesKind = "price"
    start: date | None = None
    end: date | None = None
    vintages: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Capabilities:
    """Was eine Quelle liefern kann."""

    kinds: frozenset[str]
    vintages: bool = False
    needs_key: bool = False
    description: str = ""


@dataclass(frozen=True)
class License:
    """Lizenzhinweis einer Quelle."""

    name: str
    url: str = ""
    commercial_use: bool = False
    note: str = ""


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Bringt ein Provider-Ergebnis in das einheitliche Format (sortiert, ohne Lücken-Zeilen)."""
    if "obs_date" not in df.columns or "value" not in df.columns:
        raise ProviderError("Provider-Ergebnis braucht die Spalten 'obs_date' und 'value'")
    out = df[[c for c in FRAME_COLUMNS if c in df.columns]].copy()
    out["obs_date"] = pd.to_datetime(out["obs_date"]).astype("datetime64[ns]")
    out["value"] = pd.to_numeric(out["value"], errors="coerce").astype("float64")
    if "raw" in out.columns:
        out["raw"] = pd.to_numeric(out["raw"], errors="coerce").astype("float64")
    if "known_from" in out.columns:
        out["known_from"] = pd.to_datetime(out["known_from"]).astype("datetime64[ns]")
    out = out.dropna(subset=["obs_date", "value"])
    keys = ["obs_date", "known_from"] if "known_from" in out.columns else ["obs_date"]
    out = out.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    return out.reset_index(drop=True)


def clip_dates(df: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    """Beschneidet ein Ergebnis auf den angefragten Zeitraum."""
    out = df
    if start is not None:
        out = out[out["obs_date"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["obs_date"] <= pd.Timestamp(end)]
    return out.reset_index(drop=True)


class Provider(ABC):
    """Basisklasse aller Datenquellen."""

    name: ClassVar[str] = ""

    def __init__(self, config: SourceConfig, http: HttpClient | None = None) -> None:
        self.config = config
        self.http = http or HttpClient()

    # -- Schnittstelle laut Spezifikation -------------------------------------------------
    @abstractmethod
    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lädt eine Reihe im einheitlichen Format."""

    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Beschreibt, welche Arten von Reihen die Quelle abdeckt."""

    def license(self) -> License:
        """Lizenzhinweis laut Konfiguration."""
        return License(
            name=self.config.license,
            url=self.config.license_url,
            commercial_use=self.config.commercial_use,
            note=self.config.note,
        )

    # -- Hilfen ---------------------------------------------------------------------------
    @property
    def api_key(self) -> str | None:
        """API-Key aus der Umgebungsvariable (nie aus Code oder Konfiguration)."""
        env = self.config.api_key_env
        value = os.environ.get(env, "").strip() if env else ""
        return value or None

    @property
    def min_interval(self) -> float:
        """Mindestabstand zwischen zwei Abrufen in Sekunden."""
        rate = self.config.rate_limit_per_min
        return 60.0 / rate if rate else 0.0

    def available(self) -> bool:
        """Eingeschaltet und, falls nötig, mit API-Key versehen."""
        if not self.config.enabled:
            return False
        return not (self.config.requires_key and self.api_key is None)

    def unavailable_reason(self) -> str:
        """Begründung, warum die Quelle nicht nutzbar ist (leer, wenn nutzbar)."""
        if not self.config.enabled:
            return "in config/sources.yaml ausgeschaltet"
        if self.config.requires_key and self.api_key is None:
            return f"API-Key fehlt (Umgebungsvariable {self.config.api_key_env})"
        return ""

    def _require_available(self) -> None:
        if not self.available():
            raise ProviderDisabledError(f"{self.name}: {self.unavailable_reason()}")
