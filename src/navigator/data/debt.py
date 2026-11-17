"""Rohreihen des Schuldenstress-Scores (Spezifikation 6.2): Schlüssel und Symbole.

Schlüssel im Point-in-Time-Speicher:

- ``debt.<Land>.<Eingang>`` für die Länder des Tools,
- ``debt.panel.<ISO3>.<Eingang>`` für das JST-Referenzpanel (auch für Länder des Tools,
  die im Panel liegen; so wird jede JST-Reihe nur einmal geladen),
- ``debt.global.<Eingang>`` für weltweite Reihen.
"""

from __future__ import annotations

from dataclasses import dataclass

from navigator.config import AppConfig, DebtInput


@dataclass(frozen=True)
class DebtSeriesSpec:
    """Eine konkrete Rohreihe des Scores."""

    key: str
    owner: str
    name: str
    source: str
    symbol: str
    item: DebtInput


def input_key(owner: str, name: str, item: DebtInput) -> str:
    """Schlüssel einer Rohreihe; ``owner`` ist Länderkürzel oder ISO3 (Panel)."""
    if item.global_series:
        return f"debt.global.{name}"
    if item.panel:
        return f"debt.panel.{owner}.{name}"
    return f"debt.{owner}.{name}"


def debt_series_specs(config: AppConfig) -> list[DebtSeriesSpec]:
    """Alle Rohreihen des Scores laut ``debt_cycle.yaml``."""
    score = config.debt_cycle.score
    specs: list[DebtSeriesSpec] = []
    for name, item in score.inputs.items():
        if item.global_series:
            specs.append(
                DebtSeriesSpec(
                    input_key("", name, item), "global", name, item.source, item.symbol, item
                )
            )
        elif item.panel:
            panel = list(dict.fromkeys(score.panel))
            for iso3 in panel:
                panel_symbol: str = item.symbol.format(iso2="", iso3=iso3)
                specs.append(
                    DebtSeriesSpec(
                        input_key(iso3, name, item), iso3, name, item.source, panel_symbol, item
                    )
                )
        else:
            for country in score.countries:
                symbol = item.symbol_for(country, score.iso3[country])
                if symbol:
                    specs.append(
                        DebtSeriesSpec(
                            input_key(country, name, item),
                            country,
                            name,
                            item.source,
                            symbol,
                            item,
                        )
                    )
    return specs
