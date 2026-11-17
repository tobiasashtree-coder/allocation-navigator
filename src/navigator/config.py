"""Konfigurationsschemas (pydantic) und Laden der YAML-Dateien.

Alle Parameter des Tools stehen in ``config/*.yaml`` und werden hier validiert.
Der Konfigurations-Hash geht in jedes Laufprotokoll ein, damit jeder Lauf
reproduzierbar einem Konfigurationsstand zugeordnet werden kann.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_FILES = (
    "universe.yaml",
    "sources.yaml",
    "indicators.yaml",
    "currency.yaml",
    "regime_map.yaml",
    "base.yaml",
    "debt_cycle.yaml",
    "backtest.yaml",
)

Quality = Literal["original", "proxy", "synthetisch"]
SeriesKind = Literal["price", "level", "returns", "yield", "rate", "fx", "macro"]
SegmentKind = Literal[
    "price",
    "level",
    "returns",
    "synthetic_bond",
    "synthetic_linker",
    "blend",
    "excess_plus_cash",
    "cash",
]
QUADRANTS = ("disinflationary_boom", "reflation", "deflationary_bust", "stagflation")


class StrictModel(BaseModel):
    """Basis für alle Schemas: unbekannte Schlüssel sind Fehler (Tippfehler fallen auf)."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- Quellen


class SourceConfig(StrictModel):
    """Eine Datenquelle hinter der gemeinsamen Provider-Schnittstelle."""

    enabled: bool = True
    priority: int = Field(default=100, description="Kleinere Zahl = höhere Priorität")
    paid: bool = False
    api_key_env: str | None = None
    requires_key: bool = False
    rate_limit_per_min: float | None = None
    license: str = ""
    license_url: str = ""
    commercial_use: bool = False
    note: str = ""
    options: dict[str, Any] = Field(default_factory=dict)


class CacheConfig(StrictModel):
    """Einstellungen des Rohdaten-Caches."""

    max_age_hours: float = 20.0
    price_overlap_days: int = 15
    static_max_age_days: int = 30


class SourcesConfig(StrictModel):
    """Inhalt von ``sources.yaml``."""

    cross_check_tolerance: float = 0.005
    cache: CacheConfig = Field(default_factory=CacheConfig)
    sources: dict[str, SourceConfig]


# ------------------------------------------------------------------------- Universum


class BlendComponent(StrictModel):
    """Bestandteil einer gewichteten Mischung von Renditereihen."""

    symbols: dict[str, str]
    weight: float


class Segment(StrictModel):
    """Ein Abschnitt der Historie einer Assetklasse (Proxy oder Backfill)."""

    id: str
    kind: SegmentKind
    quality: Quality
    backfill: bool = False
    currency: str = "USD"
    expected_start: str | None = None
    symbols: dict[str, str] = Field(default_factory=dict)
    fallback_symbols: dict[str, str] = Field(default_factory=dict)
    distributing: bool = False
    yield_symbols: dict[str, str] = Field(default_factory=dict)
    maturity_years: float | None = None
    cpi_symbols: dict[str, str] = Field(default_factory=dict)
    components: list[BlendComponent] = Field(default_factory=list)
    verified: bool = False
    note: str = ""

    @model_validator(mode="after")
    def _check_kind(self) -> Segment:
        if self.kind in ("price", "level", "returns", "excess_plus_cash") and not self.symbols:
            raise ValueError(f"Segment {self.id}: 'symbols' fehlt für kind={self.kind}")
        synthetic = self.kind in ("synthetic_bond", "synthetic_linker")
        if synthetic and (not self.yield_symbols or self.maturity_years is None):
            raise ValueError(f"Segment {self.id}: 'yield_symbols' und 'maturity_years' nötig")
        if self.kind == "synthetic_linker" and not self.cpi_symbols:
            raise ValueError(f"Segment {self.id}: 'cpi_symbols' fehlt")
        if self.kind == "blend":
            total = sum(c.weight for c in self.components)
            if not self.components or abs(total - 1.0) > 1e-9:
                raise ValueError(f"Segment {self.id}: Gewichte der Mischung müssen 1 ergeben")
        return self


