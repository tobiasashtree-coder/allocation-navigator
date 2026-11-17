"""Langfristiger Schuldenzyklus: Schuldenstress-Score 0 bis 100 und Phase je Land (6.2).

Ablauf je Land (``owner``) und Stichtag t:

1. Jede Rohreihe wird zu Jahreswerten verdichtet. Ein Jahreswert gilt erst als bekannt,
   wenn alle Beobachtungen des Jahres nach der Verzögerungsregel bzw. ihrem Datenstand
   bekannt sind (``annualize``).
2. Aus dem bis t bekannten Stand entstehen die Bestandteile (``component_history``). Mehrere
   Quellen werden in fester Reihenfolge verkettet: jüngere Datenbanken (IMF Fiscal Monitor,
   WEO) zuerst, dann die lange Historie (IMF FPP), zuletzt JST.
3. Jeder Bestandteil wird als Perzentil gegen die bis t bekannte Verteilung eines
   Referenzpanels bewertet (Jahresendwerte aller Länder des Panels und des Tools).
4. Der Score ist das gewichtete Mittel der Perzentile mal 100. Die Phase folgt aus den
   Schwellen (kalibriert an der Score-Verteilung des Panels) und zwei Zusatzregeln für
   Entschuldung bzw. Monetarisierung.

„Neuordnung" ist nicht messbar und kommt nur aus der manuellen Einschätzung.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from navigator.config import AppConfig, DebtInput, DebtScoreConfig
from navigator.data.debt import input_key
from navigator.data.pit import PitSeries, PitStore, known_from_rule

MAX_AGE_YEARS = 3
"""Ein Bestandteil zählt nur, wenn sein jüngster Jahreswert höchstens so alt ist."""

AUX_COLUMNS = ("cb_assets_change_3y",)

PHASE_INDEX = {
    "gesund": 0,
    "Aufbau": 1,
    "Übertreibung": 2,
    "Spätphase (Finanzierungsstress)": 3,
    "Entschuldung / Monetarisierung": 4,
    "Neuordnung": 5,
}


# --------------------------------------------------------------------- Jahreswerte
def annualize(series: PitSeries, item: DebtInput, owner: str) -> PitSeries:
    """Verdichtet eine Rohreihe zu Jahreswerten (31.12.) mit konservativem ``known_from``.

    Jahreswerte (``A``) behalten alle Datenstände. Bei höherer Frequenz zählt der jüngste
    Datenstand; ein Jahreswert gilt ab dem spätesten Bekanntheitszeitpunkt seiner
    Beobachtungen und frühestens ab dem bekannten Ende des Jahres. Wird eine Beobachtung
    später revidiert, ist der Jahreswert bis dahin unbekannt (nie zu früh bekannt).
    Unvollständige Jahre entfallen.
    """
    scale = item.scale_by_country.get(owner, item.scale)
    frame = series.frame.copy()
    frame["value"] = frame["value"] * scale
    if item.frequency == "A":
        frame["obs_date"] = pd.DatetimeIndex(frame["obs_date"]) + pd.offsets.YearEnd(0)
        return PitSeries(series.key, frame)
    frame["year"] = pd.DatetimeIndex(frame["obs_date"]).year
    latest = frame.sort_values("known_from").groupby("obs_date", sort=True).last()
    known = frame.groupby("year")["known_from"].max()
    rows = []
    for year, group in latest.groupby("year"):
        last_month = pd.DatetimeIndex(group.index).max().month
        needed = {"D": 12, "M": 12, "Q": 10}[item.frequency]
        if last_month < needed:
            continue  # Jahr unvollständig
        if item.aggregate == "last":
            value = float(group["value"].iloc[-1])
        elif item.aggregate == "sum":
            value = float(group["value"].sum())
        else:
            value = float(group["value"].mean())
        year_end = pd.Timestamp(int(year), 12, 31)
        end_known = known_from_rule(
            pd.DatetimeIndex([year_end]),
            "D" if item.frequency == "D" else "M",
            item.publication_lag,
        )[0]
        rows.append(
            {
                "obs_date": year_end,
                "value": value,
                "known_from": max(pd.Timestamp(known[year]), end_known),
                "approx": True,
            }
        )
    return PitSeries(
        series.key, pd.DataFrame(rows, columns=["obs_date", "value", "known_from", "approx"])
    )


@dataclass
class OwnerInputs:
    """Jährliche Rohreihen eines Landes (oder Panel-Landes)."""

    owner: str
    series: dict[str, PitSeries] = field(default_factory=dict)
    _fast: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = field(
        default_factory=dict, repr=False
    )
    _rows: dict[tuple[int, int], dict[str, float]] = field(default_factory=dict, repr=False)

    def change_dates(self) -> list[pd.Timestamp]:
        """Zeitpunkte, an denen sich der bekannte Datenstand ändert."""
        dates: set[pd.Timestamp] = set()
        for item in self.series.values():
            dates.update(pd.DatetimeIndex(item.frame["known_from"]).unique())
        return sorted(dates)

    def as_of(self, when: pd.Timestamp) -> dict[str, pd.Series]:
        """Alle Jahresreihen zum Stichtag.

        Reihen ohne Revisionen (je Beobachtung ein Datenstand) laufen über einen schnellen
        Weg mit demselben Ergebnis wie ``PitSeries.as_of``.
        """
        out: dict[str, pd.Series] = {}
        cutoff = np.datetime64(pd.Timestamp(when).normalize(), "ns")
        for name, series in self.series.items():
            if name not in self._fast:
                frame = series.frame
                if frame["obs_date"].is_unique:
                    order = frame.sort_values("known_from")
                    self._fast[name] = (
                        order["known_from"].to_numpy(dtype="datetime64[ns]"),
                        order["obs_date"].to_numpy(dtype="datetime64[ns]"),
                        order["value"].to_numpy(dtype="float64"),
                    )
            fast = self._fast.get(name)
            if fast is None:
                out[name] = series.as_of(when)
                continue
            known, obs, values = fast
            n = int(np.searchsorted(known, cutoff, side="right"))
            sort = np.argsort(obs[:n], kind="stable")
            out[name] = pd.Series(values[:n][sort], index=pd.DatetimeIndex(obs[:n][sort]))
        return out


def load_owner_inputs(
    store: PitStore, score: DebtScoreConfig, owner: str, panel_only: bool = False
) -> OwnerInputs:
    """Lädt die Jahresreihen eines Landes des Tools bzw. eines Panel-Landes (ISO3)."""
    result = OwnerInputs(owner)
    iso3 = score.iso3.get(owner, owner)
    for name, item in score.inputs.items():
        if item.panel:
            key = input_key(iso3, name, item)
        elif panel_only:
            continue
        elif item.global_series:
            key = input_key("", name, item)
        else:
            if not item.symbol_for(owner, iso3):
                continue
            key = input_key(owner, name, item)
        series = store.load(key)
        if series is None or series.frame.empty:
            continue
        result.series[name] = annualize(series, item, owner)
    return result


# --------------------------------------------------------------------- Bestandteile
def _chain(*parts: pd.Series | None) -> pd.Series:
    """Verkettet Reihen: die erste hat Vorrang, spätere füllen Lücken (meist die Historie)."""
    out = pd.Series(dtype="float64")
    for part in parts:
        if part is None or part.empty:
            continue
        out = part.astype("float64") if out.empty else out.combine_first(part.astype("float64"))
    return out.sort_index()


def _years(series: pd.Series) -> pd.Series:
    """Lückenloser Jahresindex, damit ``shift`` Jahre zählt."""
    if series.empty:
        return series
    index = pd.date_range(series.index.min(), series.index.max(), freq="YE")
    return series.reindex(index)


def _change(series: pd.Series, years: int) -> pd.Series:
    full = _years(series)
    return (full - full.shift(years)).dropna()


def _pct_change(series: pd.Series, years: int) -> pd.Series:
    full = _years(series)
    return ((full / full.shift(years) - 1.0) * 100.0).dropna()


def _get(data: dict[str, pd.Series], name: str) -> pd.Series | None:
    value = data.get(name)
    return None if value is None or value.empty else value


def _sub(a: pd.Series | None, b: pd.Series | None) -> pd.Series | None:
    if a is None or b is None:
        return None
    return (a - b).dropna()


def component_history(data: dict[str, pd.Series]) -> pd.DataFrame:
    """Alle Bestandteile als Jahresreihen aus den bekannten Rohreihen eines Landes.

    Fehlende Rohreihen führen zu fehlenden Bestandteilen; das Gewicht der übrigen steigt.
    """
    g = lambda name: _get(data, name)  # noqa: E731
    out: dict[str, pd.Series] = {}

    debt = _chain(g("debt_fm"), g("debt_weo"), g("debt_fpp"), g("jst_debtgdp"))
    out["debt_gdp"] = debt
    out["debt_change_5y"] = _change(debt, 5) if not debt.empty else debt

    interest_recent = _sub(g("primary_balance_fm"), g("net_lending_weo"))
    revenue = _chain(g("revenue_fm"), g("revenue_fpp"))
    interest = _chain(interest_recent, g("interest_fpp"))
    if not interest.empty and not revenue.empty:
        out["interest_revenue"] = (interest / revenue.where(revenue > 0) * 100.0).dropna()

    growth_weo, inflation = g("real_growth_weo"), g("inflation_weo")
    nominal_growth = None
    if growth_weo is not None and inflation is not None:
        nominal_growth = (((1 + growth_weo / 100) * (1 + inflation / 100) - 1) * 100).dropna()
    jst_gdp = g("jst_gdp")
    jst_growth = _pct_change(jst_gdp, 1) if jst_gdp is not None else None
    rg = _chain(
        _sub(g("long_rate"), nominal_growth),
        _sub(g("real_rate_fpp"), g("real_growth_fpp")),
        _sub(g("jst_ltrate"), jst_growth),
    )
    if not rg.empty:
        out["r_minus_g"] = _years(rg).rolling(3, min_periods=2).mean().dropna()

    jst_balance = None
    rev, exp_ = g("jst_revenue"), g("jst_expenditure")
    if rev is not None and exp_ is not None and jst_gdp is not None:
        jst_balance = ((rev - exp_) / jst_gdp * 100.0).dropna()
    balance = _chain(g("primary_balance_fm"), g("primary_balance_fpp"), jst_balance)
    if not balance.empty:
        out["primary_deficit"] = -balance

    if g("term_premium") is not None:
        out["term_premium"] = data["term_premium"]

    assets = _chain(g("cb_assets"), g("cb_assets_m"))
    gdp = g("gdp_nominal")
    if not assets.empty and gdp is not None:
        ratio = (assets / gdp.where(gdp > 0) * 100.0).dropna()
        out["cb_assets_gdp"] = ratio
        out["cb_assets_change_3y"] = _change(ratio, 3)

    if g("gold_reserve_share") is not None:
        out["gold_reserve_share"] = data["gold_reserve_share"]

    fx = _chain(
        _pct_change(data["eer_broad"], 5) if g("eer_broad") is not None else None,
        _pct_change(data["eer_narrow"], 5) if g("eer_narrow") is not None else None,
    )
    if not fx.empty:
        out["fx_change_5y"] = fx

    jst_gap = None
    loans = g("jst_tloans")
    if loans is not None and jst_gdp is not None:
        credit = _years((loans / jst_gdp * 100.0).dropna())
        jst_gap = (credit - credit.rolling(15, min_periods=10).mean()).dropna()
    gap = _chain(g("credit_gap"), jst_gap)
    if not gap.empty:
        out["private_credit_gap"] = gap

    if g("dsr") is not None:
        out["debt_service_ratio"] = data["dsr"]

    frame = pd.DataFrame({k: v for k, v in out.items() if not v.empty})
    return frame.sort_index()


def latest_values(history: pd.DataFrame, when: pd.Timestamp) -> tuple[pd.Series, pd.Series]:
    """Jüngster Wert je Bestandteil (höchstens ``MAX_AGE_YEARS`` alt) und dessen Jahr."""
    values: dict[str, float] = {}
    years: dict[str, int] = {}
    for column in history.columns:
        clean = history[column].dropna()
        clean = clean[clean.index <= when]
        if clean.empty:
            continue
        year = int(clean.index[-1].year)
        if when.year - year > MAX_AGE_YEARS:
            continue
        values[column] = float(clean.iloc[-1])
        years[column] = year
    return pd.Series(values, dtype="float64"), pd.Series(years, dtype="Int64")


def owner_values(inputs: OwnerInputs, dates: Iterable[pd.Timestamp]) -> pd.DataFrame:
    """Werte der Bestandteile je Stichtag (Point-in-Time), Spalten ``Bestandteil`` und
    ``Bestandteil:year``.

    Neu gerechnet wird nur, wenn sich der bekannte Datenstand ändert.
    """
    dates = sorted(pd.Timestamp(d) for d in dates)
    changes = np.array(inputs.change_dates(), dtype="datetime64[ns]")
    rows: dict[pd.Timestamp, dict[str, float]] = {}
    for when in dates:
        state = int(np.searchsorted(changes, np.datetime64(when, "ns"), side="right"))
        key = (state, when.year)
        if key not in inputs._rows:
            history = component_history(inputs.as_of(when))
            values, years = latest_values(history, when)
            row = {**values.to_dict()}
            row.update({f"{k}:year": float(v) for k, v in years.items()})
            inputs._rows[key] = row
        rows[when] = inputs._rows[key]
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


# --------------------------------------------------------------------- Bewertung
def year_ends(start_year: int, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Jahresenden von ``start_year`` bis zum letzten abgeschlossenen Jahr vor ``end``."""
    last = end.year if end.month == 12 and end.day == 31 else end.year - 1
    return pd.date_range(f"{start_year}-12-31", f"{last}-12-31", freq="YE")


