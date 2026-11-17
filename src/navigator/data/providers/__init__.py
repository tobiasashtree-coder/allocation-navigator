"""Provider-Registry: baut die Quellen aus ``sources.yaml`` und ordnet sie nach Priorität."""

from __future__ import annotations

from navigator.config import SourcesConfig, source_base
from navigator.data.providers.base import (
    Capabilities,
    License,
    Provider,
    ProviderDisabledError,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
)
from navigator.data.providers.demo import DemoProvider, demo_config
from navigator.data.providers.fred import FredProvider
from navigator.data.providers.issuer_nav import IssuerNavProvider
from navigator.data.providers.licensed import MsciProvider, SipaProvider
from navigator.data.providers.market import (
    CoinMetricsProvider,
    EodhdProvider,
    TiingoProvider,
    YahooProvider,
)
from navigator.data.providers.private_infra import PrivateInfraProvider
from navigator.data.providers.sdmx import (
    BisProvider,
    BundesbankProvider,
    EcbProvider,
    EurostatProvider,
    OecdProvider,
)
from navigator.data.providers.static import StaticProvider
from navigator.http import HttpClient
from navigator.paths import ProjectPaths

__all__ = [
    "Capabilities",
    "License",
    "Provider",
    "ProviderDisabledError",
    "ProviderError",
    "SeriesNotFoundError",
    "SeriesRequest",
    "build_providers",
    "rank_providers",
]

_SIMPLE: dict[str, type[Provider]] = {
    "fred": FredProvider,
    "ecb": EcbProvider,
    "eurostat": EurostatProvider,
    "oecd": OecdProvider,
    "bis": BisProvider,
    "bundesbank": BundesbankProvider,
    "yfinance": YahooProvider,
    "tiingo": TiingoProvider,
    "coinmetrics": CoinMetricsProvider,
    "eodhd": EodhdProvider,
    "sipa": SipaProvider,
    "msci": MsciProvider,
}


def build_providers(
    sources: SourcesConfig,
    paths: ProjectPaths,
    http: HttpClient | None = None,
    demo: bool = False,
) -> dict[str, Provider]:
    """Erzeugt je konfigurierter Quelle einen Provider.

    Im Demo-Modus steht hinter jedem eingeschalteten Quellennamen der Demo-Provider;
    die Auswahl nach Priorität läuft dann genauso wie mit echten Quellen.
    """
    client = http or HttpClient()
    providers: dict[str, Provider] = {}
    for name, cfg in sources.sources.items():
        if demo:
            if cfg.enabled:
                providers[name] = DemoProvider(
                    demo_config().model_copy(update={"priority": cfg.priority}), alias=name
                )
            continue
        if name in _SIMPLE:
            providers[name] = _SIMPLE[name](cfg, client)
        elif name == "static":
            providers[name] = StaticProvider(
                cfg, client, paths.static, sources.cache.static_max_age_days
            )
        elif name == "issuer_nav":
            providers[name] = IssuerNavProvider(cfg, client, paths.static)
        elif name == "private_infra":
            providers[name] = PrivateInfraProvider(
                cfg, client, paths.processed / "private_infra.json"
            )
        else:
            raise ProviderError(f"Unbekannte Quelle in sources.yaml: {name}")
    return providers


def rank_providers(
    symbols: dict[str, str], providers: dict[str, Provider]
) -> list[tuple[str, Provider, str]]:
    """Nutzbare Quellen einer Reihe, höchste Priorität zuerst: (Name, Provider, Symbol)."""
    ranked = [
        (providers[source_base(name)].config.priority, name, providers[source_base(name)], symbol)
        for name, symbol in symbols.items()
        if source_base(name) in providers and providers[source_base(name)].available()
    ]
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [(name, provider, symbol) for _, name, provider, symbol in ranked]
