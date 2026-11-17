"""Vergleichswerte für nicht börsennotierte Infrastruktur (Spezifikation Abschnitt 2).

Drei Stufen:

1. Veröffentlichte Eckwerte (MSCI-Quartalsergebnisse, infra300-Meldungen): Ein Parser
   liest die frei zugänglichen Seiten. Jeder neue Wert wird mit Quelle und Abrufdatum
   gespeichert und erst nach Bestätigung verwendet. Ist der automatische Abruf einer
   Seite nicht ausdrücklich erlaubt, entsteht stattdessen eine Erinnerung zur
   manuellen Eingabe.
2. Börsennotierte NAV-Näherung: NAV je Anteil britischer Infrastruktur-Gesellschaften
   aus deren Meldungen (Kurse kommen über yfinance, siehe ``references`` im Universum).
3. Lizenz-Schnittstellen (SIPA, MSCI) in ``licensed.py``, deaktiviert.

Private Werte sind bewertungsbasiert und geglättet. Sie dienen nur der
Plausibilisierung nach Entglättung (Geltner-Verfahren), nie der Optimierung.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    SeriesNotFoundError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)
from navigator.data.providers.sdmx import period_end
from navigator.http import HttpClient, HttpError
from navigator.runlog import utc_now

log = logging.getLogger(__name__)

STATUSES = ("pending", "confirmed", "rejected", "reminder")
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}
_PCT = r"(-?\d{1,3}(?:[.,]\d{1,2})?)\s?(?:%|percent|per cent)"


@dataclass
class InfraValue:
    """Ein importierter oder manuell erfasster Eckwert."""

    id: str
    series: str
    period: str
    value: float
    unit: str
    source_url: str
    fetched_at: str
    status: str = "pending"
    note: str = ""


@dataclass(frozen=True)
class Candidate:
    """Vom Parser gefundener Wert, noch nicht gespeichert."""

    period: str
    value: float
    unit: str
    context: str


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def page_text(html: str) -> str:
    """Sichtbarer Text einer HTML-Seite."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def parse_msci_results(text: str) -> list[Candidate]:
    """Sucht in MSCI-Quartalsergebnissen die Rendite über 12 Monate bzw. das Quartal."""
    found: list[Candidate] = []
    quarter = re.search(r"\bQ([1-4])\s+(20\d{2})\b", text)
    period = f"{quarter[2]}-Q{quarter[1]}" if quarter else ""
    patterns = [
        (
            "pct_12m",
            rf"(?:12[- ]month|one[- ]year|1[- ]year|annual|rolling four[- ]quarter)"
            rf"[^.%]{{0,80}}?{_PCT}",
        ),
        ("pct_quarter", rf"(?:quarterly|for the quarter|in the quarter)[^.%]{{0,80}}?{_PCT}"),
    ]
    for unit, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append(
                Candidate(
                    period=period,
                    value=_to_float(match[1]),
                    unit=unit,
                    context=text[max(0, match.start() - 60) : match.end() + 20],
                )
            )
    return found


def parse_infra300(text: str) -> list[Candidate]:
    """Sucht in infra300-Meldungen die Monatsrendite samt Monat und Jahr."""
    found: list[Candidate] = []
    month_names = "|".join(_MONTHS)
    pattern = (
        rf"{_PCT}[^.]{{0,60}}?\bin\s+({month_names})(?:\s+(20\d{{2}}))?"
        rf"|\b({month_names})(?:\s+(20\d{{2}}))?[^.]{{0,60}}?{_PCT}"
    )
    year_hint = re.search(r"\b(20\d{2})\b", text)
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        value = match[1] or match[6]
        month = (match[2] or match[4] or "").lower()
        year = match[3] or match[5] or (year_hint[1] if year_hint else "")
        if not value or month not in _MONTHS or not year:
            continue
        found.append(
            Candidate(
                period=f"{year}-{_MONTHS[month]:02d}",
                value=_to_float(value),
                unit="pct_month",
                context=text[max(0, match.start() - 40) : match.end() + 20],
            )
        )
    return found


