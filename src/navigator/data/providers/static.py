"""Statische Downloads für lange Historien: Kenneth French, AQR, Nareit, JST, manuelle Dateien.

Ein Symbol hat die Form ``<Datensatz>:<Spalte>``; mit ``+`` lassen sich Spalten
addieren (z. B. ``french_us_factors:Mkt-RF+RF`` für die Marktrendite). Die Datensätze
stehen in ``config/sources.yaml``.

Schlägt ein Download fehl (manche Seiten blockieren automatische Abrufe), genügt es,
die Datei von Hand unter ``data/static/manual/<Datensatz>.<Endung>`` abzulegen.
"""

from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from navigator.config import SourceConfig
from navigator.data.providers.base import (
    Capabilities,
    Provider,
    ProviderError,
    SeriesNotFoundError,
    SeriesRequest,
    clip_dates,
    normalize_frame,
)
from navigator.http import HttpClient, HttpError

log = logging.getLogger(__name__)

_MONTH = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")
_MISSING_BELOW = -99.0


def _month_end(yyyymm: str) -> pd.Timestamp:
    return pd.Timestamp(int(yyyymm[:4]), int(yyyymm[4:6]), 1) + pd.offsets.MonthEnd(0)


def parse_french_csv(text: str, section: str | None = None) -> pd.DataFrame:
    """Liest die erste Monatstabelle einer CSV-Datei der Kenneth-French-Bibliothek.

    ``section`` wählt bei Dateien mit mehreren Tabellen die Tabelle, deren Titelzeile
    den Text enthält (Standard: die erste Monatstabelle, wertgewichtete Renditen).
    Fehlende Werte (-99.99, -999) werden zu NaN. Die Werte bleiben in Prozent.
    """
    lines = text.splitlines()
    title = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        cells = [c.strip() for c in line.split(",")]
        is_header = line.startswith(",") and len(cells) > 1
        if not is_header:
            if line and not _MONTH.match(cells[0]):
                title = line
            i += 1
            continue
        names = cells[1:]
        rows: list[list[str]] = []
        j = i + 1
        while j < len(lines):
            parts = [c.strip() for c in lines[j].split(",")]
            if not _MONTH.match(parts[0]):
                break
            rows.append(parts)
            j += 1
        wanted = section is None or section.lower() in title.lower()
        if rows and wanted:
            index = pd.DatetimeIndex([_month_end(r[0]) for r in rows])
            data = [[_to_float(v) for v in r[1 : len(names) + 1]] for r in rows]
            table = pd.DataFrame(data, index=index, columns=names)
            return table.where(table > _MISSING_BELOW)
        i = max(j, i + 1)
    raise ProviderError("French-CSV: keine Monatstabelle gefunden")


