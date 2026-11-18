"""Daten für das Dashboard: Schnappschüsse der Kommandozeile und Szenarien.

Alle Zahlen kommen aus dem Paket; das Dashboard rechnet nichts selbst.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from navigator.config import QUADRANTS, AppConfig, load_config
from navigator.paths import ProjectPaths, project_paths
from navigator.reporting.views import View, recommendation_view, snapshot_path


@dataclass
class Context:
    """Konfiguration, Pfade und geladene Ergebnisse."""

    config: AppConfig
    paths: ProjectPaths

    @property
    def demo(self) -> bool:
        return self.paths.demo

    def view(self, name: str) -> View | None:
        path = snapshot_path(self.paths.reports, name)
        return View.load(path) if path.exists() else None

    def csv(self, name: str, **kwargs: object) -> pd.DataFrame | None:
        path = self.paths.reports / name
        if not path.exists() or path.stat().st_size == 0:
            return None
        return pd.read_csv(path, **kwargs)

    def markdown(self, name: str) -> str | None:
        path = self.paths.reports / name
        return path.read_text(encoding="utf-8") if path.exists() else None


def context_from_env() -> Context:
    """Kontext aus ``NAVIGATOR_ROOT`` und ``NAVIGATOR_DEMO`` (von ``navigator dashboard``)."""
    root = os.environ.get("NAVIGATOR_ROOT")
    demo = os.environ.get("NAVIGATOR_DEMO", "0") == "1"
    paths = project_paths(Path(root) if root else None, demo=demo)
    return Context(load_config(paths.config), paths)


def regime_history(ctx: Context) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Historie von Methode A (global) und Methode B samt Vergleich."""
    a = ctx.csv("regime_a_history.csv", index_col=0, parse_dates=True)
    b = ctx.csv("regime_b_history.csv", header=[0, 1], index_col=0)
    if b is not None:
        b.index = pd.to_datetime(b.index, errors="coerce")
        b = b[b.index.notna()]
    return a, b


def agreement(b_history: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """Übereinstimmungsquote und Kreuztabelle A (Zeilen) gegen B (Spalten)."""
    a = b_history[("A", "regime")]
    b = b_history[("B", "regime")]
    both = pd.DataFrame({"A": a, "B": b}).dropna()
    rate = float((both["A"] == both["B"]).mean()) if len(both) else float("nan")
    table = pd.crosstab(both["A"], both["B"]).reindex(
        index=list(QUADRANTS), columns=[*QUADRANTS, "financial_stress"], fill_value=0
    )
    return rate, table.loc[:, (table != 0).any()]


def scenario(
    ctx: Context,
    method_overlay_strength: float,
    base_method: str,
    tracking_error: float,
    turnover: float,
    base_currency: str,
    simulations: int = 100,
) -> View:
    """Rechnet eine Empfehlung mit geänderten Einstellungen; die Konfiguration bleibt unberührt.

    Das Ergebnis trägt das Kennzeichen „Szenario“ (9.4).
    """
    from navigator.allocation.recommend import load_and_recommend

    config = ctx.config.model_copy(deep=True)
    config.debt_cycle.overlay_strength = method_overlay_strength
    target = config.base.outputs["target_weights"]
    target["tracking_error_max"] = tracking_error
    target["turnover_max_quarter"] = turnover
    config.currency.base = base_currency
    rec = load_and_recommend(config, ctx.paths, None, True, None, simulations, base_method)
    label = (
        f"Overlay-Stärke {method_overlay_strength:.2f}, Basis {base_method}, "
        f"Tracking Error {tracking_error:.1%}, Umschlag {turnover:.0%}, Währung {base_currency}"
    )
    return recommendation_view(rec, config, scenario=label)