@dataclass
class ReferencePool:
    """Jahresendwerte aller Länder je Bestandteil, für Perzentile zum Stichtag."""

    frames: dict[str, pd.DataFrame]  # Bestandteil -> Spalten date, value

    def percentile(self, component: str, value: float, when: pd.Timestamp, minimum: int) -> float:
        """Anteil der bis ``when`` bekannten Referenzwerte unter ``value`` (Gleichstand halb)."""
        frame = self.frames.get(component)
        if frame is None or np.isnan(value):
            return float("nan")
        known = frame["value"].to_numpy()[frame["date"].to_numpy() <= np.datetime64(when, "ns")]
        if len(known) < minimum:
            return float("nan")
        below = float((known < value).sum())
        equal = float((known == value).sum())
        return (below + 0.5 * equal) / len(known)


def build_pool(
    year_end_values: dict[str, pd.DataFrame], components: Iterable[str]
) -> ReferencePool:
    """Referenzverteilung aus den Jahresendwerten (je Land eine Zeile pro Jahr)."""
    frames: dict[str, pd.DataFrame] = {}
    for component in components:
        parts = []
        for frame in year_end_values.values():
            if component in frame.columns:
                col = frame[component].dropna()
                parts.append(pd.DataFrame({"date": col.index, "value": col.to_numpy()}))
        if parts:
            frames[component] = pd.concat(parts, ignore_index=True).sort_values("date")
    return ReferencePool(frames)