def parse_french_dat(text: str) -> pd.DataFrame:
    """Liest die erste Monatstabelle einer ``.Dat``-Datei (internationale French-Daten).

    Die Dateien sind durch Leerzeichen getrennt; die erste Wertspalte ist die
    Marktrendite in USD und heißt hier ``Mkt``.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        parts = line.split()
        if parts and _MONTH.match(parts[0]) and len(parts) > 1:
            rows.append(parts)
        elif rows:
            break
    if not rows:
        raise ProviderError("French-DAT: keine Monatszeilen gefunden")
    width = min(len(r) for r in rows) - 1
    names = ["Mkt"] + [f"c{k}" for k in range(1, width)]
    index = pd.DatetimeIndex([_month_end(r[0]) for r in rows])
    data = [[_to_float(v) for v in r[1 : width + 1]] for r in rows]
    table = pd.DataFrame(data, index=index, columns=names)
    return table.where(table > _MISSING_BELOW)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _parse_period(value: Any) -> pd.Timestamp | None:
    """Liest ein Datum oder eine Monatsangabe wie ``1960M01`` bzw. ``196001``."""
    if isinstance(value, pd.Timestamp):
        return value
    text = str(value).strip()
    if match := re.fullmatch(r"((?:18|19|20)\d{2})[Mm-]?(0[1-9]|1[0-2])", text):
        return pd.Timestamp(int(match[1]), int(match[2]), 1)
    if not text or text.lower() in ("nan", "nat", "none") or not re.search(r"\d{4}", text):
        return None
    stamp = pd.to_datetime(text, errors="coerce")
    return None if pd.isna(stamp) else stamp


def read_excel_grid(content: bytes, sheet: Any) -> pd.DataFrame:
    """Liest ein Tabellenblatt roh, ohne Kopfzeile."""
    return pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)


def excel_table(grid: pd.DataFrame, column_hint: str, search_rows: int = 80) -> pd.DataFrame:
    """Findet die Kopfzeile selbst und liefert die Tabelle darunter.

    Kopfzeile ist die erste Zeile, in der eine Zelle dem gesuchten Spaltennamen
    entspricht (ersatzweise ihn enthält) und unter der die erste Spalte Datumsangaben
    trägt. So bleibt der Parser robust, wenn ein Anbieter Vorspannzeilen ergänzt.
    """
    wanted = column_hint.split("+")[0].strip().lower()
    limit = min(search_rows, len(grid))
    cells = [[str(v).strip().lower() for v in grid.iloc[i]] for i in range(limit)]
    exact = [i for i in range(limit) if wanted in cells[i]]
    partial = [i for i in range(limit) if any(wanted in c for c in cells[i])]
    for index in exact + partial:
        below = grid.iloc[index + 1 : index + 6, 0]
        if not any(_parse_period(v) is not None for v in below):
            continue
        header = [str(v).strip() for v in grid.iloc[index]]
        body = grid.iloc[index + 1 :]
        dates = [_parse_period(v) for v in body.iloc[:, 0]]
        keep = [d is not None for d in dates]
        table = body.loc[keep].iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
        table.columns = header[1:]
        table.index = pd.DatetimeIndex([d for d in dates if d is not None]) + pd.offsets.MonthEnd(0)
        return table.loc[:, [c for c in table.columns if c and c.lower() != "nan"]]
    texts = max(cells, key=lambda row: sum(1 for c in row if c and c != "nan"), default=[])
    raise SeriesNotFoundError(
        f"Excel: keine Kopfzeile mit Spalte {column_hint!r} gefunden "
        f"(textreichste Zeile: {[c for c in texts if c and c != 'nan'][:10]})"
    )


def parse_excel_positional(
    content: bytes, sheet: Any, skiprows: int, columns: dict[str, int]
) -> pd.DataFrame:
    """Liest eine Excel-Tabelle ohne brauchbaren Kopf über feste Spaltenpositionen."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None, skiprows=skiprows)
    dates = pd.to_datetime(raw.iloc[:, 0], errors="coerce")
    keep = dates.notna().to_numpy()
    index = pd.DatetimeIndex(dates[keep]) + pd.offsets.MonthEnd(0)
    data = {
        name: pd.to_numeric(raw.iloc[:, pos][keep], errors="coerce").to_numpy()
        for name, pos in columns.items()
    }
    return pd.DataFrame(data, index=index)


def parse_manual_csv(text: str) -> pd.DataFrame:
    """Liest eine manuell abgelegte CSV: erste Spalte Datum, weitere Spalten Werte."""
    header = text.lstrip("﻿").splitlines()[0] if text.strip() else ""
    sep = ";" if header.count(";") > header.count(",") else ","
    table = pd.read_csv(io.StringIO(text.lstrip("﻿")), sep=sep)
    dates = pd.to_datetime(table.iloc[:, 0], errors="coerce")
    table = table[dates.notna().to_numpy()]
    out = table.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    out.index = pd.DatetimeIndex(dates.dropna()) + pd.offsets.MonthEnd(0)
    out.columns = [str(c).strip() for c in out.columns]
    return out


def pick_column(table: pd.DataFrame, expression: str) -> pd.Series:
    """Wählt eine Spalte (exakt, sonst eindeutiger Teiltreffer); ``A+B`` addiert Spalten."""
    total: pd.Series | None = None
    for part in expression.split("+"):
        wanted = part.strip().lower()
        exact = [c for c in table.columns if str(c).strip().lower() == wanted]
        partial = [c for c in table.columns if wanted in str(c).strip().lower()]
        matches = exact or partial
        if len(matches) != 1:
            raise SeriesNotFoundError(
                f"Spalte {part!r} nicht eindeutig (Treffer: {matches}; vorhanden: "
                f"{[str(c) for c in table.columns][:12]})"
            )
        column = table[matches[0]].astype("float64")
        total = column if total is None else total + column
    assert total is not None
    return total


def looks_like_level(series: pd.Series) -> bool:
    """Erkennt, ob eine Reihe ein Indexstand (statt Renditen in Prozent) ist."""
    clean = series.dropna()
    if clean.empty:
        return False
    return bool((clean > 0).all() and clean.median() > 20 and (clean.diff() < 0).mean() < 0.6)


