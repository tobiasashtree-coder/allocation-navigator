"""Point-in-Time-Speicher: Entscheidungen zu t nutzen nur Daten, die zu t bekannt waren.

Das ist die wichtigste Qualitätsanforderung des Tools. Jede Makroreihe trägt deshalb
zwei Datumsangaben je Wert: das Beobachtungsdatum (``obs_date``) und den Zeitpunkt,
ab dem der Wert öffentlich bekannt war (``known_from``). Spätere Revisionen sind
zusätzliche Zeilen mit späterem ``known_from``.

Herkunft von ``known_from``:

- ALFRED liefert echte Veröffentlichungsdaten (Vintages).
- Wo es keine Vintages gibt (EZB, Eurostat, OECD, BIS), gilt eine konservative
  Veröffentlichungsverzögerung je Reihe.
- Für Werte vor Beginn der ALFRED-Historie gilt ebenfalls die Verzögerungsregel;
  diese Zeilen sind mit ``approx`` gekennzeichnet.
- Revisionen, die das Tool selbst bei späteren Abrufen bemerkt, erhalten das
  Abrufdatum als ``known_from``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from navigator.config import PublicationLag
from navigator.data.cache import safe_name

PIT_COLUMNS = ["obs_date", "value", "known_from", "approx"]


def period_end(dates: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    """Ende der Periode, auf die sich eine Beobachtung bezieht."""
    index = pd.DatetimeIndex(dates).normalize()
    if frequency == "M":
        return pd.DatetimeIndex(index + pd.offsets.MonthEnd(0))
    if frequency == "Q":
        return pd.DatetimeIndex(index + pd.offsets.QuarterEnd(0))
    if frequency == "A":
        return pd.DatetimeIndex(index + pd.offsets.YearEnd(0))
    return index


def known_from_rule(
    dates: pd.DatetimeIndex, frequency: str, lag: PublicationLag
) -> pd.DatetimeIndex:
    """Bekanntheitszeitpunkt nach der konservativen Verzögerungsregel.

    ``months=1`` heißt: Der Wert eines Monats gilt erst am Ende des Folgemonats als
    bekannt.
    """
    end = period_end(dates, frequency)
    if lag.months:
        end = pd.DatetimeIndex(end + pd.offsets.MonthEnd(lag.months))
    if lag.days:
        end = pd.DatetimeIndex(end + pd.Timedelta(days=lag.days))
    return end


@dataclass
class PitSeries:
    """Eine Reihe mit allen bekannten Datenständen."""

    key: str
    frame: pd.DataFrame

    def __post_init__(self) -> None:
        frame = self.frame.copy()
        if "approx" not in frame.columns:
            frame["approx"] = False
        frame["obs_date"] = pd.to_datetime(frame["obs_date"]).astype("datetime64[ns]")
        frame["known_from"] = pd.to_datetime(frame["known_from"]).astype("datetime64[ns]")
        frame["value"] = frame["value"].astype("float64")
        frame["approx"] = frame["approx"].astype(bool)
        self.frame = (
            frame[PIT_COLUMNS]
            .dropna(subset=["obs_date", "value", "known_from"])
            .drop_duplicates(subset=["obs_date", "known_from"], keep="last")
            .sort_values(["obs_date", "known_from"])
            .reset_index(drop=True)
        )

    def as_of(self, when: pd.Timestamp | str) -> pd.Series:
        """Die Reihe, wie sie am Ende des Tages ``when`` bekannt war.

        Je Beobachtung zählt der jüngste Datenstand mit ``known_from <= when``. Werte,
        die erst später veröffentlicht oder revidiert wurden, fließen nicht ein.
        """
        cutoff = pd.Timestamp(when).normalize()
        known = self.frame[self.frame["known_from"] <= cutoff]
        latest = known.groupby("obs_date", sort=True)["value"].last()
        latest.name = self.key
        return latest

    def latest(self) -> pd.Series:
        """Der aktuellste Datenstand (nur für Anzeige, nie für Entscheidungen in der Historie)."""
        latest = self.frame.groupby("obs_date", sort=True)["value"].last()
        latest.name = self.key
        return latest

    def first_release(self) -> pd.Series:
        """Erstveröffentlichung je Beobachtung."""
        first = self.frame.groupby("obs_date", sort=True)["value"].first()
        first.name = self.key
        return first

    def revision_count(self) -> int:
        """Anzahl der Zeilen, die eine frühere Veröffentlichung revidieren."""
        return int(len(self.frame) - self.frame["obs_date"].nunique())


def from_lagged(key: str, frame: pd.DataFrame, frequency: str, lag: PublicationLag) -> PitSeries:
    """Baut eine Point-in-Time-Reihe aus einem einzigen Datenstand per Verzögerungsregel."""
    out = frame[["obs_date", "value"]].copy()
    out["known_from"] = known_from_rule(pd.DatetimeIndex(out["obs_date"]), frequency, lag)
    out["approx"] = True
    return PitSeries(key, out)


def from_vintages(key: str, frame: pd.DataFrame, frequency: str, lag: PublicationLag) -> PitSeries:
    """Baut eine Point-in-Time-Reihe aus echten Vintages (ALFRED).

    Beobachtungen, die schon im ersten überhaupt vorhandenen Datenstand enthalten
    sind, wurden meist viel früher veröffentlicht. Für sie gilt die Verzögerungsregel
    (``approx``), damit die Historie vor Beginn der Vintages nutzbar bleibt.
    """
    out = frame[["obs_date", "value", "known_from"]].copy()
    out["known_from"] = pd.to_datetime(out["known_from"]).astype("datetime64[ns]")
    rule = known_from_rule(pd.DatetimeIndex(out["obs_date"]), frequency, lag)
    first_vintage = out["known_from"].min()
    prehistory = (out["known_from"] == first_vintage).to_numpy() & (rule < first_vintage)
    out["approx"] = prehistory
    out.loc[prehistory, "known_from"] = rule[prehistory]
    return PitSeries(key, out)


def merge_fetch(
    existing: PitSeries,
    frame: pd.DataFrame,
    frequency: str,
    lag: PublicationLag,
    fetched_at: pd.Timestamp,
) -> PitSeries:
    """Ergänzt einen neuen Abruf einer Quelle ohne Vintages.

    Neue Beobachtungen gelten ab dem früheren von Verzögerungsregel und Abrufdatum als
    bekannt. Geänderte Werte sind Revisionen und gelten ab dem Abrufdatum.
    """
    fetched = pd.Timestamp(fetched_at).tz_localize(None).normalize()
    current = existing.latest()
    fresh = frame.set_index("obs_date")["value"].astype("float64")
    new_obs = fresh[~fresh.index.isin(current.index)]
    common = fresh[fresh.index.isin(current.index)]
    changed = common[
        ~np.isclose(common.to_numpy(), current.reindex(common.index).to_numpy(), rtol=1e-9)
    ]
    rows = [existing.frame]
    if len(new_obs):
        rule = known_from_rule(pd.DatetimeIndex(new_obs.index), frequency, lag)
        rows.append(
            pd.DataFrame(
                {
                    "obs_date": new_obs.index,
                    "value": new_obs.to_numpy(),
                    "known_from": np.minimum(rule.to_numpy(), np.datetime64(fetched)),
                    "approx": rule.to_numpy() <= np.datetime64(fetched),
                }
            )
        )
    if len(changed):
        rows.append(
            pd.DataFrame(
                {
                    "obs_date": changed.index,
                    "value": changed.to_numpy(),
                    "known_from": fetched,
                    "approx": False,
                }
            )
        )
    return PitSeries(existing.key, pd.concat(rows, ignore_index=True))


class PitStore:
    """Ablage der Point-in-Time-Reihen als Parquet-Dateien."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / f"{safe_name(key)}.parquet"

    def load(self, key: str, origin: str | None = None) -> PitSeries | None:
        """Lädt eine Reihe oder ``None``.

        Mit ``origin`` (``Quelle:Symbol``) nur, wenn die Reihe aus genau dieser Quelle stammt;
        so werden Altbestände einer früher konfigurierten Quelle nie verwendet.
        """
        path = self._path(key)
        if not path.exists():
            return None
        if origin is not None and self.origin(key) != origin:
            return None
        return PitSeries(key, pd.read_parquet(path))

    def _origin_path(self, key: str) -> Path:
        return self.root / f"{safe_name(key)}.origin"

    def origin(self, key: str) -> str | None:
        """Quelle und Symbol, aus denen die gespeicherte Reihe stammt (falls bekannt)."""
        path = self._origin_path(key)
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def save(self, series: PitSeries) -> None:
        """Speichert eine Reihe."""
        self.root.mkdir(parents=True, exist_ok=True)
        series.frame.to_parquet(self._path(series.key), index=False)

    def update(
        self,
        key: str,
        frame: pd.DataFrame,
        frequency: str,
        lag: PublicationLag,
        fetched_at: pd.Timestamp,
        origin: str | None = None,
    ) -> PitSeries:
        """Übernimmt einen Abruf: Vintages ersetzen den Stand, sonst wird ergänzt.

        Stammt der Abruf aus einer anderen Quelle als der gespeicherte Stand (``origin``),
        wird die Reihe neu aufgebaut: Abweichungen zwischen Quellen sind keine Revisionen
        (E-67).
        """
        if "known_from" in frame.columns:
            series = from_vintages(key, frame, frequency, lag)
        else:
            existing = self.load(key)
            if existing is not None and origin is not None and self.origin(key) != origin:
                existing = None
            series = (
                from_lagged(key, frame, frequency, lag)
                if existing is None
                else merge_fetch(existing, frame, frequency, lag, fetched_at)
            )
        self.save(series)
        if origin is not None:
            self._origin_path(key).write_text(origin, encoding="utf-8")
        return series