class AssetClass(StrictModel):
    """Eine Assetklasse des Anlageuniversums."""

    name: str
    group: Literal["Aktien", "Anleihen", "Sachwerte", "Diversifikatoren", "Liquidität"]
    role: str
    optional: bool = False
    enabled: bool = True
    hedged: bool = False
    max_weight: float | None = None
    in_regime_features: bool = True
    fx_exposure: dict[str, float] = Field(default_factory=dict)
    segments: list[Segment]

    @model_validator(mode="after")
    def _check(self) -> AssetClass:
        if not self.segments:
            raise ValueError(f"{self.name}: mindestens ein Segment nötig")
        if self.fx_exposure and abs(sum(self.fx_exposure.values()) - 1.0) > 1e-6:
            raise ValueError(f"{self.name}: fx_exposure muss sich zu 1 summieren")
        return self


class ReferenceSeries(StrictModel):
    """Vergleichsreihe außerhalb des Universums (z. B. NAV-Näherung privater Infrastruktur)."""

    name: str
    kind: SeriesKind = "price"
    currency: str = "USD"
    symbols: dict[str, str]
    purpose: str = ""


class CalibrationConfig(StrictModel):
    """Gleitende Kalibrierung an der Naht zwischen Backfill und Proxy."""

    window_months: int = 36
    min_months: int = 12
    shrinkage: float = 0.5
    min_correlation: float = 0.6
    beta_bounds: tuple[float, float] = (0.5, 2.0)
    alpha_bound_monthly: float = 0.0


class UniverseConfig(StrictModel):
    """Inhalt von ``universe.yaml``."""

    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    assets: dict[str, AssetClass]
    references: dict[str, ReferenceSeries] = Field(default_factory=dict)

    def enabled_assets(self) -> dict[str, AssetClass]:
        """Alle eingeschalteten Assetklassen."""
        return {k: a for k, a in self.assets.items() if a.enabled}


# --------------------------------------------------------------------------- Währung


class FxSeries(StrictModel):
    """Eine Wechselkursreihe mit ihrer Notierungsform."""

    currency: str
    quote: Literal["per_eur", "usd_per_unit", "per_usd", "dem_per_usd"]
    symbols: dict[str, str]
    note: str = ""


class RateSegment(StrictModel):
    """Abschnitt einer Kurzfristzins-Historie (Prozent p. a.)."""

    id: str
    symbols: dict[str, str]
    note: str = ""


class CurrencyConfig(StrictModel):
    """Inhalt von ``currency.yaml``."""

    base: str = "EUR"
    supported: list[str] = Field(default_factory=lambda: ["EUR", "USD", "CHF", "GBP"])
    dem_per_eur: float = 1.95583
    fx_series: list[FxSeries]
    short_rates: dict[str, list[RateSegment]]
    scenario_shock: float = 0.10

    @model_validator(mode="after")
    def _check(self) -> CurrencyConfig:
        if self.base not in self.supported:
            raise ValueError("Basiswährung muss in 'supported' enthalten sein")
        missing = [c for c in self.supported if c not in self.short_rates]
        if missing:
            raise ValueError(f"Kurzfristzinsen fehlen für: {missing}")
        return self


# ------------------------------------------------------------------------ Indikatoren


class PublicationLag(StrictModel):
    """Konservative Veröffentlichungsverzögerung nach Periodenende."""

    months: int = 0
    days: int = 0


class Indicator(StrictModel):
    """Ein Makro- oder Marktindikator."""

    name: str
    region: str
    axis: Literal["growth", "inflation", "credit_cycle", "debt_cycle", "market"]
    symbols: dict[str, str]
    frequency: Literal["D", "M", "Q", "A"] = "M"
    vintages: bool = False
    publication_lag: PublicationLag = Field(default_factory=PublicationLag)
    change: Literal["pct", "diff", "level", "core_momentum"] = "pct"
    invert: bool = False
    verified: bool = False
    note: str = ""


class IndicatorDefaults(StrictModel):
    """Gemeinsame Transformation (Abschnitt 4.1 der Spezifikation)."""

    change_months: int = 6
    zscore_window_months: int = 120
    zscore_min_months: int = 60
    clip: float = 3.0


class IndicatorsConfig(StrictModel):
    """Inhalt von ``indicators.yaml``."""

    defaults: IndicatorDefaults = Field(default_factory=IndicatorDefaults)
    region_weights: dict[str, float] = Field(default_factory=dict)
    indicators: dict[str, Indicator]


# -------------------------------------------------- spätere Meilensteine (festgeschrieben)


class RegimeRules(StrictModel):
    """Parameter der regelbasierten Regime-Erkennung (Abschnitt 4.2)."""

    logistic_k: float = 1.5
    neutral_band: float = 0.25
    confirm_months: int = 2
    switch_probability: float = 0.60


