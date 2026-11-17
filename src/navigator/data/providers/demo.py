"""Demo-Provider: deterministische, synthetische Reihen ohne Netzzugriff.

Nur für Tests und zum Ausprobieren der Abläufe (``--demo``). Demo-Daten liegen in
einem eigenen Ordner (``data_demo``) und jeder Bericht ist deutlich als Demo
gekennzeichnet. Sie sagen nichts über echte Märkte aus.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar

import numpy as np
import pandas as pd

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)

DEMO_END = pd.Timestamp("2026-10-30")
_STARTS = {
    "price": "2000-01-03",
    "level": "1968-04-01",
    "returns": "1970-01-31",
    "yield": "1962-01-02",
    "rate": "1960-01-01",
    "fx": "1971-01-04",
    "macro": "1960-01-31",
}


def _seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big")


class DemoProvider(Provider):
    """Erzeugt je Symbol reproduzierbare Zufallsreihen passend zur Art der Reihe."""

    name: ClassVar[str] = "demo"

    def __init__(self, config: SourceConfig, alias: str = "demo") -> None:
        super().__init__(config)
        self.alias = alias

    def available(self) -> bool:
        """Der Demo-Provider ist immer nutzbar."""
        return True

    def capabilities(self) -> Capabilities:
        """Alle Arten von Reihen, mit einfachen Vintages für Makrodaten."""
        return Capabilities(
            kinds=frozenset(_STARTS), vintages=True, description="synthetische Demo-Daten"
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Liefert eine synthetische Reihe; gleiche Anfrage ergibt immer dieselben Werte."""
        kind = request.kind
        # Dieselbe Reihe aus zwei Quellen soll fast gleich sein (Kreuzprüfung),
        # daher hängt der Zufall nur am Symbol, nicht an der Quelle.
        rng = np.random.default_rng(_seed(request.symbol.split(".")[0].upper(), kind))
        start = pd.Timestamp(_STARTS[kind])
        if kind in ("price", "level", "yield", "fx") or (kind == "rate"):
            dates = pd.bdate_range(start, DEMO_END)
        else:
            dates = pd.date_range(start, DEMO_END, freq="ME")
        n = len(dates)
        frame = pd.DataFrame({"obs_date": dates})
        if kind == "price":
            vol = 0.01 * (0.4 + rng.random() * 1.2)
            steps = rng.normal(0.0003, vol, n)
            adjusted = 100.0 * np.exp(np.cumsum(steps))
            payout = np.exp(-np.arange(n)[::-1] * 0.00008)
            frame["value"] = adjusted
            frame["raw"] = adjusted * payout
        elif kind in ("level", "fx"):
            base = 1.0 if kind == "fx" else 100.0
            frame["value"] = base * np.exp(np.cumsum(rng.normal(0.0001, 0.006, n)))
        elif kind in ("yield", "rate"):
            level = np.empty(n)
            level[0] = 5.0
            shocks = rng.normal(0.0, 0.05, n)
            for i in range(1, n):
                level[i] = level[i - 1] + 0.001 * (4.0 - level[i - 1]) + shocks[i]
            frame["value"] = np.clip(level, -0.5, 18.0)
        elif kind == "returns":
            frame["value"] = rng.normal(0.006, 0.04, n)
        else:  # macro
            frame["value"] = 100.0 * np.exp(np.cumsum(rng.normal(0.002, 0.006, n)))
            if request.vintages:
                first = frame.copy()
                first["known_from"] = first["obs_date"] + pd.Timedelta(days=20)
                revised = frame.iloc[-24:].copy()
                revised["value"] = revised["value"] * (1.0 + rng.normal(0.0, 0.002, len(revised)))
                revised["known_from"] = revised["obs_date"] + pd.Timedelta(days=80)
                frame = pd.concat([first, revised], ignore_index=True)
        return clip_dates(normalize_frame(frame), request.start, request.end)


def demo_config() -> SourceConfig:
    """Konfiguration des Demo-Providers."""
    return SourceConfig(license="Synthetische Demo-Daten", note="keine echten Marktdaten")
