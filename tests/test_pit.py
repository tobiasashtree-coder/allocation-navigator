"""Point-in-Time-Speicher: keine Daten nach t dürfen in ein Ergebnis für t einfließen."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import PublicationLag
from navigator.data.pit import (
    PitSeries,
    PitStore,
    from_lagged,
    from_vintages,
    known_from_rule,
    merge_fetch,
)
from navigator.testing import perturb_frame_after

LAG1 = PublicationLag(months=1)


def _vintage_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "obs_date": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01", "2024-03-01"]
            ),
            "value": [100.0, 101.0, 102.0, 101.5, 103.0],
            "known_from": pd.to_datetime(
                ["2024-02-15", "2024-03-15", "2024-03-15", "2024-04-16", "2024-04-16"]
            ),
        }
    )


def test_known_from_rule_month_quarter_and_days() -> None:
    dates = pd.DatetimeIndex(["2024-01-01", "2024-01-31"])
    assert list(known_from_rule(dates, "M", LAG1)) == [pd.Timestamp("2024-02-29")] * 2
    quarter = known_from_rule(pd.DatetimeIndex(["2024-01-01"]), "Q", PublicationLag(months=2))
    assert quarter[0] == pd.Timestamp("2024-05-31")
    daily = known_from_rule(pd.DatetimeIndex(["2024-01-10"]), "D", PublicationLag(days=1))
    assert daily[0] == pd.Timestamp("2024-01-11")


def test_as_of_returns_only_what_was_known() -> None:
    series = PitSeries("x", _vintage_frame())
    assert series.as_of("2024-02-14").empty
    assert series.as_of("2024-02-15").to_dict() == {pd.Timestamp("2024-01-01"): 100.0}
    march = series.as_of("2024-03-31")
    assert march[pd.Timestamp("2024-01-01")] == 101.0  # Revision vom 15.03. ist bekannt
    assert march[pd.Timestamp("2024-02-01")] == 102.0  # Revision vom 16.04. noch nicht
    assert pd.Timestamp("2024-03-01") not in march.index
    assert series.latest()[pd.Timestamp("2024-02-01")] == 101.5
    assert series.first_release()[pd.Timestamp("2024-01-01")] == 100.0
    assert series.revision_count() == 2


def test_lag_rule_delays_availability() -> None:
    frame = pd.DataFrame(
        {"obs_date": pd.to_datetime(["2024-01-31", "2024-02-29"]), "value": [1.0, 2.0]}
    )
    series = from_lagged("x", frame, "M", LAG1)
    assert series.as_of("2024-02-28").empty
    assert list(series.as_of("2024-02-29")) == [1.0]
    assert list(series.as_of("2024-03-31")) == [1.0, 2.0]


def test_vintage_prehistory_uses_lag_rule_and_is_flagged() -> None:
    frame = pd.DataFrame(
        {
            "obs_date": pd.to_datetime(["1990-01-01", "1990-02-01", "2000-01-01", "2000-01-01"]),
            "value": [1.0, 2.0, 3.0, 3.5],
            "known_from": pd.to_datetime(["2000-02-10", "2000-02-10", "2000-02-10", "2000-03-10"]),
        }
    )
    series = from_vintages("x", frame, "M", LAG1)
    # Die alten Werte stehen im ersten Datenstand von 2000, waren aber längst veröffentlicht.
    assert list(series.as_of("1990-03-31")) == [1.0, 2.0]
    assert series.as_of("1990-02-27").empty
    flagged = series.frame.set_index(["obs_date", "known_from"])["approx"]
    assert flagged.loc[(pd.Timestamp("1990-01-01"), pd.Timestamp("1990-02-28"))]
    assert not flagged.loc[(pd.Timestamp("2000-01-01"), pd.Timestamp("2000-02-10"))]
    assert series.as_of("2000-02-29")[pd.Timestamp("2000-01-01")] == 3.0


def test_merge_fetch_records_new_values_and_revisions() -> None:
    first = pd.DataFrame(
        {"obs_date": pd.to_datetime(["2024-01-31", "2024-02-29"]), "value": [1.0, 2.0]}
    )
    series = from_lagged("x", first, "M", LAG1)
    second = pd.DataFrame(
        {
            "obs_date": pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"]),
            "value": [1.0, 2.2, 3.0],
        }
    )
    merged = merge_fetch(series, second, "M", LAG1, pd.Timestamp("2024-04-20", tz="UTC"))
    # Die Revision des Februarwerts gilt erst ab dem Abrufdatum.
    assert merged.as_of("2024-04-19")[pd.Timestamp("2024-02-29")] == 2.0
    assert merged.as_of("2024-04-20")[pd.Timestamp("2024-02-29")] == 2.2
    # Der neue Märzwert gilt ab dem früheren von Regel (30.04.) und Abruf (20.04.).
    assert pd.Timestamp("2024-03-31") not in merged.as_of("2024-04-19").index
    assert merged.as_of("2024-04-20")[pd.Timestamp("2024-03-31")] == 3.0
    assert merged.revision_count() == 1


def test_store_roundtrip_and_update(tmp_path: Path) -> None:
    store = PitStore(tmp_path / "pit")
    assert store.load("indicator.x") is None
    store.update("indicator.x", _vintage_frame(), "M", LAG1, pd.Timestamp("2024-05-01"))
    loaded = store.load("indicator.x")
    assert loaded is not None and loaded.revision_count() == 2
    plain = pd.DataFrame({"obs_date": pd.to_datetime(["2024-01-31"]), "value": [5.0]})
    store.update("indicator.y", plain, "M", LAG1, pd.Timestamp("2024-05-01"))
    plain2 = pd.DataFrame({"obs_date": pd.to_datetime(["2024-01-31"]), "value": [6.0]})
    updated = store.update("indicator.y", plain2, "M", LAG1, pd.Timestamp("2024-06-01"))
    assert updated.as_of("2024-05-31").iloc[0] == 5.0
    assert updated.as_of("2024-06-01").iloc[0] == 6.0


@pytest.mark.parametrize("seed", range(5))
def test_no_lookahead_in_as_of(seed: int) -> None:
    """Look-ahead-Test: Werden alle Daten nach t verändert, bleibt as_of(t) gleich."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2000-01-31", periods=120, freq="ME")
    rows = []
    for month in months:
        release = month + pd.Timedelta(days=int(rng.integers(10, 45)))
        rows.append((month, rng.normal(), release))
        for _ in range(int(rng.integers(0, 3))):
            release = release + pd.Timedelta(days=int(rng.integers(20, 400)))
            rows.append((month, rng.normal(), release))
    frame = pd.DataFrame(rows, columns=["obs_date", "value", "known_from"])
    original = PitSeries("x", frame)
    for when in pd.date_range("2001-06-30", "2010-06-30", freq="13ME"):
        perturbed = PitSeries("x", perturb_frame_after(frame, when, rng))
        assert not perturbed.frame.equals(original.frame)
        pd.testing.assert_series_equal(original.as_of(when), perturbed.as_of(when))
