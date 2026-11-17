"""Hilfen für Look-ahead-Tests.

Arbeitsregel: Jede Funktion, die Daten für ein Datum t liefert, bekommt einen Test, der
beweist, dass keine Daten nach t einfließen. Das Prinzip ist immer gleich: Alle Daten
nach t werden verändert; das Ergebnis für t darf sich dadurch nicht ändern.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def perturb_frame_after(
    frame: pd.DataFrame, when: pd.Timestamp, rng: np.random.Generator
) -> pd.DataFrame:
    """Verändert alle Zeilen, die erst nach ``when`` beobachtet oder bekannt wurden.

    Zeilen mit ``obs_date > when`` bzw. ``known_from > when`` erhalten zufällig stark
    veränderte Werte; alles bis ``when`` bleibt unverändert.
    """
    out = frame.copy()
    later = pd.to_datetime(out["obs_date"]) > when
    if "known_from" in out.columns:
        later = later | (pd.to_datetime(out["known_from"]) > when)
    count = int(later.sum())
    for column in ("value", "raw"):
        if column in out.columns and count:
            factors = rng.uniform(0.2, 5.0, count)
            out.loc[later, column] = out.loc[later, column].to_numpy() * factors + rng.normal(
                0.0, 1.0, count
            )
    return out


def perturb_parquet_tree(source: Path, target: Path, when: pd.Timestamp, seed: int = 0) -> int:
    """Kopiert alle Parquet-Dateien nach ``target`` und verändert darin Daten nach ``when``.

    Begleitdateien (JSON) werden unverändert kopiert. Liefert die Zahl veränderter Dateien.
    """
    rng = np.random.default_rng(seed)
    changed = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".parquet":
            destination.write_bytes(path.read_bytes())
            continue
        frame = pd.read_parquet(path)
        perturbed = perturb_frame_after(frame, when, rng)
        if not perturbed.equals(frame):
            changed += 1
        perturbed.to_parquet(destination, index=False)
    return changed


def assert_no_lookahead(
    compute: Callable[[Any, pd.Timestamp], pd.DataFrame | pd.Series],
    original: Any,
    perturbed: Any,
    when: pd.Timestamp,
) -> None:
    """Prüft, dass ``compute(daten, when)`` für Original und veränderte Daten gleich ist."""
    expected = compute(original, when)
    actual = compute(perturbed, when)
    if isinstance(expected, pd.Series):
        pd.testing.assert_series_equal(expected, actual)
    else:
        pd.testing.assert_frame_equal(expected, actual)