def score_frame(values: pd.DataFrame, pool: ReferencePool, score: DebtScoreConfig) -> pd.DataFrame:
    """Perzentile (Spalten ``p:<Bestandteil>``) und Score je Stichtag."""
    enabled = {k: c for k, c in score.components.items() if c.enabled}
    out = pd.DataFrame(index=values.index)
    weights = pd.DataFrame(index=values.index)
    for name, component in enabled.items():
        if name not in values.columns:
            continue
        pct = [
            pool.percentile(name, float(v), when, score.min_reference)
            for when, v in values[name].items()
        ]
        oriented = pd.Series(pct, index=values.index, dtype="float64")
        if component.direction < 0:
            oriented = 1.0 - oriented
        out[f"p:{name}"] = oriented
        weights[name] = np.where(oriented.notna(), component.weight, 0.0)
    pcts = out[[c for c in out.columns if c.startswith("p:")]]
    total = weights.sum(axis=1) if not weights.empty else pd.Series(0.0, index=values.index)
    count = (weights > 0).sum(axis=1) if not weights.empty else pd.Series(0, index=values.index)
    weighted = sum(
        (pcts[f"p:{n}"].fillna(0.0) * weights[n] for n in weights.columns),
        start=pd.Series(0.0, index=values.index),
    )
    out["score"] = (weighted / total.where(total > 0) * 100.0).where(count >= score.min_components)
    out["components"] = count
    return out


