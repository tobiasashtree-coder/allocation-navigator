"""Allokations-Navigator: Dashboard mit sechs Reitern (Spezifikation 9.4).

Start: ``navigator dashboard [--demo]``. Liest die Schnappschüsse von ``navigator recommend``,
``navigator backtest``, ``navigator regime run`` und ``navigator debt run``. Änderungen in der
Seitenleiste werden nicht in die Konfiguration geschrieben, sondern als Szenario gerechnet.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from navigator.dashboard.data import Context, agreement, context_from_env, regime_history, scenario
from navigator.reporting.views import View, detail_display

COLORS = {
    "disinflationary_boom": "#2ca02c",
    "reflation": "#ff7f0e",
    "deflationary_bust": "#1f77b4",
    "stagflation": "#d62728",
    "financial_stress": "#7f7f7f",
}
LABELS = {
    "disinflationary_boom": "Disinflationärer Aufschwung",
    "reflation": "Reflation / Überhitzung",
    "deflationary_bust": "Deflationäre Rezession",
    "stagflation": "Stagflation",
    "financial_stress": "Finanzstress",
}
BASES = {"risk_parity": "Risikoparität", "equal_weight": "Gleichgewichtung"}
VARIANTS = {"a": "Methode A", "b": "Methode B", "ab": "Zusammenführung A + B"}


def regime_bands(series: pd.Series, name: str) -> go.Figure:
    """Zeitstrahl mit farbigen Regime-Bändern."""
    fig = go.Figure()
    clean = series.dropna()
    for regime, color in COLORS.items():
        mask = clean == regime
        if mask.any():
            fig.add_trace(
                go.Bar(
                    x=clean.index[mask],
                    y=[1] * int(mask.sum()),
                    marker_color=color,
                    name=LABELS[regime],
                    width=31 * 24 * 3600 * 1000,
                )
            )
    fig.update_layout(
        barmode="stack",
        height=170,
        title=name,
        yaxis={"visible": False},
        margin={"t": 30, "b": 10},
        bargap=0,
    )
    return fig


def sidebar(ctx: Context) -> dict[str, Any]:
    """Einstellungen; Änderungen werden als Szenario gekennzeichnet."""
    st.sidebar.header("Einstellungen")
    cfg = ctx.config
    target = cfg.base.outputs["target_weights"]
    method = st.sidebar.selectbox(
        "Methode", list(VARIANTS), index=2, format_func=lambda k: VARIANTS[k]
    )
    show_overlay = st.sidebar.toggle("Mit Overlay", value=True)
    strength = st.sidebar.slider(
        "Overlay-Stärke", 0.0, 1.0, float(cfg.debt_cycle.overlay_strength), 0.05
    )
    base_method = st.sidebar.selectbox(
        "Basisallokation",
        ["risk_parity", "equal_weight"],
        format_func=lambda k: BASES[k],
    )
    te = st.sidebar.slider(
        "Tracking Error max.", 0.005, 0.08, float(target["tracking_error_max"]), 0.005
    )
    turnover = st.sidebar.slider(
        "Umschlag max. je Quartal", 0.05, 0.5, float(target["turnover_max_quarter"]), 0.05
    )
    currency = st.sidebar.selectbox(
        "Basiswährung",
        ["EUR", "USD", "CHF", "GBP"],
        index=["EUR", "USD", "CHF", "GBP"].index(cfg.currency.base),
    )
    changed = (
        abs(strength - cfg.debt_cycle.overlay_strength) > 1e-9
        or base_method != "risk_parity"
        or abs(te - float(target["tracking_error_max"])) > 1e-9
        or abs(turnover - float(target["turnover_max_quarter"])) > 1e-9
        or currency != cfg.currency.base
    )
    run = False
    if changed:
        st.sidebar.warning("Einstellungen weichen von der Konfiguration ab: Szenario.")
        run = st.sidebar.button("Szenario berechnen")
    return {
        "method": method,
        "overlay": show_overlay,
        "strength": strength,
        "base": base_method,
        "te": te,
        "turnover": turnover,
        "currency": currency,
        "changed": changed,
        "run": run,
    }


def tab_overview(ctx: Context, rec: View | None, settings: dict[str, Any]) -> None:
    st.subheader("Übersicht")
    if rec is None:
        st.info("Noch keine Empfehlung. Erst `navigator recommend` ausführen.")
        return
    v = rec.values
    cols = st.columns(4)
    cols[0].metric("Stichtag", v["asof"])
    cols[1].metric("Überzeugung (A vs. B)", f"{v['conviction']:.2f}")
    probs = rec.tables["probs"]
    for i, method in enumerate(("a", "b")):
        if method in probs.columns:
            cols[2 + i].metric(
                f"Regime {VARIANTS[method]}",
                str(probs[method].idxmax()),
                f"{probs[method].max():.0%}",
            )
    debt = ctx.csv("debt_history.csv", parse_dates=["date"])
    if debt is not None and "phase" in debt.columns:
        last = debt.sort_values("date").groupby("country").last()[["score", "phase"]]
        st.markdown("**Schuldenzyklus (gemessen)**")
        st.dataframe(last, use_container_width=True)
    key = _variant_key(settings)
    if f"detail:{key}" in rec.tables:
        st.markdown(f"**Ampel ({key})**")
        st.dataframe(rec.tables[f"detail:{key}"][["Klasse", "Ampel"]], use_container_width=True)


def tab_regime(ctx: Context) -> None:
    st.subheader("Regime")
    a, b = regime_history(ctx)
    if a is None or b is None:
        st.info("Noch keine Regime-Historie. Erst `navigator regime run --method both` ausführen.")
        return
    st.plotly_chart(regime_bands(a["regime"], "Methode A (global)"), use_container_width=True)
    st.plotly_chart(
        regime_bands(b[("B", "regime")], "Methode B (USA, gefiltert)"), use_container_width=True
    )
    rate, table = agreement(b)
    st.metric("Übereinstimmung A und B über die Historie", f"{rate:.0%}")
    st.markdown("**Kreuztabelle (Zeilen: A, Spalten: B, Monate)**")
    st.dataframe(table.rename(index=LABELS, columns=LABELS), use_container_width=True)
    if ("vergleich", "begruendung") in b.columns:
        last = b[("vergleich", "begruendung")].dropna()
        if not last.empty:
            st.markdown("**Begründung der Abweichung (aktuell)**")
            st.write(str(last.iloc[-1]))
    report = ctx.markdown("regime_b_latest.md")
    if report:
        with st.expander("Bericht Methode B und Vergleich"):
            st.markdown(report)


def tab_debt(ctx: Context) -> None:
    st.subheader("Schuldenzyklus")
    debt = ctx.csv("debt_history.csv", parse_dates=["date"])
    if debt is None:
        st.info("Noch kein Schuldenzyklus. Erst `navigator debt run` ausführen.")
        return
    fig = go.Figure()
    for country, frame in debt.groupby("country"):
        fig.add_trace(
            go.Scatter(x=frame["date"], y=frame["score"], name=str(country), mode="lines")
        )
    fig.update_layout(height=320, title="Schuldenstress-Score 0–100", margin={"t": 30})
    st.plotly_chart(fig, use_container_width=True)
    last = debt.sort_values("date").groupby("country").last()
    rows = []
    for country in ctx.config.debt_cycle.score.countries:
        entry = ctx.config.debt_cycle.assessments.get(country, {})
        measured = last["phase"].get(country) if "phase" in last else None
        rows.append(
            {
                "Land": country,
                "Score": last["score"].get(country),
                "gemessen": measured,
                "manuell": entry.get("phase"),
                "Gegenposition": entry.get("counter_position", ""),
            }
        )
    st.dataframe(pd.DataFrame(rows).set_index("Land"), use_container_width=True)
    report = ctx.markdown("debt_latest.md")
    if report and "## Warnungen" in report:
        warn = report.split("## Warnungen", 1)[1].split("## ", 1)[0]
        st.warning(warn.strip())


def _variant_key(settings: dict[str, Any]) -> str:
    return f"{settings['method']}{'+overlay' if settings['overlay'] else ''}"


def tab_recommend(ctx: Context, rec: View | None, settings: dict[str, Any]) -> None:
    st.subheader("Empfehlungen")
    if rec is None:
        st.info("Noch keine Empfehlung. Erst `navigator recommend` ausführen.")
        return
    if rec.values.get("scenario"):
        st.warning(f"SZENARIO (nicht die Konfiguration): {rec.values['scenario']}")
    key = _variant_key(settings)
    if f"detail:{key}" not in rec.tables:
        st.info(f"Variante {key} nicht vorhanden.")
        return
    st.markdown(f"**Ampel, Über-/Untergewichtung, Zielgewichte: {key}**")
    st.dataframe(detail_display(rec, key), use_container_width=True, key="detail_table")
    cols = st.columns(4)
    cols[0].metric("Tracking Error", f"{rec.values['tracking_error'][key]:.2%}")
    cols[1].metric("Umschlag", f"{rec.values['turnover'][key]:.1%}")
    cols[2].metric("Active Share", f"{rec.values['active_share'][key]:.1%}")
    failed = [k for k, ok in rec.values["checks"][key].items() if not ok]
    cols[3].metric(
        "Restriktionen", "eingehalten" if not failed else "verletzt: " + ", ".join(failed)
    )
    without = settings["method"]
    if settings["overlay"] and f"detail:{without}" in rec.tables:
        compare = pd.DataFrame(
            {
                "ohne Overlay %": rec.tables["targets"][without] * 100,
                "mit Overlay %": rec.tables["targets"][key] * 100,
            }
        )
        st.markdown("**Mit und ohne Overlay**")
        st.dataframe(compare, use_container_width=True)
    parts = rec.tables[f"parts:{key}"]
    asset = st.selectbox("Zerlegung für Klasse", list(parts.index))
    row = parts.loc[asset] * 100
    fig = go.Figure(
        go.Waterfall(
            x=["Basis", "Regime", "Overlay", "Restriktionen", "Ziel"],
            measure=["absolute", "relative", "relative", "relative", "total"],
            y=[row["Basis"], row["Regime"], row["Overlay"], row["Restriktionen"], 0],
        )
    )
    fig.update_layout(height=300, title=f"Zerlegung {asset} (Pp.)", margin={"t": 30})
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Währungen ({rec.values['base_currency']})**")
    st.write(
        "Exposure: "
        + ", ".join(f"{k} {v:.1%}" for k, v in sorted(rec.values["exposure"].items()))
        + f" · Anteil der Wechselkurse am Risiko: {rec.values['currency_risk']:.1%}"
    )
    st.dataframe(rec.tables["currency"], use_container_width=True)


def tab_backtest(ctx: Context) -> None:
    st.subheader("Backtest")
    bt = ctx.view("backtest")
    if bt is None:
        st.info("Noch kein Backtest. Erst `navigator backtest` ausführen.")
        return
    returns = bt.tables["returns"]
    returns.index = pd.to_datetime(returns.index)
    fig = go.Figure()
    for col in returns.columns:
        fig.add_trace(
            go.Scatter(x=returns.index, y=(1 + returns[col].fillna(0)).cumprod(), name=col)
        )
    fig.update_layout(height=380, yaxis_type="log", title="Wertentwicklung", margin={"t": 30})
    st.plotly_chart(fig, use_container_width=True)
    regimes = bt.tables["regimes"]["regime"]
    regimes.index = pd.to_datetime(regimes.index)
    st.plotly_chart(
        regime_bands(regimes[regimes.index >= returns.index.min()], "Regime (Methode A)"),
        use_container_width=True,
    )
    for title, key in (
        ("Prüfzeitraum ab 2008", "metrics_test"),
        ("Entwicklung bis 2007", "metrics_dev"),
        ("Gesamt", "metrics_all"),
    ):
        st.markdown(f"**{title}**")
        st.dataframe(bt.tables[key], use_container_width=True)
    v = bt.values
    st.markdown(
        f"**Placebo:** p-Wert {v['placebo_p']:.3f} (echte Sharpe {v['placebo_reference']:.3f}); "
        f"**Deflated Sharpe** {v['deflated']:.3f} bei {v['n_trials']} Varianten."
    )
    placebo = bt.tables["placebo"]
    if not placebo.empty:
        hist = go.Figure(go.Histogram(x=placebo["Sharpe"], nbinsx=40))
        hist.add_vline(x=v["placebo_reference"], line_color="red")
        hist.update_layout(height=260, title="Placebo-Sharpe-Ratios", margin={"t": 30})
        st.plotly_chart(hist, use_container_width=True)
    st.markdown("**Sensitivität**")
    st.dataframe(bt.tables["sensitivity"], use_container_width=True)


def tab_data(ctx: Context) -> None:
    from navigator.data.providers.private_infra import PrivateInfraStore

    st.subheader("Daten und Qualität")
    report = ctx.markdown("validation_latest.md")
    if report:
        st.markdown(report)
    else:
        st.info("Noch kein Validierungsbericht. Erst `navigator data validate` ausführen.")
    store = PrivateInfraStore(ctx.paths.processed / "private_infra.json")
    pending = [v for v in store.load() if v.status == "pending"]
    st.markdown("**Private Infrastruktur: neu importierte Werte**")
    if not pending:
        st.write("Keine offenen Werte.")
    for value in pending:
        cols = st.columns([4, 1, 1])
        cols[0].write(
            f"{value.series} {value.period}: {value.value} {value.unit} ({value.source_url})"
        )
        if cols[1].button("Bestätigen", key=f"ok-{value.id}"):
            store.set_status(value.id, "confirmed")
            st.rerun()
        if cols[2].button("Verwerfen", key=f"no-{value.id}"):
            store.set_status(value.id, "rejected")
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Allokations-Navigator", layout="wide")
    ctx = context_from_env()
    st.title("Allokations-Navigator")
    if ctx.demo:
        st.error(
            "DEMO-DATEN: synthetische Reihen, keine Aussage über Märkte, Regime oder Backtests."
        )
    settings = sidebar(ctx)
    rec = ctx.view("recommend")
    if settings["run"]:
        with st.spinner("Szenario wird gerechnet …"):
            st.session_state["scenario"] = scenario(
                ctx,
                float(settings["strength"]),
                str(settings["base"]),
                float(settings["te"]),
                float(settings["turnover"]),
                str(settings["currency"]),
            )
    if settings["changed"] and "scenario" in st.session_state:
        rec = st.session_state["scenario"]
    elif not settings["changed"]:
        st.session_state.pop("scenario", None)
    tabs = st.tabs(
        ["Übersicht", "Regime", "Schuldenzyklus", "Empfehlungen", "Backtest", "Daten und Qualität"]
    )
    with tabs[0]:
        tab_overview(ctx, rec, settings)
    with tabs[1]:
        tab_regime(ctx)
    with tabs[2]:
        tab_debt(ctx)
    with tabs[3]:
        tab_recommend(ctx, rec, settings)
    with tabs[4]:
        tab_backtest(ctx)
    with tabs[5]:
        tab_data(ctx)


main()
