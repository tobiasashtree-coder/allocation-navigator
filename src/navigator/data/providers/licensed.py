"""Lizenz-Schnittstellen für private Infrastruktur: SIPA (infra300) und MSCI.

Beide sind Platzhalter laut Spezifikation: Die Provider existieren, damit ein
späteres Abo nur in der Konfiguration eingeschaltet werden muss. Ohne Lizenz
lehnen sie jeden Abruf ab.
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderDisabledError,
    SeriesRequest,
)


class _LicensedPlaceholder(Provider):
    """Gemeinsame Basis der vorbereiteten, deaktivierten Lizenz-Provider."""

    product: ClassVar[str] = ""

    def capabilities(self) -> Capabilities:
        """Lizenzierte Private-Markets-Indizes."""
        return Capabilities(
            kinds=frozenset({"returns", "level"}),
            needs_key=True,
            description=f"{self.product} (Lizenz erforderlich, Schnittstelle vorbereitet)",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Lehnt ab, solange keine Lizenz hinterlegt und der Abruf nicht implementiert ist."""
        self._require_available()
        raise ProviderDisabledError(
            f"{self.name}: Der Abruf von {self.product} ist vorbereitet, aber noch nicht "
            "angebunden. Nach Abschluss einer Lizenz hier den Endpunkt des Anbieters "
            "implementieren (Rückgabeformat siehe providers/base.py)."
        )


class SipaProvider(_LicensedPlaceholder):
    """SIPA / Scientific Infra: infra300-Index nicht börsennotierter Infrastruktur."""

    name: ClassVar[str] = "sipa"
    product = "infra300"


class MsciProvider(_LicensedPlaceholder):
    """MSCI Global Quarterly Private Infrastructure Asset Index."""

    name: ClassVar[str] = "msci"
    product = "MSCI Private Infrastructure Asset Index"