def phase_for(row: pd.Series, thresholds: list[float], score: DebtScoreConfig) -> str | None:
    """Phase aus Score, Schuldenniveau und den Zusatzregeln (Entschuldung, Monetarisierung)."""
    value = row.get("score")
    if value is None or pd.isna(value):
        return None
    rules = score.rules
    debt_pct = row.get("p:debt_gdp", np.nan)
    high_debt = bool(pd.notna(debt_pct) and debt_pct >= rules.high_debt_percentile)
    change = row.get("debt_change_5y", np.nan)
    rg = row.get("r_minus_g", np.nan)
    deleveraging = bool(
        pd.notna(change) and change <= rules.deleveraging_pp and not (pd.notna(rg) and rg > 0)
    )
    cb_change = row.get("cb_assets_change_3y", np.nan)
    monetizing = bool(pd.notna(cb_change) and cb_change >= rules.monetization_pp)
    if high_debt and (deleveraging or monetizing):
        return "Entschuldung / Monetarisierung"
    t1, t2, t3 = thresholds
    if value < t1:
        return "gesund"
    if value < t2:
        return "Aufbau"
    if value < t3:
        return "Übertreibung"
    return "Spätphase (Finanzierungsstress)"


@dataclass
class DebtStressResult:
    """Ergebnis für alle Länder."""

    monthly: dict[str, pd.DataFrame]  # Land -> Werte, Perzentile, Score, Phase je Monatsende
    year_end: dict[str, pd.DataFrame]  # alle Länder inkl. Panel, Jahresenden
    thresholds: list[float]
    thresholds_fixed: bool
    calibration: pd.DataFrame
    coverage: pd.DataFrame
    panel_owners: list[str]

    def current(self, asof: pd.Timestamp | None = None) -> pd.DataFrame:
        """Stand je Land zum Stichtag (Standard: letzter Monat)."""
        rows = []
        for country, frame in self.monthly.items():
            if frame.empty:
                continue
            sub = frame if asof is None else frame[frame.index <= asof]
            if sub.empty:
                continue
            row = sub.iloc[-1]
            rows.append({"country": country, "date": sub.index[-1], **row.to_dict()})
        return pd.DataFrame(rows).set_index("country") if rows else pd.DataFrame()


