"""Währungsumrechnung und Währungssicherung (Spezifikation Abschnitt 3 und 7.6).

Intern wird jede Währung als „USD je Einheit" geführt. Daraus ergibt sich jeder
Kreuzkurs. Ab 1999 stammen die Kurse aus den EZB-Referenzkursen; davor aus den
Tageskursen der Federal Reserve (H.10), wobei der Euro über die D-Mark mit dem
unwiderruflichen Umrechnungskurs zurückgerechnet wird.

Die Währungssicherung wird näherungsweise als Lokalrendite plus Zinsdifferenz
(Basiswährung minus Fremdwährung) auf Monatsbasis gerechnet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from navigator.config import CurrencyConfig

SeriesLoaderFn = Callable[[dict[str, str], str], pd.Series | None]


def is_monthly(series: pd.Series) -> bool:
    """Erkennt Monatsreihen am Abstand der Beobachtungen."""
    if len(series) < 3:
        return False
    gaps = pd.Series(series.index[1:] - series.index[:-1])
    return bool(gaps.median() > pd.Timedelta(days=20))


def to_month_end(series: pd.Series, asof: pd.Timestamp | None = None) -> pd.Series:
    """Monatsendstände einer Tages- oder Monatsreihe.

    Es zählen nur Beobachtungen bis ``asof``. Ein noch nicht abgeschlossener letzter
    Monat wird verworfen, damit keine Teilmonate als Monatswerte gelten. Ob eine Reihe
    monatlich ist, wird an der ganzen Reihe erkannt (das ist eine feste Eigenschaft der
    Reihe und hängt nicht von Werten ab).
    """
    clean = series.dropna().sort_index()
    if clean.empty:
        return clean
    if is_monthly(clean):
        out = clean.copy()
        out.index = pd.DatetimeIndex(clean.index).normalize() + pd.offsets.MonthEnd(0)
        out = out[~out.index.duplicated(keep="last")]
        return out if asof is None else out[out.index <= pd.Timestamp(asof)]
    if asof is not None:
        clean = clean[clean.index <= pd.Timestamp(asof)]
    if clean.empty:
        return clean
    monthly = clean.resample("ME").last().dropna()
    last_obs = clean.index.max()
    if len(monthly) and last_obs < monthly.index[-1] - pd.Timedelta(days=4):
        monthly = monthly.iloc[:-1]
    return monthly


def month_mean(series: pd.Series, asof: pd.Timestamp | None = None) -> pd.Series:
    """Monatsdurchschnitt einer Tagesreihe (für Zinssätze); Monatsreihen bleiben unverändert."""
    clean = series.dropna().sort_index()
    if clean.empty or is_monthly(clean):
        return to_month_end(clean, asof)
    if asof is not None:
        clean = clean[clean.index <= pd.Timestamp(asof)]
    if clean.empty:
        return clean
    means = clean.resample("ME").mean().dropna()
    last_obs = clean.index.max()
    if len(means) and last_obs < means.index[-1] - pd.Timedelta(days=4):
        means = means.iloc[:-1]
    return means


@dataclass
class FxRates:
    """Monatsendkurse aller Währungen als „USD je Einheit"."""

    usd_per_unit: pd.DataFrame

    def has(self, currency: str) -> bool:
        """Ob für die Währung Kurse vorliegen."""
        return currency == "USD" or currency in self.usd_per_unit.columns

    def rate(self, from_ccy: str, to_ccy: str) -> pd.Series:
        """Wert einer Einheit ``from_ccy`` in ``to_ccy`` zum Monatsende."""
        frame = self.usd_per_unit
        ones = pd.Series(1.0, index=frame.index)
        left = ones if from_ccy == "USD" else frame[from_ccy]
        right = ones if to_ccy == "USD" else frame[to_ccy]
        return (left / right).dropna()

    def fx_return(self, from_ccy: str, to_ccy: str) -> pd.Series:
        """Monatsrendite aus dem Halten von ``from_ccy``, gemessen in ``to_ccy``."""
        if from_ccy == to_ccy:
            return pd.Series(0.0, index=self.usd_per_unit.index)
        return self.rate(from_ccy, to_ccy).pct_change(fill_method=None).dropna()

    def convert_returns(self, returns: pd.Series, from_ccy: str, to_ccy: str) -> pd.Series:
        """Ungesicherte Rendite in ``to_ccy``: (1 + Lokalrendite) × (1 + Währungsrendite) − 1."""
        if from_ccy == to_ccy:
            return returns.dropna()
        fx = self.fx_return(from_ccy, to_ccy)
        joined = pd.concat([returns, fx], axis=1, join="inner").dropna()
        return (1.0 + joined.iloc[:, 0]) * (1.0 + joined.iloc[:, 1]) - 1.0


