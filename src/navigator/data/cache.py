"""Lokaler Rohdaten-Cache (Parquet) mit Abrufzeitpunkt je Reihe.

Erneute Abrufe laufen inkrementell: Für Tagesreihen wird nur das Ende der Historie
nachgeladen. Weicht die Überlappung vom gespeicherten Stand ab (z. B. weil Kurse nach
einer Ausschüttung neu bereinigt wurden), wird die ganze Reihe neu geladen.

Fällt eine Quelle aus, liefert der Cache den älteren Stand mit dem Kennzeichen
``stale``; veraltete Daten werden also nie stillschweigend verwendet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from navigator.data.providers.base import Provider, ProviderError, SeriesRequest, normalize_frame
from navigator.runlog import utc_now

log = logging.getLogger(__name__)

INCREMENTAL_KINDS = frozenset({"price", "level", "fx", "yield", "rate"})


@dataclass
class CacheMeta:
    """Begleitdaten einer gespeicherten Reihe."""

    provider: str
    symbol: str
    kind: str
    fetched_at: str
    first_obs: str
    last_obs: str
    rows: int
    vintages: bool = False
    stale: bool = False
    error: str = ""
    mode: str = "full"

    def fetched(self) -> datetime:
        """Abrufzeitpunkt als Datum."""
        return datetime.fromisoformat(self.fetched_at)


def safe_name(symbol: str) -> str:
    """Dateiname für ein Symbol (lesbar und eindeutig)."""
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol).strip("_")[:60]
    digest = hashlib.sha1(symbol.encode()).hexdigest()[:8]
    return f"{readable}_{digest}"


class SeriesCache:
    """Speichert Provider-Ergebnisse je Quelle und Symbol."""

    def __init__(
        self,
        root: Path,
        max_age_hours: float = 20.0,
        price_overlap_days: int = 15,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.root = root
        self.max_age_hours = max_age_hours
        self.price_overlap_days = price_overlap_days
        self._now = now

    def _paths(self, provider: str, symbol: str) -> tuple[Path, Path]:
        base = self.root / provider / safe_name(symbol)
        return base.with_suffix(".parquet"), base.with_suffix(".json")

    def read(self, provider: str, symbol: str) -> tuple[pd.DataFrame, CacheMeta] | None:
        """Liest eine gespeicherte Reihe samt Begleitdaten."""
        data_path, meta_path = self._paths(provider, symbol)
        if not data_path.exists() or not meta_path.exists():
            return None
        meta = CacheMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
        return normalize_frame(pd.read_parquet(data_path)), meta

    def write(
        self, provider: str, symbol: str, kind: str, frame: pd.DataFrame, mode: str = "full"
    ) -> CacheMeta:
        """Speichert eine Reihe und ihren Abrufzeitpunkt."""
        data_path, meta_path = self._paths(provider, symbol)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(data_path, index=False)
        meta = CacheMeta(
            provider=provider,
            symbol=symbol,
            kind=kind,
            fetched_at=self._now().isoformat(timespec="seconds"),
            first_obs=str(frame["obs_date"].min().date()),
            last_obs=str(frame["obs_date"].max().date()),
            rows=len(frame),
            vintages="known_from" in frame.columns,
            mode=mode,
        )
        meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False), encoding="utf-8")
        return meta

    def _is_fresh(self, meta: CacheMeta) -> bool:
        age = (self._now() - meta.fetched()).total_seconds() / 3600.0
        return age < self.max_age_hours

    def fetch(
        self, name: str, provider: Provider, request: SeriesRequest, force: bool = False
    ) -> tuple[pd.DataFrame, CacheMeta]:
        """Liefert eine Reihe aus dem Cache oder lädt sie (inkrementell) nach."""
        cached = self.read(name, request.symbol)
        if cached is not None and not force and self._is_fresh(cached[1]):
            return cached
        try:
            if (
                cached is not None
                and not force
                and request.kind in INCREMENTAL_KINDS
                and not request.vintages
            ):
                merged = self._incremental(provider, request, cached[0])
                if merged is not None:
                    return merged, self.write(
                        name, request.symbol, request.kind, merged, mode="incremental"
                    )
            frame = provider.fetch_series(request)
            return frame, self.write(name, request.symbol, request.kind, frame)
        except Exception as exc:
            # Quelle ausgefallen oder Antwort unlesbar: nie den ganzen Lauf abbrechen,
            # aber auch nie stillschweigend weitermachen.
            if cached is None:
                if isinstance(exc, ProviderError):
                    raise
                raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
            log.warning(
                "%s: Abruf von %s gescheitert (%s); verwende den Stand vom %s",
                name,
                request.symbol,
                exc,
                cached[1].fetched_at,
            )
            return cached[0], replace(cached[1], stale=True, error=str(exc))

    def _incremental(
        self, provider: Provider, request: SeriesRequest, old: pd.DataFrame
    ) -> pd.DataFrame | None:
        """Lädt nur das Ende nach. Liefert ``None``, wenn die Historie neu geladen werden muss."""
        start = (old["obs_date"].max() - pd.Timedelta(days=self.price_overlap_days)).date()
        fresh = provider.fetch_series(replace(request, start=start))
        overlap = old.merge(fresh, on="obs_date", suffixes=("_old", "_new"))
        if overlap.empty:
            return None
        same = np.allclose(
            overlap["value_old"].to_numpy(), overlap["value_new"].to_numpy(), rtol=1e-6, atol=1e-9
        )
        if not same:
            log.info(
                "%s: gespeicherte Historie weicht ab (neu bereinigt?), lade vollständig neu",
                request.symbol,
            )
            return None
        keep = old[old["obs_date"] < fresh["obs_date"].min()]
        return normalize_frame(pd.concat([keep, fresh], ignore_index=True))