def calibrate_thresholds(
    year_end: dict[str, pd.DataFrame], score: DebtScoreConfig
) -> tuple[list[float], pd.DataFrame]:
    """Schwellen als Quantile der Score-Verteilung (alle Länder, Jahre bis ``end_year``)."""
    values = []
    for frame in year_end.values():
        if "score" not in frame.columns:
            continue
        clean = frame["score"].dropna()
        values.append(clean[clean.index.year <= score.calibration.end_year])
    pooled = pd.concat(values) if values else pd.Series(dtype="float64")
    if pooled.empty:
        return [35.0, 60.0, 80.0], pd.DataFrame()
    q = score.calibration.quantiles
    thresholds = [round(float(pooled.quantile(x)), 1) for x in q]
    table = pd.DataFrame(
        {
            "Quantil": q,
            "Schwelle": thresholds,
            "Grenze": ["gesund | Aufbau", "Aufbau | Übertreibung", "Übertreibung | Spätphase"],
        }
    )
    table.attrs["n"] = len(pooled)
    table.attrs["years"] = (int(pooled.index.year.min()), int(pooled.index.year.max()))
    return thresholds, table


def run_debt_stress(
    config: AppConfig, store: PitStore, asof: pd.Timestamp | None = None
) -> DebtStressResult:
    """Score und Phase für alle Länder des Tools, Point-in-Time."""
    score = config.debt_cycle.score
    end = (pd.Timestamp.today() if asof is None else pd.Timestamp(asof)).normalize()
    targets = list(score.countries)
    target_iso = {score.iso3[c] for c in targets}
    panel_owners = [iso for iso in dict.fromkeys(score.panel) if iso not in target_iso]

    inputs: dict[str, OwnerInputs] = {c: load_owner_inputs(store, score, c) for c in targets}
    for iso in panel_owners:
        inputs[iso] = load_owner_inputs(store, score, iso, panel_only=True)

    ends = year_ends(score.panel_start_year, end)
    year_values = {owner: owner_values(item, ends) for owner, item in inputs.items()}
    pool = build_pool(year_values, score.components)

    year_end: dict[str, pd.DataFrame] = {}
    for owner, values in year_values.items():
        if values.empty:
            year_end[owner] = values
            continue
        year_end[owner] = values.join(score_frame(values, pool, score))

    if score.thresholds is not None:
        thresholds, fixed = list(score.thresholds), True
        _, calibration = calibrate_thresholds(year_end, score)
    else:
        thresholds, calibration = calibrate_thresholds(year_end, score)
        fixed = False

    for frame in year_end.values():
        if not frame.empty:
            frame["phase"] = [phase_for(r, thresholds, score) for _, r in frame.iterrows()]

    months = pd.date_range(score.start, end, freq="ME")
    monthly: dict[str, pd.DataFrame] = {}
    for country in targets:
        values = owner_values(inputs[country], months)
        if values.empty:
            monthly[country] = values
            continue
        frame = values.join(score_frame(values, pool, score))
        frame["phase"] = [phase_for(r, thresholds, score) for _, r in frame.iterrows()]
        monthly[country] = frame

    coverage_rows = []
    for owner, item in inputs.items():
        for name, series in item.series.items():
            latest = series.latest()
            coverage_rows.append(
                {
                    "owner": owner,
                    "input": name,
                    "first": int(latest.index.min().year) if not latest.empty else None,
                    "last": int(latest.index.max().year) if not latest.empty else None,
                    "median": float(latest.median()) if not latest.empty else None,
                }
            )
    return DebtStressResult(
        monthly=monthly,
        year_end=year_end,
        thresholds=thresholds,
        thresholds_fixed=fixed,
        calibration=calibration,
        coverage=pd.DataFrame(coverage_rows),
        panel_owners=panel_owners,
    )


