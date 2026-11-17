"""Abläufe der Datenschicht: Abruf aller Reihen, Point-in-Time-Ablage, Snapshot, Validierung.

Die Kommandozeile ruft nur diese Funktionen auf. Fällt eine Quelle aus, greift die
nächste laut Priorität; das wird im Log und im Ergebnis vermerkt. Nie werden
stillschweigend falsche oder veraltete Daten verwendet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from navigator.config import AppConfig, PublicationLag
from navigator.data.cache import SeriesCache
from navigator.data.pit import PitStore
from navigator.data.providers import (
    Provider,
    ProviderError,
    SeriesRequest,
    build_providers,
    rank_providers,
)
from navigator.data.synthetic import check_against_fund
from navigator.data.universe import SeriesLoader, UniverseBuilder
from navigator.data.validate import (
    Finding,
    ValidationReport,
    check_dividends,
    check_gaps,
    check_jumps,
    check_splits,
    check_staleness,
    check_start,
    check_universe,
    cross_check,
    summarize_cross_check,
)
from navigator.http import HttpClient
from navigator.paths import ProjectPaths
from navigator.runlog import utc_now, write_run

log = logging.getLogger(__name__)

_SEGMENT_KIND = {
    "price": "price",
    "level": "level",
    "returns": "returns",
    "excess_plus_cash": "returns",
}


@dataclass(frozen=True)
class RawSpec:
    """Eine Rohreihe, die das Tool braucht."""

    key: str
    kind: str
    symbols: tuple[tuple[str, str], ...]
    cross_check: bool = False
    optional: bool = False
    vintages: bool = False
    pit: bool = False
    frequency: str = "D"
    lag_months: int = 0
    lag_days: int = 0
    expected_start: str | None = None
    distributing: bool = False
    historical: bool = False

    def symbol_map(self) -> dict[str, str]:
        """Symbole je Quelle."""
        return dict(self.symbols)

    def lag(self) -> PublicationLag:
        """Veröffentlichungsverzögerung."""
        return PublicationLag(months=self.lag_months, days=self.lag_days)


@dataclass
class FetchResult:
    """Ergebnis des Abrufs einer Rohreihe."""

    key: str
    kind: str
    status: str
    provider: str = ""
    symbol: str = ""
    rows: int = 0
    first_obs: str = ""
    last_obs: str = ""
    secondary: str = ""
    message: str = ""
    optional: bool = False


def _spec(key: str, kind: str, symbols: dict[str, str], **extra: object) -> RawSpec:
    return RawSpec(key=key, kind=kind, symbols=tuple(sorted(symbols.items())), **extra)  # type: ignore[arg-type]


def collect_specs(config: AppConfig) -> list[RawSpec]:
    """Alle Rohreihen aus Universum, Währungs- und Indikatorkonfiguration."""
    specs: list[RawSpec] = []
    for key, asset in config.universe.enabled_assets().items():
        for seg in asset.segments:
            prefix = f"asset.{key}.{seg.id}"
            if seg.kind in _SEGMENT_KIND:
                kind = _SEGMENT_KIND[seg.kind]
                specs.append(
                    _spec(
                        prefix,
                        kind,
                        seg.symbols,
                        cross_check=kind == "price",
                        expected_start=seg.expected_start,
                        distributing=seg.distributing,
                        historical=seg.backfill,
                    )
                )
                if seg.fallback_symbols:
                    specs.append(
                        _spec(f"{prefix}.fallback", kind, seg.fallback_symbols, optional=True)
                    )
            if seg.yield_symbols:
                specs.append(
                    _spec(
                        f"{prefix}.yield",
                        "yield",
                        seg.yield_symbols,
                        expected_start=seg.expected_start,
                        historical=seg.backfill,
                    )
                )
            if seg.cpi_symbols:
                specs.append(_spec(f"{prefix}.cpi", "macro", seg.cpi_symbols, frequency="M"))
            for i, component in enumerate(seg.components):
                specs.append(
                    _spec(f"{prefix}.c{i}", "returns", component.symbols, historical=seg.backfill)
                )
    for key, reference in config.universe.references.items():
        specs.append(_spec(f"reference.{key}", reference.kind, reference.symbols, optional=True))
    for entry in config.currency.fx_series:
        specs.append(
            _spec(
                f"fx.{entry.currency}.{entry.quote}",
                "fx",
                entry.symbols,
                historical=entry.quote == "dem_per_usd",
            )
        )
    for currency, segments in config.currency.short_rates.items():
        for position, segment in enumerate(segments):
            specs.append(
                _spec(
                    f"rate.{currency}.{segment.id}",
                    "rate",
                    segment.symbols,
                    historical=position > 0,
                )
            )
    for key, indicator in config.indicators.indicators.items():
        specs.append(
            _spec(
                f"indicator.{key}",
                "level" if indicator.frequency == "D" else "macro",
                indicator.symbols,
                vintages=indicator.vintages,
                pit=True,
                frequency=indicator.frequency,
                lag_months=indicator.publication_lag.months,
                lag_days=indicator.publication_lag.days,
            )
        )
    return specs


def make_cache(config: AppConfig, paths: ProjectPaths) -> SeriesCache:
    """Cache mit den Einstellungen aus ``sources.yaml``."""
    cache_cfg = config.sources.cache
    return SeriesCache(paths.raw, cache_cfg.max_age_hours, cache_cfg.price_overlap_days)


def make_providers(
    config: AppConfig, paths: ProjectPaths, http: HttpClient | None = None
) -> dict[str, Provider]:
    """Provider laut Konfiguration; im Demo-Modus synthetische Quellen."""
    return build_providers(config.sources, paths, http, demo=paths.demo)


def _fetch_spec(
    spec: RawSpec,
    providers: dict[str, Provider],
    cache: SeriesCache,
    pit: PitStore,
    force: bool,
    all_sources: bool,
    now: datetime,
) -> FetchResult:
    ranked = rank_providers(spec.symbol_map(), providers)
    result = FetchResult(spec.key, spec.kind, "fehlgeschlagen", optional=spec.optional)
    if not ranked:
        reasons = [
            f"{name}: {providers[name].unavailable_reason() or 'unbekannt'}"
            for name in spec.symbol_map()
            if name in providers
        ]
        result.message = "keine nutzbare Quelle (" + "; ".join(reasons) + ")"
        return result
    errors: list[str] = []
    primary_index = -1
    for index, (name, provider, symbol) in enumerate(ranked):
        wants_vintages = spec.vintages and provider.capabilities().vintages
        if wants_vintages and provider.config.api_key_env and provider.api_key is None:
            wants_vintages = False
            errors.append(f"{name}: ohne API-Key keine Vintages, es gilt die Verzögerungsregel")
        request = SeriesRequest(symbol=symbol, kind=spec.kind, vintages=wants_vintages)  # type: ignore[arg-type]
        try:
            frame, meta = cache.fetch(name, provider, request, force=force)
        except ProviderError as exc:
            errors.append(f"{name}: {exc}")
            log.warning("%s: %s", spec.key, exc)
            continue
        if primary_index < 0:
            primary_index = index
            result.provider, result.symbol = name, symbol
            result.rows, result.first_obs, result.last_obs = (
                meta.rows,
                meta.first_obs,
                meta.last_obs,
            )
            result.status = "veraltet" if meta.stale else ("ok" if index == 0 else "ersatzquelle")
            if spec.pit:
                pit.update(spec.key, frame, spec.frequency, spec.lag(), pd.Timestamp(now))
            if not (spec.cross_check or all_sources):
                break
        else:
            result.secondary = name if not result.secondary else f"{result.secondary}, {name}"
            if not all_sources:
                break
    result.message = " | ".join(errors)
    return result


def update_data(
    config: AppConfig,
    paths: ProjectPaths,
    providers: dict[str, Provider] | None = None,
    only: str | None = None,
    force: bool = False,
    all_sources: bool = False,
    snapshot: bool = True,
) -> list[FetchResult]:
    """Lädt alle Rohreihen, pflegt den Point-in-Time-Speicher und legt einen Snapshot an."""
    paths.ensure()
    providers = providers or make_providers(config, paths)
    cache = make_cache(config, paths)
    pit = PitStore(paths.pit)
    now = utc_now()
    results = []
    for spec in collect_specs(config):
        if only and only not in spec.key:
            continue
        result = _fetch_spec(spec, providers, cache, pit, force, all_sources, now)
        results.append(result)
        level = logging.INFO if result.status == "ok" else logging.WARNING
        log.log(
            level, "%-48s %-13s %s %s", spec.key, result.status, result.provider, result.message
        )
    summary: dict[str, object] = {
        "series": len(results),
        "ok": sum(r.status == "ok" for r in results),
        "ersatzquelle": sum(r.status == "ersatzquelle" for r in results),
        "veraltet": sum(r.status == "veraltet" for r in results),
        "fehlgeschlagen": sum(r.status == "fehlgeschlagen" for r in results),
        "demo": paths.demo,
    }
    if snapshot and not only:
        summary["snapshot"] = str(write_snapshot(paths, config.config_hash, now, results))
    write_run(paths.runs, "data update", config.config_hash, summary)
    return results


def write_snapshot(
    paths: ProjectPaths, config_hash: str, now: datetime, results: list[FetchResult]
) -> Path:
    """Friert den Datenstand ein: Kopie von Rohdaten und Point-in-Time-Speicher mit Prüfsummen."""
    target = paths.snapshots / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{config_hash[:8]}"
    files: dict[str, str] = {}
    for source, name in ((paths.raw, "raw"), (paths.pit, "pit")):
        if not source.exists():
            continue
        shutil.copytree(source, target / name, dirs_exist_ok=True)
        for path in sorted((target / name).rglob("*")):
            if path.is_file():
                files[path.relative_to(target).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    manifest = {
        "created_at": now.isoformat(timespec="seconds"),
        "config_hash": config_hash,
        "demo": paths.demo,
        "files": files,
        "results": [asdict(r) for r in results],
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return target


def results_frame(results: list[FetchResult]) -> pd.DataFrame:
    """Abrufergebnisse als Tabelle."""
    columns = [
        "key",
        "status",
        "provider",
        "symbol",
        "first_obs",
        "last_obs",
        "rows",
        "secondary",
        "message",
    ]
    return pd.DataFrame([[getattr(r, c) for c in columns] for r in results], columns=columns)


def sources_table(config: AppConfig, providers: dict[str, Provider]) -> pd.DataFrame:
    """Übersicht der Quellen: eingeschaltet, Key vorhanden, Priorität, Lizenz."""
    rows = []
    for name, cfg in sorted(config.sources.sources.items(), key=lambda kv: (kv[1].priority, kv[0])):
        provider = providers.get(name)
        rows.append(
            {
                "Quelle": name,
                "Priorität": cfg.priority,
                "eingeschaltet": "ja" if cfg.enabled else "nein",
                "kostenpflichtig": "ja" if cfg.paid else "nein",
                "nutzbar": "ja" if provider is not None and provider.available() else "nein",
                "Hinweis": (provider.unavailable_reason() if provider is not None else "") or "",
                "Lizenz": cfg.license,
            }
        )
    return pd.DataFrame(rows)


def series_table(config: AppConfig, cache: SeriesCache) -> pd.DataFrame:
    """Je Rohreihe und Quelle: liegt sie vor, von wann bis wann, wie viele Werte."""
    rows = []
    for spec in collect_specs(config):
        for name, symbol in spec.symbols:
            cached = cache.read(name, symbol)
            enabled = (
                config.sources.sources[name].enabled if name in config.sources.sources else False
            )
            if cached is None and not enabled:
                continue
            meta = None if cached is None else cached[1]
            rows.append(
                {
                    "Reihe": spec.key,
                    "Quelle": name,
                    "Symbol": symbol,
                    "vorhanden": "ja" if meta else "NEIN",
                    "von": meta.first_obs if meta else "",
                    "bis": meta.last_obs if meta else "",
                    "Werte": meta.rows if meta else 0,
                    "erwartet ab": spec.expected_start or "",
                    "abgerufen": meta.fetched_at[:16] if meta else "",
                }
            )
    return pd.DataFrame(rows)


def run_validation(
    config: AppConfig, paths: ProjectPaths, providers: dict[str, Provider] | None = None
) -> ValidationReport:
    """Prüft alle gespeicherten Reihen und das Universum in jeder Basiswährung."""
    providers = providers or make_providers(config, paths)
    cache = make_cache(config, paths)
    now = utc_now()
    report = ValidationReport(
        created_at=now.isoformat(timespec="seconds"),
        config_hash=config.config_hash,
        demo=paths.demo,
    )
    findings: list[Finding] = []
    tolerance = config.sources.cross_check_tolerance
    for spec in collect_specs(config):
        available = [(n, s, cache.read(n, s)) for n, s in spec.symbols]
        present = [(n, s, c) for n, s, c in available if c is not None]
        if not present:
            severity = "Hinweis" if spec.optional else "Fehler"
            findings.append(Finding(severity, spec.key, "Abruf", "keine Daten im Cache"))  # type: ignore[arg-type]
            continue
        present.sort(
            key=lambda item: providers[item[0]].config.priority if item[0] in providers else 9999
        )
        name, _symbol, cached = present[0]
        assert cached is not None
        frame, meta = cached
        scope = f"{spec.key} [{name}]"
        findings += check_staleness(meta, scope, now, frame, spec.historical)
        findings += check_start(spec.expected_start, frame["obs_date"].min(), scope)
        if spec.kind in ("price", "level", "fx", "yield"):
            findings += check_gaps(frame, scope)
        if spec.kind == "price":
            crypto = "bitcoin" in spec.key
            findings += check_jumps(frame, scope, 0.6 if crypto else 0.25)
            if not crypto:
                findings += check_splits(frame, scope)
            if spec.distributing:
                findings += check_dividends(frame, scope)
            if spec.cross_check:
                if len(present) < 2:
                    findings.append(
                        Finding("Hinweis", scope, "Zweitquelle", "keine Zweitquelle im Cache")
                    )
                for other_name, _other_symbol, other in present[1:]:
                    assert other is not None
                    deviations = cross_check(frame, other[0], tolerance)
                    findings += summarize_cross_check(
                        deviations, scope, (name, other_name), tolerance
                    )
    loader = SeriesLoader(cache, providers)
    builder = UniverseBuilder(config, loader)
    expected = list(config.universe.enabled_assets())
    complete = []
    for base in config.currency.supported:
        universe = builder.build(base)
        findings += check_universe(universe.returns, expected, base)
        findings += [Finding("Hinweis", base, "Aufbau", issue) for issue in universe.issues]
        report.tables[f"Universum in {base}"] = universe.coverage()
        have = sum(a in universe.returns.columns for a in expected)
        complete.append(f"{base}: {have}/{len(expected)}")
        if base == config.currency.base:
            calibration_rows = [
                {"asset": asset, **asdict(cal)}
                for asset, items in universe.calibrations.items()
                for cal in items
            ]
            report.tables["Kalibrierung an den Nähten (Basiswährung)"] = pd.DataFrame(
                calibration_rows
            )
            minimum = config.universe.calibration.min_months
            for row in calibration_rows:
                if row["months"] >= minimum and not row["applied"]:
                    findings.append(
                        Finding(
                            "Warnung",
                            f"{row['asset']}/{row['older']}",
                            "Backfill",
                            f"passt schlecht zu {row['newer']} (Korrelation "
                            f"{row['correlation']:.2f}); unkalibriert verkettet",
                        )
                    )
            report.tables["Synthetische Reihen gegen Fonds"] = _synthetic_checks(
                config, builder, findings
            )
    report.notes.append("Assetklassen mit Monatsreihe je Basiswährung: " + ", ".join(complete))
    report.tables["Point-in-Time-Speicher (Makroreihen)"] = _pit_table(config, PitStore(paths.pit))
    report.tables["Quellen"] = sources_table(config, providers)
    report.tables["Rohreihen je Quelle"] = series_table(config, cache)
    report.findings = findings
    write_run(
        paths.runs,
        "data validate",
        config.config_hash,
        {
            "Fehler": report.count("Fehler"),
            "Warnung": report.count("Warnung"),
            "Hinweis": report.count("Hinweis"),
        },
    )
    return report


def _synthetic_checks(
    config: AppConfig, builder: UniverseBuilder, findings: list[Finding]
) -> pd.DataFrame:
    """Prüft synthetische Anleihen gegen das Proxy-Segment (Korrelation über 0,95)."""
    base = config.currency.base
    cash = pd.DataFrame()
    rows = []
    for key, asset in config.universe.enabled_assets().items():
        fund = next((s for s in asset.segments if s.kind == "price"), None)
        if fund is None:
            continue
        fund_returns = builder.segment_returns(fund, base, cash, None)
        for seg in asset.segments:
            if seg.kind not in ("synthetic_bond", "synthetic_linker") or fund_returns is None:
                continue
            synthetic = builder.segment_returns(seg, base, cash, None)
            if synthetic is None:
                continue
            check = check_against_fund(synthetic, fund_returns)
            rows.append(
                {
                    "asset": key,
                    "synthetisch": seg.id,
                    "Fonds": fund.id,
                    "Monate": check.months,
                    "Korrelation": check.correlation,
                    "Tracking Error p.a.": check.tracking_error_annual,
                    "akzeptiert": "ja" if check.accepted else "nein",
                }
            )
            if check.months >= 12 and not check.accepted:
                findings.append(
                    Finding(
                        "Warnung",
                        f"{key}/{seg.id}",
                        "Synthetik",
                        f"Korrelation {check.correlation:.2f} zum Fonds {fund.id} liegt unter 0,95",
                    )
                )
    return pd.DataFrame(rows)


def _pit_table(config: AppConfig, pit: PitStore) -> pd.DataFrame:
    columns = [
        "Indikator",
        "Beobachtungen",
        "von",
        "bis",
        "Revisionen",
        "Anteil Verzögerungsregel",
        "echte Vintages",
        "zuletzt bekannt ab",
    ]
    rows: list[list[object]] = []
    for key, indicator in config.indicators.indicators.items():
        series = pit.load(f"indicator.{key}")
        if series is None or series.frame.empty:
            rows.append([key, 0, "", "", 0, "", "", ""])
            continue
        frame = series.frame
        rows.append(
            [
                key,
                int(frame["obs_date"].nunique()),
                str(frame["obs_date"].min().date()),
                str(frame["obs_date"].max().date()),
                series.revision_count(),
                f"{frame['approx'].mean():.0%}",
                "ja" if indicator.vintages and not frame["approx"].all() else "nein",
                str(frame["known_from"].max().date()),
            ]
        )
    return pd.DataFrame(rows, columns=columns, dtype=object)