class RegimeMapConfig(StrictModel):
    """Inhalt von ``regime_map.yaml``: Erwartungsvektoren je Klasse und Quadrant."""

    status: str = "Entwurf"
    scale_note: str = ""
    rules: RegimeRules = Field(default_factory=RegimeRules)
    quadrants: dict[str, str]
    expectations: dict[str, dict[str, float]]

    @model_validator(mode="after")
    def _check(self) -> RegimeMapConfig:
        if set(self.quadrants) != set(QUADRANTS):
            raise ValueError(f"quadrants muss genau {QUADRANTS} enthalten")
        for asset, vec in self.expectations.items():
            if set(vec) != set(QUADRANTS):
                raise ValueError(f"{asset}: Erwartungsvektor braucht alle vier Quadranten")
        return self


class BaseAllocationConfig(StrictModel):
    """Inhalt von ``base.yaml``: Risikoparität über vier Umfeldkörbe (Abschnitt 7.1)."""

    method: Literal["risk_parity_baskets"] = "risk_parity_baskets"
    baskets: dict[str, list[str]]
    covariance: dict[str, Any]
    black_litterman: dict[str, Any]
    outputs: dict[str, Any]
    constraints: dict[str, Any]


class DebtCycleConfig(StrictModel):
    """Inhalt von ``debt_cycle.yaml``: manuelle Einschätzung und Overlay-Vektoren."""

    phases: list[str]
    lambda_by_phase: dict[str, float]
    overlay_strength: float = 1.0
    assessments: dict[str, dict[str, Any]]
    overlay_vectors: dict[str, dict[str, Any]]
    score: dict[str, Any] = Field(default_factory=dict)


class BacktestConfig(StrictModel):
    """Inhalt von ``backtest.yaml``: Zeiträume, Kosten, Restriktionen (Abschnitt 8)."""

    periods: dict[str, Any]
    rebalancing: dict[str, Any]
    costs_bps: dict[str, float]
    benchmarks: dict[str, Any]
    placebo: dict[str, Any]
    robustness: dict[str, Any]


class AppConfig(StrictModel):
    """Gesamte Konfiguration eines Laufs."""

    universe: UniverseConfig
    sources: SourcesConfig
    indicators: IndicatorsConfig
    currency: CurrencyConfig
    regime_map: RegimeMapConfig
    base: BaseAllocationConfig
    debt_cycle: DebtCycleConfig
    backtest: BacktestConfig
    config_hash: str = ""

    @model_validator(mode="after")
    def _cross_checks(self) -> AppConfig:
        assets = set(self.universe.assets)
        unknown = set(self.regime_map.expectations) - assets
        if unknown:
            raise ValueError(f"regime_map.yaml nennt unbekannte Assetklassen: {sorted(unknown)}")
        missing = assets - set(self.regime_map.expectations)
        if missing:
            raise ValueError(f"regime_map.yaml fehlt für: {sorted(missing)}")
        for basket, members in self.base.baskets.items():
            bad = set(members) - assets
            if bad:
                raise ValueError(f"base.yaml, Korb {basket}: unbekannte Klassen {sorted(bad)}")
        known_sources = set(self.sources.sources)
        for key, asset in self.universe.assets.items():
            for seg in asset.segments:
                used = (
                    set(seg.symbols)
                    | set(seg.fallback_symbols)
                    | set(seg.yield_symbols)
                    | set(seg.cpi_symbols)
                )
                for comp in seg.components:
                    used |= set(comp.symbols)
                bad_src = used - known_sources
                if bad_src:
                    raise ValueError(f"{key}/{seg.id}: unbekannte Quellen {sorted(bad_src)}")
        return self


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: YAML-Wurzel muss ein Objekt sein")
    return data


def config_hash(config_dir: Path) -> str:
    """SHA-256 über alle Konfigurationsdateien (Name und Inhalt, zeilenendeneutral)."""
    digest = hashlib.sha256()
    for name in CONFIG_FILES:
        path = config_dir / name
        digest.update(name.encode())
        if path.exists():
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def load_config(config_dir: Path) -> AppConfig:
    """Lädt und validiert alle YAML-Dateien aus ``config_dir``."""
    raw = {
        name.removesuffix(".yaml"): _load_yaml(config_dir / name)
        for name in CONFIG_FILES
        if (config_dir / name).exists()
    }
    missing = [n for n in CONFIG_FILES if n.removesuffix(".yaml") not in raw]
    if missing:
        raise FileNotFoundError(f"Konfigurationsdateien fehlen in {config_dir}: {missing}")
    return AppConfig(**raw, config_hash=config_hash(config_dir))
