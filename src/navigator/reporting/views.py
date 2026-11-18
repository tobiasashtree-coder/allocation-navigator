"""Gemeinsame Ansichten für Kommandozeile, Bericht und Dashboard (Spezifikation 9).

Eine Empfehlung bzw. ein Backtest wird einmal in Tabellen übersetzt (``View``). Die
Kommandozeile schreibt diese Tabellen als CSV und als Schnappschuss
(``reports/snapshot/*.json``); das Dashboard liest den Schnappschuss oder rechnet ein
Szenario über dieselbe Funktion. So zeigen beide dieselben Zahlen (Abnahme M7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from navigator.allocation.base import risk_contributions
from navigator.allocation.recommend import QUADRANT_LABELS, Recommendation
from navigator.config import AppConfig

SNAPSHOT_DIR = "snapshot"


@dataclass
class View:
    """Tabellen und Kennwerte einer Auswertung."""

    kind: str
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        """Schreibt den Schnappschuss als JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": self.kind,
            "values": self.values,
            "tables": {
                k: v.to_json(orient="split", double_precision=15, date_format="iso")
                for k, v in self.tables.items()
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> View:
        """Liest einen Schnappschuss."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        tables = {
            k: pd.read_json(StringIO(v), orient="split", precise_float=True)
            for k, v in payload["tables"].items()
        }
        return cls(payload["kind"], tables, payload["values"])


def snapshot_path(reports: Path, name: str) -> Path:
    """Pfad eines Schnappschusses im Berichtsordner."""
    return reports / SNAPSHOT_DIR / f"{name}.json"


def recommendation_view(rec: Recommendation, config: AppConfig, scenario: str = "") -> View:
    """Alle Tabellen einer Empfehlung."""
    names = {k: a.name for k, a in config.universe.assets.items()}
    tables: dict[str, pd.DataFrame] = {}
    targets = pd.DataFrame({k: v.target.weights for k, v in rec.variants.items()})
    targets["base"] = rec.base.weights
    tables["targets"] = targets.fillna(0.0).rename_axis("asset")
    for key, v in rec.variants.items():
        assets = list(v.lights.index)
        tables[f"detail:{key}"] = pd.DataFrame(
            {
                "Klasse": [names.get(a, a) for a in assets],
                "Ampel": v.lights.reindex(assets).to_numpy(),
                "Signal": v.signal.reindex(assets).to_numpy(),
                "Tilt_pp": v.tilt_pp.reindex(assets).to_numpy(),
                "Basis": rec.base.weights.reindex(assets).to_numpy(),
                "Ziel": v.target.weights.reindex(assets).to_numpy(),
                "Band_low": v.target.low.reindex(assets).to_numpy(),
                "Band_high": v.target.high.reindex(assets).to_numpy(),
            },
            index=pd.Index(assets, name="asset"),
        )
        tables[f"parts:{key}"] = v.parts.rename_axis("asset")
    probs = pd.DataFrame({k: v.probs for k, v in rec.variants.items() if "+" not in k})
    tables["probs"] = probs.rename(index=QUADRANT_LABELS).rename_axis("Quadrant")
    rc = risk_contributions(rec.base.weights, rec.base.cov)
    tables["base"] = pd.DataFrame(
        {"Gewicht": rec.base.weights, "Risikobeitrag": rc.reindex(rec.base.weights.index)}
    ).rename_axis("asset")
    tables["regime_returns"] = rec.regime_returns.rename(columns=QUADRANT_LABELS).rename_axis(
        "asset"
    )
    tables["currency"] = rec.currency.rename_axis("asset")
    first = next(iter(rec.variants.values()))
    values = {
        "asof": str(rec.asof.date()),
        "base_currency": config.currency.base,
        "config_hash": config.config_hash,
        "conviction": first.conviction,
        "base_volatility": rec.base.volatility(),
        "shrinkage": rec.base.shrinkage,
        "currency_risk": rec.currency_risk,
        "exposure": rec.usd_exposure,
        "checks": {k: v.target.checks for k, v in rec.variants.items()},
        "tracking_error": {k: v.target.tracking_error for k, v in rec.variants.items()},
        "turnover": {k: v.target.turnover for k, v in rec.variants.items()},
        "active_share": {
            k: 0.5 * float((v.target.weights - rec.base.weights).abs().sum())
            for k, v in rec.variants.items()
        },
        "notes": rec.notes,
        "scenario": scenario,
    }
    return View("recommend", tables, values)


def backtest_view(result: Any, config: AppConfig) -> View:
    """Tabellen eines Backtests: Monatsrenditen je Strategie, Kennzahlen, Placebo."""
    from navigator.backtest.run import _period_table

    returns = pd.DataFrame({k: s.returns for k, s in result.strategies.items()})
    p = config.backtest.periods
    tables = {
        "returns": returns.rename_axis("date"),
        "metrics_test": _period_table(result, str(p.get("test_start", "2008-01")), None),
        "metrics_dev": _period_table(result, None, str(p.get("development_end", "2007-12"))),
        "metrics_all": _period_table(result, None, None),
        "sensitivity": result.sensitivity,
        "placebo": pd.DataFrame({"Sharpe": result.placebo_sharpes}),
        "regimes": result.regimes.rename("regime").to_frame().rename_axis("date"),
    }
    values = {
        "placebo_p": result.placebo_p,
        "placebo_reference": result.placebo_reference,
        "deflated": result.deflated,
        "n_trials": result.n_trials,
        "start": str(result.start.date()),
        "config_hash": config.config_hash,
    }
    return View("backtest", tables, values)


def detail_display(view: View, variant: str) -> pd.DataFrame:
    """Tabelle „Ampel, Tilts, Zielgewichte“ in Prozent, wie im Dashboard angezeigt."""
    frame = view.tables[f"detail:{variant}"].copy()
    for col in ("Signal", "Basis", "Ziel", "Band_low", "Band_high"):
        frame[col] = frame[col] * 100
    return frame.rename(
        columns={
            "Signal": "Signal % p. a.",
            "Tilt_pp": "Tilt Pp.",
            "Basis": "Basis %",
            "Ziel": "Ziel %",
            "Band_low": "Band von %",
            "Band_high": "Band bis %",
        }
    )


def allocation_table(view: View, variant: str, amount: float | None = None) -> pd.DataFrame:
    """Empfohlene Gewichtung je Klasse zum Stichtag, absteigend; optional als Betrag.

    Gleiche Zahlen wie ``recommend_targets.csv`` (Spalte ``variant``).
    """
    detail = view.tables[f"detail:{variant}"]
    frame = pd.DataFrame(
        {
            "Klasse": detail["Klasse"],
            "Gewicht %": detail["Ziel"] * 100,
            "Basis %": detail["Basis"] * 100,
            "Abweichung Pp.": (detail["Ziel"] - detail["Basis"]) * 100,
            "Ampel": detail["Ampel"],
        },
        index=detail.index,
    ).sort_values("Gewicht %", ascending=False)
    if amount is not None and amount > 0:
        frame.insert(2, "Betrag", frame["Gewicht %"] / 100 * amount)
    return frame
