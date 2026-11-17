"""Backfill-Verkettung: Proxy und frühere Ersatzreihen zu einer Historie verbinden.

Backfill-Reihen werden nur für den Zeitraum vor Proxy-Start verwendet und an der Naht
mit gleitender Kalibrierung verkettet: Im Überlappungsfenster nach Proxy-Start wird
geschätzt, wie die Ersatzreihe den Proxy abbildet (alpha, beta), und die frühere
Historie entsprechend angepasst.

Point-in-Time: Die Kalibrierung nutzt nur Daten bis zum Stichtag. Liegt der Stichtag
vor dem Ende des Fensters, wächst das Fenster mit; liegt er vor Proxy-Start, bleibt
die Ersatzreihe unverändert.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from navigator.config import CalibrationConfig


@dataclass
class SegmentSeries:
    """Monatsrenditen eines Segments in der Zielwährung."""

    id: str
    returns: pd.Series
    quality: str
    backfill: bool = False


@dataclass
class Calibration:
    """Ergebnis der Kalibrierung an einer Naht."""

    older: str
    newer: str
    seam: str
    months: int
    alpha: float
    beta: float
    correlation: float
    applied: bool


@dataclass
class Spliced:
    """Verkettete Historie mit Herkunft und Qualitätskennzeichen je Monat."""

    returns: pd.Series
    segment: pd.Series
    quality: pd.Series
    backfill: pd.Series
    calibrations: list[Calibration] = field(default_factory=list)


def calibrate(
    newer: pd.Series, older: pd.Series, seam: pd.Timestamp, config: CalibrationConfig
) -> tuple[float, float, int, float]:
    """Schätzt alpha und beta der Ersatzreihe im Fenster nach der Naht (geschrumpft, begrenzt).

    Bei zu wenigen Monaten oder zu geringer Korrelation bleibt die Ersatzreihe
    unverändert (alpha = 0, beta = 1).
    """
    joined = pd.concat([newer, older], axis=1, join="inner").dropna()
    joined = joined[joined.index >= seam].iloc[: config.window_months]
    months = len(joined)
    if months < config.min_months:
        return 0.0, 1.0, months, float("nan")
    y, x = joined.iloc[:, 0].to_numpy(), joined.iloc[:, 1].to_numpy()
    variance = float(np.var(x))
    corr = float(np.corrcoef(x, y)[0, 1]) if variance > 0 and np.var(y) > 0 else float("nan")
    if not corr >= config.min_correlation:
        return 0.0, 1.0, months, corr
    raw_beta = float(np.cov(x, y, bias=True)[0, 1] / variance)
    beta = 1.0 + (1.0 - config.shrinkage) * (raw_beta - 1.0)
    beta = float(np.clip(beta, config.beta_bounds[0], config.beta_bounds[1]))
    alpha = (1.0 - config.shrinkage) * float(y.mean() - beta * x.mean())
    alpha = float(np.clip(alpha, -config.alpha_bound_monthly, config.alpha_bound_monthly))
    return alpha, beta, months, corr


def splice(
    segments: list[SegmentSeries],
    config: CalibrationConfig,
    asof: pd.Timestamp | None = None,
) -> Spliced:
    """Verkettet Segmente (bevorzugtes zuerst) zu einer Reihe.

    Es zählen nur Daten bis ``asof``; damit hängt das Ergebnis für einen Stichtag nie
    von späteren Daten ab.
    """
    cut = [
        SegmentSeries(
            s.id,
            (s.returns if asof is None else s.returns[s.returns.index <= asof]).dropna(),
            s.quality,
            s.backfill,
        )
        for s in segments
    ]
    cut = [s for s in cut if len(s.returns)]
    empty = pd.Series(dtype="float64")
    if not cut:
        return Spliced(empty, empty.astype("object"), empty.astype("object"), empty.astype(bool))
    first = cut[0]
    returns = first.returns.copy()
    segment = pd.Series(first.id, index=returns.index, dtype="object")
    quality = pd.Series(first.quality, index=returns.index, dtype="object")
    backfill = pd.Series(first.backfill, index=returns.index, dtype=bool)
    calibrations: list[Calibration] = []
    newer_id = first.id
    for older in cut[1:]:
        seam = returns.index.min()
        part = older.returns[older.returns.index < seam]
        if part.empty:
            continue
        alpha, beta, months, corr = calibrate(returns, older.returns, seam, config)
        applied = months >= config.min_months and corr >= config.min_correlation
        calibrations.append(
            Calibration(older.id, newer_id, str(seam.date()), months, alpha, beta, corr, applied)
        )
        adjusted = alpha + beta * part
        returns = pd.concat([adjusted, returns])
        segment = pd.concat([pd.Series(older.id, index=part.index, dtype="object"), segment])
        quality = pd.concat([pd.Series(older.quality, index=part.index, dtype="object"), quality])
        backfill = pd.concat([pd.Series(True, index=part.index, dtype=bool), backfill])
        newer_id = older.id
    return Spliced(returns.sort_index(), segment, quality, backfill, calibrations)