class StaticProvider(Provider):
    """Lädt statische Datensätze, legt sie lokal ab und liefert einzelne Spalten."""

    name: ClassVar[str] = "static"

    def __init__(
        self,
        config: SourceConfig,
        http: HttpClient | None = None,
        static_dir: Path | None = None,
        max_age_days: float = 30.0,
    ) -> None:
        super().__init__(config, http)
        self.static_dir = static_dir or Path("data/static")
        self.max_age_days = max_age_days
        self._tables: dict[str, pd.DataFrame] = {}

    def capabilities(self) -> Capabilities:
        """Backfill-Reihen und historische Datensätze."""
        return Capabilities(
            kinds=frozenset({"returns", "level", "macro"}),
            description="Kenneth French, AQR, Nareit, JST, manuell abgelegte Dateien",
        )

    # ---------------------------------------------------------------- Dateien
    def _datasets(self) -> dict[str, dict[str, Any]]:
        return dict(self.config.options.get("datasets", {}))

    def _content(self, dataset: str, spec: dict[str, Any]) -> bytes:
        manual = sorted((self.static_dir / "manual").glob(f"{dataset}.*"))
        if manual:
            return manual[0].read_bytes()
        url = str(spec.get("url", ""))
        if not url:
            raise SeriesNotFoundError(f"static: Datensatz {dataset} hat keine URL")
        suffix = Path(url.split("?")[0]).suffix or ".bin"
        target = self.static_dir / "downloads" / f"{dataset}{suffix}"
        fresh = target.exists() and (time.time() - target.stat().st_mtime) < (
            self.max_age_days * 86_400
        )
        if not fresh:
            try:
                response = self.http.get(url, min_interval=self.min_interval)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(response.content)
            except HttpError as exc:
                if not target.exists():
                    raise ProviderError(
                        f"static: Download von {dataset} gescheitert ({exc}). Datei bitte "
                        f"von Hand unter {self.static_dir / 'manual'} als "
                        f"'{dataset}{suffix}' ablegen."
                    ) from exc
                log.warning(
                    "static: Download von %s gescheitert (%s); verwende den älteren Stand",
                    dataset,
                    exc,
                )
        return target.read_bytes()

    def _table(self, dataset: str) -> pd.DataFrame:
        if dataset in self._tables:
            return self._tables[dataset]
        specs = self._datasets()
        if dataset not in specs:
            raise SeriesNotFoundError(f"static: unbekannter Datensatz {dataset}")
        spec = specs[dataset]
        fmt = str(spec.get("format", ""))
        if fmt == "manual_csv":
            path = self.static_dir / str(spec.get("path", f"manual/{dataset}.csv"))
            if not path.exists():
                raise SeriesNotFoundError(
                    f"static: manuelle Datei fehlt ({path}); erste Spalte Datum, dann Werte"
                )
            table = parse_manual_csv(path.read_text(encoding="utf-8"))
        else:
            content = self._content(dataset, spec)
            if fmt in ("french_csv", "french_dat"):
                text = _unzip_text(content, spec.get("member"))
                table = (
                    parse_french_csv(text, spec.get("section"))
                    if fmt == "french_csv"
                    else parse_french_dat(text)
                )
            elif fmt == "excel":
                table = read_excel_grid(content, spec.get("sheet", 0))
            elif fmt == "excel_positional":
                table = parse_excel_positional(
                    content,
                    spec.get("sheet", 0),
                    int(spec.get("skiprows", 0)),
                    {str(k): int(v) for k, v in dict(spec.get("columns", {})).items()},
                )
            else:
                raise ProviderError(f"static: unbekanntes Format {fmt!r} für {dataset}")
        self._tables[dataset] = table
        return table

    # ------------------------------------------------------------------ Abruf
    def fetch_series(self, request: SeriesRequest) -> pd.DataFrame:
        """Liefert eine Spalte eines Datensatzes als Monatsreihe (Renditen dezimal)."""
        self._require_available()
        if ":" not in request.symbol:
            raise ProviderError("static: Symbol muss 'Datensatz:Spalte' sein")
        dataset, column = request.symbol.split(":", 1)
        spec = self._datasets().get(dataset, {})
        table = self._table(dataset)
        if str(spec.get("format", "")) == "excel":
            table = excel_table(table, column)
        series = pick_column(table, column).dropna()
        value_type = str(spec.get("value_type", "returns"))
        if value_type == "auto":
            value_type = "level_to_returns" if looks_like_level(series) else "percent"
        if value_type == "level_to_returns":
            series = series.pct_change(fill_method=None).dropna()
        elif value_type == "percent":
            series = series * 0.01
        elif value_type != "level":
            series = series * float(spec.get("scale", 1.0))
        frame = pd.DataFrame({"obs_date": series.index, "value": series.to_numpy()})
        out = clip_dates(normalize_frame(frame), request.start, request.end)
        if out.empty:
            raise SeriesNotFoundError(f"static: keine Werte für {request.symbol}")
        return out


def _unzip_text(content: bytes, member: Any = None) -> str:
    """Liefert den Text einer Datei aus einem ZIP (oder den Inhalt selbst, falls kein ZIP)."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return content.decode("latin-1")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if member:
            matches = [n for n in names if n.lower().endswith(str(member).lower())]
            if not matches:
                raise SeriesNotFoundError(f"ZIP enthält {member} nicht (Inhalt: {names[:10]})")
            name = matches[0]
        else:
            name = names[0]
        return archive.read(name).decode("latin-1")