def phase_distance(a: str | None, b: str | None) -> int | None:
    """Abstand zweier Phasen in der Reihenfolge der Spezifikation."""
    if a is None or b is None:
        return None
    return abs(PHASE_INDEX[a] - PHASE_INDEX[b])


def episode_check(result: DebtStressResult, score: DebtScoreConfig) -> pd.DataFrame:
    """Gemessene Phasen in den Episoden aus der Konfiguration (Jahresenden)."""
    rows = []
    for episode in score.episodes:
        frame = result.year_end.get(episode.country, pd.DataFrame())
        if frame.empty or "phase" not in frame.columns:
            phases = pd.Series(dtype="object")
        else:
            years = frame.index.year
            phases = frame.loc[(years >= episode.start) & (years <= episode.end), "phase"].dropna()
        counts = phases.value_counts()
        share = float(phases.isin(episode.expected).mean()) if len(phases) else float("nan")
        rows.append(
            {
                "Land": episode.country,
                "Jahre": f"{episode.start}–{episode.end}",
                "erwartet": ", ".join(episode.expected),
                "Jahre mit Score": len(phases),
                "Anteil erwartet": share,
                "gemessen": ", ".join(f"{k} {v}" for k, v in counts.items()),
                "Hinweis": episode.note,
            }
        )
    return pd.DataFrame(rows)