def parse_nav_per_share(text: str) -> list[Candidate]:
    """Sucht in Unternehmensmeldungen den NAV je Anteil in Pence."""
    found: list[Candidate] = []
    pattern = (
        r"(?:NAV|net asset value)\s+per\s+(?:ordinary\s+)?share[^.]{0,60}?"
        r"(\d{2,4}(?:\.\d{1,2})?)\s?(?:p\b|pence)"
    )
    date = re.search(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(20\d{2})\b", text, re.I)
    period = f"{date[3]}-{_MONTHS[date[2].lower()]:02d}" if date else ""
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        found.append(
            Candidate(
                period=period,
                value=float(match[1]),
                unit="pence",
                context=text[max(0, match.start() - 40) : match.end() + 20],
            )
        )
    return found


PARSERS = {
    "msci_private_infra_12m": parse_msci_results,
    "infra300_monthly": parse_infra300,
    "nav": parse_nav_per_share,
}


def geltner_unsmooth(returns: pd.Series, rho: float | None = None) -> pd.Series:
    """Entglättet bewertungsbasierte Renditen: r*_t = (r_t - rho * r_{t-1}) / (1 - rho).

    Ohne Vorgabe wird ``rho`` als Autokorrelation erster Ordnung geschätzt und auf
    [0, 0,9] begrenzt.
    """
    clean = returns.dropna().astype("float64")
    if len(clean) < 3:
        return clean
    if rho is None:
        rho = float(np.clip(clean.autocorr(lag=1), 0.0, 0.9))
        if np.isnan(rho):
            rho = 0.0
    return ((clean - rho * clean.shift(1)) / (1.0 - rho)).dropna()


class PrivateInfraStore:
    """Ablage der Eckwerte mit Status (ausstehend, bestätigt, abgelehnt, Erinnerung)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[InfraValue]:
        """Alle gespeicherten Einträge."""
        if not self.path.exists():
            return []
        return [InfraValue(**item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self, values: list[InfraValue]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(v) for v in values]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(
        self,
        series: str,
        period: str,
        value: float,
        unit: str,
        source_url: str,
        status: str = "pending",
        note: str = "",
    ) -> InfraValue | None:
        """Fügt einen Wert hinzu; identische Einträge werden nicht doppelt gespeichert."""
        values = self.load()
        for existing in values:
            same = (existing.series, existing.period, existing.unit) == (series, period, unit)
            if same and existing.status == status and abs(existing.value - value) < 1e-12:
                return None
        entry = InfraValue(
            id=f"{len(values) + 1:04d}",
            series=series,
            period=period,
            value=value,
            unit=unit,
            source_url=source_url,
            fetched_at=utc_now().isoformat(timespec="seconds"),
            status=status,
            note=note,
        )
        values.append(entry)
        self._save(values)
        return entry

    def set_status(self, entry_id: str, status: str) -> InfraValue:
        """Bestätigt oder verwirft einen Eintrag."""
        if status not in STATUSES:
            raise ValueError(f"Unbekannter Status {status}")
        values = self.load()
        for entry in values:
            if entry.id == entry_id:
                entry.status = status
                self._save(values)
                return entry
        raise KeyError(f"Eintrag {entry_id} nicht gefunden")

    def confirmed(self, series: str) -> pd.DataFrame:
        """Bestätigte Werte einer Reihe im Provider-Format."""
        rows = [
            (period_end(v.period), v.value)
            for v in self.load()
            if v.series == series and v.status == "confirmed" and v.period
        ]
        return normalize_frame(pd.DataFrame(rows, columns=["obs_date", "value"]))


class PrivateInfraProvider(Provider):
    """Automatischer Import veröffentlichter Eckwerte privater Infrastruktur."""

    name: ClassVar[str] = "private_infra"

    def __init__(
        self,
        config: SourceConfig,
        http: HttpClient | None = None,
        store_path: Path | None = None,
    ) -> None:
        super().__init__(config, http)
        self.store = PrivateInfraStore(store_path or Path("data/processed/private_infra.json"))

    def capabilities(self) -> Capabilities:
        """Bestätigte Eckwerte; nur zur Plausibilisierung."""
        return Capabilities(
            kinds=frozenset({"returns", "level"}),
            description="Veröffentlichte Eckwerte privater Infrastruktur (nach Bestätigung)",
        )

    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Liefert ausschließlich bestätigte Werte einer Reihe."""
        self._require_available()
        frame = self.store.confirmed(request.symbol)
        if frame.empty:
            raise SeriesNotFoundError(
                f"private_infra: keine bestätigten Werte für {request.symbol}"
            )
        return clip_dates(frame, request.start, request.end)

    def import_published(self) -> list[str]:
        """Ruft die konfigurierten Seiten ab und legt neue Werte als „ausstehend" ab.

        Liefert je Seite eine Meldung. Ohne ausdrückliche Erlaubnis oder bei
        ablehnender ``robots.txt`` entsteht eine Erinnerung zur manuellen Eingabe.
        """
        messages: list[str] = []
        pages: dict[str, dict[str, Any]] = dict(self.config.options.get("pages", {}))
        for name, page in pages.items():
            series, url = str(page.get("series", name)), str(page.get("url", ""))
            access = str(page.get("automated_access", "unknown"))
            reason = ""
            if access != "allowed":
                reason = f"automatischer Abruf nicht freigegeben (automated_access={access})"
            elif not self.http.robots_allowed(url):
                reason = "robots.txt erlaubt den Abruf nicht"
            if reason:
                self.store.add(series, "", float("nan"), "", url, status="reminder", note=reason)
                messages.append(f"{name}: Erinnerung zur manuellen Eingabe ({reason})")
                continue
            try:
                text = page_text(self.http.get(url, min_interval=self.min_interval).text)
            except HttpError as exc:
                self.store.add(series, "", float("nan"), "", url, status="reminder", note=str(exc))
                messages.append(f"{name}: Abruf gescheitert, Erinnerung angelegt ({exc})")
                continue
            parser = PARSERS.get(series, parse_msci_results)
            added = 0
            for cand in parser(text):
                if self.store.add(
                    series, cand.period, cand.value, cand.unit, url, note=cand.context
                ):
                    added += 1
            messages.append(f"{name}: {added} neue Werte, Bestätigung ausstehend")
        return messages
