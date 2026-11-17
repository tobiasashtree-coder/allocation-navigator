"""Backfill-Verkettung und Aufbau des Universums, einschließlich Look-ahead-Test."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from navigator.config import AppConfig, CalibrationConfig
from navigator.data.backfill import SegmentSeries, calibrate, splice
from navigator.data.pipeline import make_cache, make_providers
from navigator.data.universe import SeriesLoader, UniverseBuilder, UniverseData
from navigator.paths import ProjectPaths
from navigator.testing import assert_no_lookahead, perturb_parquet_tree

CAL = CalibrationConfig()


def _pair(
    beta: float = 1.5, alpha: float = 0.001, noise: float = 0.002
) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(7)
    index = pd.date_range("1990-01-31", periods=240, freq="ME")
    older = pd.Series(rng.normal(0.005, 0.04, 240), index=index)
    newer = (alpha + beta * older + rng.normal(0, noise, 240)).iloc[120:]
    return newer, older


def test_splice_uses_backfill_only_before_proxy_start() -> None:
    newer, older = _pair()
    result = splice(
        [SegmentSeries("proxy", newer, "proxy"), SegmentSeries("index", older, "original", True)],
        CAL,
    )
    seam = newer.index.min()
    assert result.returns.index.is_monotonic_increasing and len(result.returns) == 240
    pd.testing.assert_series_equal(result.returns[seam:], newer, check_names=False)
    assert (result.segment[:"1999-12-31"] == "index").all()
    assert (result.segment[seam:] == "proxy").all()
    assert result.backfill[:"1999-12-31"].all() and not result.backfill[seam:].any()
    assert set(result.quality) == {"original", "proxy"}


def test_calibration_recovers_relationship_with_shrinkage() -> None:
    newer, older = _pair(beta=1.5, alpha=0.0, noise=0.001)
    alpha, beta, months, corr = calibrate(newer, older, newer.index.min(), CAL)
    assert months == 36 and corr > 0.99
    assert beta == pytest.approx(1.25, abs=0.02)  # halbe Schrumpfung von 1,5 Richtung 1
    assert abs(alpha) <= CAL.alpha_bound_monthly
    result = splice(
        [SegmentSeries("proxy", newer, "proxy"), SegmentSeries("index", older, "original", True)],
        CAL,
    )
    assert result.calibrations[0].applied
    before = result.returns[:"1999-12-31"]
    assert before.std() == pytest.approx(beta * older[:"1999-12-31"].std(), rel=1e-9)


def test_level_difference_is_not_extrapolated_by_default() -> None:
    """Ein Renditevorsprung des Proxys im Fenster wird nicht auf Jahrzehnte davor übertragen."""
    newer, older = _pair(beta=1.0, alpha=0.004, noise=0.001)
    alpha, beta, _, _ = calibrate(newer, older, newer.index.min(), CAL)
    assert alpha == 0.0 and beta == pytest.approx(1.0, abs=0.02)
    loose = CalibrationConfig(alpha_bound_monthly=0.005)
    assert calibrate(newer, older, newer.index.min(), loose)[0] == pytest.approx(0.002, abs=5e-4)


def test_poorly_matching_backfill_is_not_calibrated() -> None:
    rng = np.random.default_rng(11)
    index = pd.date_range("1990-01-31", periods=240, freq="ME")
    older = pd.Series(rng.normal(0, 0.04, 240), index=index)
    newer = pd.Series(rng.normal(0, 0.04, 120), index=index[120:])
    result = splice(
        [SegmentSeries("proxy", newer, "proxy"), SegmentSeries("index", older, "original", True)],
        CAL,
    )
    calibration = result.calibrations[0]
    assert not calibration.applied and (calibration.alpha, calibration.beta) == (0.0, 1.0)
    pd.testing.assert_series_equal(
        result.returns[:"1999-12-31"], older[:"1999-12-31"], check_names=False
    )


def test_calibration_is_point_in_time() -> None:
    """Vor Proxy-Start bleibt der Backfill unverändert; das Fenster wächst mit dem Stichtag."""
    newer, older = _pair(beta=1.6, alpha=0.0, noise=0.001)
    segments = [
        SegmentSeries("proxy", newer, "proxy"),
        SegmentSeries("index", older, "original", True),
    ]
    early = splice(segments, CAL, asof=pd.Timestamp("1998-06-30"))
    assert (early.segment == "index").all() and early.calibrations == []
    pd.testing.assert_series_equal(early.returns, older[:"1998-06-30"], check_names=False)
    young = splice(segments, CAL, asof=pd.Timestamp("2000-06-30"))  # erst 6 Monate Überlappung
    assert not young.calibrations[0].applied and young.calibrations[0].months == 6
    mature = splice(segments, CAL, asof=pd.Timestamp("2001-06-30"))
    assert mature.calibrations[0].applied and mature.calibrations[0].months == 18
    # Daten nach dem Stichtag ändern das Ergebnis für den Stichtag nicht.
    changed = [
        SegmentSeries(
            s.id, s.returns.where(s.returns.index <= "2001-06-30", 9.9), s.quality, s.backfill
        )
        for s in segments
    ]
    again = splice(changed, CAL, asof=pd.Timestamp("2001-06-30"))
    pd.testing.assert_series_equal(mature.returns, again.returns)


# --------------------------------------------------------------------------- Universum


def _builder(config: AppConfig, paths: ProjectPaths) -> UniverseBuilder:
    providers = make_providers(config, paths)
    return UniverseBuilder(config, SeriesLoader(make_cache(config, paths), providers))


@pytest.fixture(scope="module")
def universes(config: AppConfig, demo_project: ProjectPaths) -> dict[str, UniverseData]:
    builder = _builder(config, demo_project)
    return {base: builder.build(base) for base in config.currency.supported}


def test_all_18_classes_in_every_base_currency(
    config: AppConfig, universes: dict[str, UniverseData]
) -> None:
    """Abnahmekriterium M1: alle 18 Klassen als Monatsreihen in jeder Basiswährung."""
    expected = list(config.universe.enabled_assets())
    for base, universe in universes.items():
        assert list(universe.returns.columns) == expected, base
        assert universe.returns.index.is_month_end.all()
        for asset in expected:
            series = universe.returns[asset].dropna()
            assert len(series) > 120 and np.isfinite(series.to_numpy()).all(), (base, asset)
        flags = {q for q in universe.quality.to_numpy().ravel() if isinstance(q, str)}
        assert flags == {"original", "proxy", "synthetisch"}


def test_currency_effect_is_separated_and_consistent(universes: dict[str, UniverseData]) -> None:
    eur, usd = universes["EUR"], universes["USD"]
    # Ein USD-Fonds hat in USD keinen Währungseinfluss, in EUR schon.
    assert (usd.currency_effect["equity_us"].dropna() == 0).all()
    assert eur.currency_effect["equity_us"].abs().sum() > 0
    # EUR-Anleihen: in EUR kein Einfluss; in USD nur die Zinsdifferenz der Sicherung (klein).
    assert (eur.currency_effect["bond_eur_long"].dropna() == 0).all()
    carry = usd.currency_effect["bond_eur_long"].dropna()
    assert 0 < carry.abs().max() < 0.02
    # Ungesichert: (1 + lokal) * (1 + Währung) - 1; der Effekt ist die Differenz zur Lokalrendite.
    local = usd.returns["equity_us"]
    effect = eur.currency_effect["equity_us"]
    joined = pd.concat([eur.returns["equity_us"], local, effect], axis=1).dropna().loc["2005":]
    assert np.allclose(joined.iloc[:, 0], joined.iloc[:, 1] + joined.iloc[:, 2])
    # Cash folgt der Basiswährung.
    assert not np.allclose(
        eur.returns["cash"].dropna().tail(24), usd.returns["cash"].dropna().tail(24)
    )


def test_coverage_table_flags_backfill_and_quality(universes: dict[str, UniverseData]) -> None:
    coverage = universes["EUR"].coverage()
    assert coverage.loc["equity_us", "backfill"] > 0.3
    assert coverage.loc["bitcoin", "original"] == 1.0 and coverage.loc["bitcoin", "backfill"] == 0.0
    assert coverage.loc["bond_eur_long", "synthetisch"] > 0.3
    assert coverage.loc["bond_high_yield", "proxy"] == 1.0
    row = coverage.loc["equity_us"]
    assert row["original"] + row["proxy"] + row["synthetisch"] == pytest.approx(1.0)


def test_unsupported_base_currency_is_rejected(
    config: AppConfig, demo_project: ProjectPaths
) -> None:
    with pytest.raises(ValueError, match="nicht unterstützt"):
        _builder(config, demo_project).build("JPY")


@pytest.mark.parametrize("when", ["1995-06-30", "2003-11-30", "2015-03-31", "2026-06-30"])
@pytest.mark.parametrize("base", ["EUR", "USD"])
def test_no_lookahead_in_universe(
    config: AppConfig, demo_project: ProjectPaths, tmp_path: Path, when: str, base: str
) -> None:
    """Look-ahead-Test: Werden alle Rohdaten nach t verändert, bleibt das Universum bis t gleich."""
    stamp = pd.Timestamp(when)
    perturbed = ProjectPaths(root=tmp_path, demo=True)
    changed = perturb_parquet_tree(demo_project.raw, perturbed.raw, stamp, seed=42)
    assert changed > 50, "der Test muss die Daten nach t wirklich verändern"

    def compute(paths: ProjectPaths, t: pd.Timestamp) -> pd.DataFrame:
        universe = _builder(config, paths).build(base, asof=t)
        assert universe.returns.index.max() <= t
        return pd.concat({"r": universe.returns, "fx": universe.currency_effect}, axis=1)

    assert_no_lookahead(compute, demo_project, perturbed, stamp)
    # Gegenprobe: Ohne Stichtag unterscheiden sich die Ergebnisse.
    full_a = _builder(config, demo_project).build(base).returns
    full_b = _builder(config, perturbed).build(base).returns
    assert not full_a.equals(full_b)
