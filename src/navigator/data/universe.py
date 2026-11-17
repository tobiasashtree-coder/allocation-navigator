"""Aufbau des Anlageuniversums: monatliche Total-Return-Reihen aller Assetklassen.

Aus den gespeicherten Rohdaten entsteht je Assetklasse eine Monatsreihe in der
gewählten Basiswährung, mit Qualitätskennzeichen und Herkunft je Monat sowie dem
getrennt ausgewiesenen Währungseinfluss.

Point-in-Time: ``build(base, asof=t)`` verwendet ausschließlich Beobachtungen bis t.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from navigator.config import AppConfig, AssetClass, Segment
from navigator.data.backfill import Calibration, SegmentSeries, Spliced, splice
from navigator.data.cache import SeriesCache
from navigator.data.fx import (
    FxRates,
    build_cash_returns,
    build_fx_rates,
    hedged_return,
    to_month_end,
)
from navigator.data.providers import Provider
from navigator.data.synthetic import (
    blend_returns,
    synthetic_bond_returns,
    synthetic_linker_returns,
)

log = logging.getLogger(__name__)


def apply_cost_schedule(returns: pd.Series, segment: Segment) -> pd.Series:
    """Zieht je Monat ein Zwölftel des jeweils gültigen Jahresabschlags ab.

    Der Abschlag hängt nur vom Kalendermonat ab, nie von Renditen; er ist damit
    stichtagsneutral.
    """
    deduction = pd.Series(0.0, index=returns.index)
    for step in sorted(segment.cost_schedule, key=lambda c: c.start):
        begin = pd.Timestamp(f"{step.start}-01")
        deduction[returns.index >= begin] = step.annual / 12.0
    return returns - deduction


class SeriesLoader:
    """Liest Reihen aus dem Cache und wählt je Reihe die Quelle mit der höchsten Priorität."""

    def __init__(self, cache: SeriesCache, providers: dict[str, Provider]) -> None:
        self.cache = cache
        self.providers = providers
        self.used: dict[str, str] = {}
        self._memo: dict[tuple[str, str], pd.DataFrame | None] = {}

    def _order(self, symbols: dict[str, str]) -> list[tuple[str, str]]:
        def priority(name: str) -> int:
            return self.providers[name].config.priority if name in self.providers else 10_000

        return sorted(symbols.items(), key=lambda item: (priority(item[0]), item[0]))

    def frame(self, symbols: dict[str, str]) -> tuple[pd.DataFrame, str] | None:
        """Gespeicherte Reihe der bestplatzierten Quelle, die Daten hat."""
        for name, symbol in self._order(symbols):
            key = (name, symbol)
            if key not in self._memo:
                cached = self.cache.read(name, symbol)
                self._memo[key] = None if cached is None else cached[0]
            data = self._memo[key]
            if data is not None and not data.empty:
                self.used[symbol] = name
                return data, name
        return None

    def series(self, symbols: dict[str, str], kind: str = "") -> pd.Series | None:
        """Werte einer Reihe, nach Beobachtungsdatum indiziert (jüngster Datenstand)."""
        found = self.frame(symbols)
        if found is None:
            return None
        data = found[0]
        if "known_from" in data.columns:
            data = data.sort_values(["obs_date", "known_from"]).drop_duplicates(
                "obs_date", keep="last"
            )
        return pd.Series(
            data["value"].to_numpy(), index=pd.DatetimeIndex(data["obs_date"]), name=kind
        )


@dataclass
class UniverseData:
    """Das Universum für eine Basiswährung und einen Stichtag."""

    base: str
    asof: pd.Timestamp | None
    returns: pd.DataFrame
    currency_effect: pd.DataFrame
    quality: pd.DataFrame
    segment: pd.DataFrame
    backfill: pd.DataFrame
    calibrations: dict[str, list[Calibration]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def coverage(self) -> pd.DataFrame:
        """Übersicht je Assetklasse: Zeitraum, Monate, Anteil je Qualitätskennzeichen."""
        rows = []
        for asset in self.returns.columns:
            series = self.returns[asset].dropna()
            if series.empty:
                rows.append({"asset": asset, "start": "", "end": "", "months": 0})
                continue
            quality = self.quality[asset].reindex(series.index)
            backfill = self.backfill[asset].reindex(series.index).fillna(False).astype(bool)
            proxy_start = series.index[~backfill.to_numpy()].min() if (~backfill).any() else None
            rows.append(
                {
                    "asset": asset,
                    "start": series.index.min().strftime("%Y-%m"),
                    "end": series.index.max().strftime("%Y-%m"),
                    "months": len(series),
                    "proxy_start": "" if proxy_start is None else proxy_start.strftime("%Y-%m"),
                    "original": float((quality == "original").mean()),
                    "proxy": float((quality == "proxy").mean()),
                    "synthetisch": float((quality == "synthetisch").mean()),
                    "backfill": float(backfill.mean()),
                    "return_pa": float((1.0 + series).prod() ** (12.0 / len(series)) - 1.0),
                    "vol_pa": float(series.std() * 12.0**0.5),
                }
            )
        if not rows:
            return pd.DataFrame(columns=["start", "end", "months"]).rename_axis("asset")
        return pd.DataFrame(rows).set_index("asset")


class UniverseBuilder:
    """Baut das Universum aus Konfiguration und gespeicherten Rohdaten."""

    def __init__(self, config: AppConfig, loader: SeriesLoader) -> None:
        self.config = config
        self.loader = loader

    # ----------------------------------------------------------- Segmentrenditen
    def _price_returns(
        self, symbols: dict[str, str], asof: pd.Timestamp | None
    ) -> pd.Series | None:
        raw = self.loader.series(symbols, "price")
        if raw is None:
            return None
        monthly = to_month_end(raw, asof)
        returns = monthly.pct_change(fill_method=None).dropna()
        return returns if len(returns) else None

    def _monthly_returns(
        self, symbols: dict[str, str], asof: pd.Timestamp | None
    ) -> pd.Series | None:
        raw = self.loader.series(symbols, "returns")
        if raw is None:
            return None
        out = raw.dropna().sort_index()
        out.index = pd.DatetimeIndex(out.index).normalize() + pd.offsets.MonthEnd(0)
        out = out[~out.index.duplicated(keep="last")]
        return out if asof is None else out[out.index <= asof]

    def segment_returns(
        self, segment: Segment, base: str, cash: pd.DataFrame, asof: pd.Timestamp | None
    ) -> pd.Series | None:
        """Monatsrenditen eines Segments in seiner Notierungswährung, nach Kostenabschlag."""
        returns = self._raw_segment_returns(segment, base, cash, asof)
        if returns is None or not segment.cost_schedule:
            return returns
        return apply_cost_schedule(returns, segment)

    def _raw_segment_returns(
        self, segment: Segment, base: str, cash: pd.DataFrame, asof: pd.Timestamp | None
    ) -> pd.Series | None:
        kind = segment.kind
        if kind in ("price", "level"):
            returns = self._price_returns(segment.symbols, asof)
            if returns is None and segment.fallback_symbols:
                returns = self._price_returns(segment.fallback_symbols, asof)
            return returns
        if kind == "returns":
            return self._monthly_returns(segment.symbols, asof)
        if kind in ("synthetic_bond", "synthetic_linker"):
            yields = self.loader.series(segment.yield_symbols, "yield")
            if yields is None or segment.maturity_years is None:
                return None
            monthly = to_month_end(yields, asof)
            if kind == "synthetic_bond":
                return synthetic_bond_returns(monthly, segment.maturity_years)
            cpi = self.loader.series(segment.cpi_symbols, "macro")
            if cpi is None:
                return None
            return synthetic_linker_returns(
                monthly, to_month_end(cpi, asof), segment.maturity_years
            )
        if kind == "blend":
            parts = []
            for component in segment.components:
                series = self._monthly_returns(component.symbols, asof)
                if series is None:
                    return None
                parts.append((series, component.weight))
            return blend_returns(parts)
        if kind == "excess_plus_cash":
            excess = self._monthly_returns(segment.symbols, asof)
            currency = base if segment.currency == "BASE" else segment.currency
            if excess is None or currency not in cash.columns:
                return None
            joined = pd.concat([excess, cash[currency]], axis=1, join="inner").dropna()
            return joined.iloc[:, 0] + joined.iloc[:, 1]
        if kind == "cash":
            return cash[base].dropna() if base in cash.columns else None
        raise ValueError(f"Unbekannte Segmentart {kind}")

    def _to_base(
        self,
        local: pd.Series,
        currency: str,
        base: str,
        hedged: bool,
        fx: FxRates,
        cash: pd.DataFrame,
    ) -> tuple[pd.Series, pd.Series] | None:
        """Rendite in Basiswährung und der darin enthaltene Währungseinfluss."""
        if currency == base:
            return local, pd.Series(0.0, index=local.index)
        if hedged:
            if base not in cash.columns or currency not in cash.columns:
                return None
            total = hedged_return(local, cash[base], cash[currency])
        else:
            if not (fx.has(base) and fx.has(currency)):
                return None
            total = fx.convert_returns(local, currency, base)
        effect = (total - local.reindex(total.index)).rename("currency")
        return total, effect

    # --------------------------------------------------------------- Universum
    def build(
        self, base: str | None = None, asof: pd.Timestamp | str | None = None
    ) -> UniverseData:
        """Baut alle eingeschalteten Assetklassen für ``base`` zum Stichtag ``asof``."""
        base = base or self.config.currency.base
        if base not in self.config.currency.supported:
            raise ValueError(f"Basiswährung {base} wird nicht unterstützt")
        stamp = None if asof is None else pd.Timestamp(asof).normalize()
        fx = build_fx_rates(self.config.currency, self.loader.series, stamp)
        cash = build_cash_returns(self.config.currency, self.loader.series, stamp)
        issues: list[str] = []
        if base not in cash.columns:
            issues.append(
                f"Kurzfristzins für {base} fehlt: Cash und Währungssicherung nicht möglich"
            )
        columns: dict[str, dict[str, pd.Series]] = {
            name: {} for name in ("returns", "currency_effect", "quality", "segment", "backfill")
        }
        calibrations: dict[str, list[Calibration]] = {}
        for key, asset in self.config.universe.enabled_assets().items():
            result = self._build_asset(key, asset, base, fx, cash, stamp, issues)
            if result is None:
                issues.append(f"{key}: keine Daten in {base}")
                continue
            spliced, effect = result
            columns["returns"][key] = spliced.returns
            columns["currency_effect"][key] = effect.reindex(spliced.returns.index).fillna(0.0)
            columns["quality"][key] = spliced.quality
            columns["segment"][key] = spliced.segment
            columns["backfill"][key] = spliced.backfill
            calibrations[key] = spliced.calibrations
        order = list(self.config.universe.enabled_assets())
        frames = {
            name: pd.DataFrame(data).reindex(columns=[k for k in order if k in data]).sort_index()
            for name, data in columns.items()
        }
        return UniverseData(
            base=base,
            asof=stamp,
            returns=frames["returns"],
            currency_effect=frames["currency_effect"],
            quality=frames["quality"],
            segment=frames["segment"],
            backfill=frames["backfill"],
            calibrations=calibrations,
            issues=issues,
        )

    def _build_asset(
        self,
        key: str,
        asset: AssetClass,
        base: str,
        fx: FxRates,
        cash: pd.DataFrame,
        asof: pd.Timestamp | None,
        issues: list[str],
    ) -> tuple[Spliced, pd.Series] | None:
        series: list[SegmentSeries] = []
        effects: dict[str, pd.Series] = {}
        for segment in asset.segments:
            local = self.segment_returns(segment, base, cash, asof)
            if local is None or local.empty:
                issues.append(f"{key}/{segment.id}: keine Daten")
                continue
            currency = base if segment.currency == "BASE" else segment.currency
            converted = self._to_base(local, currency, base, asset.hedged, fx, cash)
            if converted is None:
                issues.append(f"{key}/{segment.id}: Umrechnung {currency}->{base} nicht möglich")
                continue
            total, effect = converted
            series.append(SegmentSeries(segment.id, total, segment.quality, segment.backfill))
            effects[segment.id] = effect
        if not series:
            return None
        spliced = splice(series, self.config.universe.calibration, asof)
        if spliced.returns.empty:
            return None
        effect = pd.Series(0.0, index=spliced.returns.index)
        for segment_id, values in effects.items():
            months = spliced.segment.index[spliced.segment == segment_id]
            effect.loc[months] = values.reindex(months).fillna(0.0).to_numpy()
        return spliced, effect