def build_fx_rates(
    config: CurrencyConfig, load: SeriesLoaderFn, asof: pd.Timestamp | None = None
) -> FxRates:
    """Baut die Monatsendkurse aus den konfigurierten Reihen (Reihenfolge = Vorrang)."""
    eur_candidates: list[pd.Series] = []
    for entry in config.fx_series:
        is_eur_usd = (entry.currency == "USD" and entry.quote == "per_eur") or (
            entry.currency == "EUR" and entry.quote in ("usd_per_unit", "dem_per_usd")
        )
        if not is_eur_usd:
            continue
        raw = load(entry.symbols, "fx")
        if raw is None or raw.empty:
            continue
        monthly = to_month_end(raw, asof)
        eur_candidates.append(
            config.dem_per_eur / monthly if entry.quote == "dem_per_usd" else monthly
        )
    columns: dict[str, pd.Series] = {}
    eur_usd = _combine(eur_candidates)
    if eur_usd is not None:
        columns["EUR"] = eur_usd
    by_currency: dict[str, list[pd.Series]] = {}
    for entry in config.fx_series:
        if entry.currency in ("USD", "EUR"):
            continue
        raw = load(entry.symbols, "fx")
        if raw is None or raw.empty:
            continue
        monthly = to_month_end(raw, asof)
        if entry.quote == "per_eur":
            if eur_usd is None:
                continue
            joined = pd.concat([eur_usd, monthly], axis=1, join="inner").dropna()
            value = joined.iloc[:, 0] / joined.iloc[:, 1]
        elif entry.quote == "per_usd":
            value = 1.0 / monthly
        else:
            value = monthly
        by_currency.setdefault(entry.currency, []).append(value)
    for currency, candidates in by_currency.items():
        combined = _combine(candidates)
        if combined is not None:
            columns[currency] = combined
    return FxRates(pd.DataFrame(columns).sort_index())


def _combine(candidates: list[pd.Series]) -> pd.Series | None:
    """Erste Reihe hat Vorrang; spätere füllen Lücken."""
    result: pd.Series | None = None
    for series in candidates:
        result = series if result is None else result.combine_first(series)
    return None if result is None else result.sort_index()


def build_cash_returns(
    config: CurrencyConfig, load: SeriesLoaderFn, asof: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Monatliche Geldmarktrendite je Währung aus den Kurzfristzinsen (Prozent p. a. / 12)."""
    columns: dict[str, pd.Series] = {}
    for currency, segments in config.short_rates.items():
        candidates = []
        for segment in segments:
            raw = load(segment.symbols, "rate")
            if raw is not None and not raw.empty:
                candidates.append(month_mean(raw, asof) / 1200.0)
        combined = _combine(candidates)
        if combined is not None:
            columns[currency] = combined
    return pd.DataFrame(columns).sort_index()


def hedged_return(local: pd.Series, cash_base: pd.Series, cash_foreign: pd.Series) -> pd.Series:
    """Gesicherte Rendite: Lokalrendite plus Zinsdifferenz (Basis minus Fremdwährung)."""
    joined = pd.concat([local, cash_base, cash_foreign], axis=1, join="inner").dropna()
    return joined.iloc[:, 0] + joined.iloc[:, 1] - joined.iloc[:, 2]


def decompose(total: pd.Series, currency_effect: pd.Series) -> pd.DataFrame:
    """Zerlegt die Rendite in Basiswährung in Lokal- und Währungsbeitrag (Summe = Gesamt)."""
    joined = pd.concat([total, currency_effect], axis=1, join="inner")
    joined.columns = ["total", "currency"]
    joined["local"] = joined["total"] - joined["currency"]
    return joined[["local", "currency", "total"]]
