"""Rohdaten-Cache: Aktualität, inkrementeller Abruf, Rückfall auf den älteren Stand."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import SourceConfig
from navigator.data.cache import SeriesCache, safe_name
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)


class ScriptedProvider(Provider):
    """Liefert vorbereitete Daten und merkt sich die Anfragen."""

    name = "scripted"

    def __init__(self, frame: pd.DataFrame) -> None:
        super().__init__(SourceConfig())
        self.frame = frame
        self.requests: list[SeriesRequest] = []
        self.fail = False

    def capabilities(self) -> Capabilities:
        return Capabilities(kinds=frozenset({"price"}))

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        self.requests.append(request)
        if self.fail:
            raise ProviderError("Quelle nicht erreichbar")
        return clip_dates(normalize_frame(self.frame), request.start, request.end)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _prices(days: int, scale: float = 1.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=days)
    return pd.DataFrame({"obs_date": dates, "value": scale * (100.0 + np.arange(days))})


def test_safe_name_is_filesystem_safe_and_unique() -> None:
    first, second = safe_name("EXR/D.USD.EUR.SP00.A"), safe_name("EXR/D.USD.EUR.SP00_A")
    assert "/" not in first and first != second


def test_fresh_cache_avoids_second_fetch(tmp_path: Path) -> None:
    clock = Clock()
    cache = SeriesCache(tmp_path, max_age_hours=20, now=clock)
    provider = ScriptedProvider(_prices(50))
    request = SeriesRequest("ABC", "price")
    frame, meta = cache.fetch("scripted", provider, request)
    assert len(frame) == 50 and meta.fetched_at.startswith("2026-11-16T12:00")
    cache.fetch("scripted", provider, request)
    assert len(provider.requests) == 1
    cache.fetch("scripted", provider, request, force=True)
    assert len(provider.requests) == 2


def test_incremental_fetch_appends_only_the_tail(tmp_path: Path) -> None:
    clock = Clock()
    cache = SeriesCache(tmp_path, max_age_hours=20, price_overlap_days=15, now=clock)
    provider = ScriptedProvider(_prices(50))
    request = SeriesRequest("ABC", "price")
    cache.fetch("scripted", provider, request)
    provider.frame = _prices(60)
    clock.now += timedelta(days=2)
    frame, meta = cache.fetch("scripted", provider, request)
    assert len(frame) == 60 and meta.mode == "incremental"
    assert provider.requests[-1].start is not None  # nur das Ende wurde angefragt
    assert len(provider.requests) == 2


def test_readjusted_history_triggers_full_reload(tmp_path: Path) -> None:
    clock = Clock()
    cache = SeriesCache(tmp_path, now=clock)
    provider = ScriptedProvider(_prices(50))
    request = SeriesRequest("ABC", "price")
    cache.fetch("scripted", provider, request)
    provider.frame = _prices(60, scale=0.98)  # z. B. nach einer Ausschüttung neu bereinigt
    clock.now += timedelta(days=2)
    frame, meta = cache.fetch("scripted", provider, request)
    assert meta.mode == "full" and len(frame) == 60
    assert frame["value"].iloc[0] == pytest.approx(98.0)
    assert provider.requests[-1].start is None


def test_failed_source_returns_stale_data_flagged(tmp_path: Path) -> None:
    clock = Clock()
    cache = SeriesCache(tmp_path, now=clock)
    provider = ScriptedProvider(_prices(50))
    request = SeriesRequest("ABC", "price")
    cache.fetch("scripted", provider, request)
    provider.fail = True
    clock.now += timedelta(days=3)
    frame, meta = cache.fetch("scripted", provider, request)
    assert len(frame) == 50
    assert meta.stale and "nicht erreichbar" in meta.error


def test_failed_source_without_cache_raises(tmp_path: Path) -> None:
    provider = ScriptedProvider(_prices(5))
    provider.fail = True
    with pytest.raises(ProviderError):
        SeriesCache(tmp_path).fetch("scripted", provider, SeriesRequest("ABC", "price"))


def test_unreadable_answers_never_abort_but_are_reported(tmp_path: Path) -> None:
    """Auch unerwartete Fehler (HTTP, kaputtes Format) führen zum gekennzeichneten Rückfall."""
    from navigator.http import HttpError

    class Broken(ScriptedProvider):
        error: Exception = HttpError("HTTP 404 für https://example.org", status=404)

        def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
            if self.fail:
                raise self.error
            return super().fetch_series(request)

    clock = Clock()
    cache = SeriesCache(tmp_path, now=clock)
    provider = Broken(_prices(20))
    request = SeriesRequest("ABC", "price")
    provider.fail = True
    with pytest.raises(ProviderError, match="HttpError: HTTP 404"):
        cache.fetch("scripted", provider, request)
    provider.fail = False
    cache.fetch("scripted", provider, request)
    provider.fail, provider.error = True, ValueError("Spalte fehlt")
    clock.now += timedelta(days=2)
    _, meta = cache.fetch("scripted", provider, request)
    assert meta.stale and "Spalte fehlt" in meta.error
