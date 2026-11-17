# Arbeitsregeln für den Coding-Agenten

Dieses Repository enthält den **Allokations-Navigator**: ein strategisches
Asset-Allocation-Tool nach Ray Dalios Zyklenlogik. Die vollständige Spezifikation steht in
`docs/SPEC.md`. Lies sie, bevor du Code änderst.

## Stand

- Fertig: **M0**, **M1**, **M2** (Methode A), **M3** (Methode B und Vergleich; Prüfpunkt
  freigegeben am 17.11.2026 mit Variante 2, Marktmerkmale als Veränderung).
- In Arbeit: **M4** (Schuldenzyklus-Overlay, freigegeben am 17.11.2026). Danach M5, M6 und
  Prüfpunkt nach M6.
- Echte Daten erreicht nur der GitHub-Workflow „Live-Daten (manuell)" oder ein lokaler Lauf;
  die Cloud-Entwicklungsumgebung erreicht die Datenquellen nicht. Berichte stehen im Log des
  Laufs (`gh run view <id> --log`), Artefakte sind von dort nicht ladbar.

## Arbeitsweise

- Meilensteine M0 bis M8 strikt nacheinander. Ein Meilenstein ist erst fertig, wenn sein
  Abnahmekriterium erfüllt und getestet ist.
- Nach M1, M3 und M6 anhalten: Ergebnisse, Abweichungen von der Spezifikation und offene
  Fragen in `docs/checkpoints/` zusammenfassen und auf Freigabe warten.
- `docs/decisions.md` führen: jede Designentscheidung mit Datum, Alternativen, Grund.

## Regeln

1. **Point-in-Time-Korrektheit hat Vorrang vor allem anderen.** Jede Funktion, die Daten
   für ein Datum t liefert, bekommt einen Test, der beweist, dass keine Daten nach t
   einfließen. Hilfen dafür stehen in `src/navigator/testing.py`
   (`perturb_parquet_tree`, `assert_no_lookahead`).
2. Im Backtest nur **gefilterte** HMM-Wahrscheinlichkeiten, nie geglättete oder Viterbi.
3. **Keine Parameter auf die Historie optimieren.** Alle Parameter stehen in `config/` und
   werden vor dem Backtest festgeschrieben.
4. Ticker, Startdaten und Datenreihen-IDs vor Verwendung prüfen
   (`navigator data sources --probe`); Abweichungen in `docs/decisions.md` festhalten.
5. Alle Logik im Paket `src/navigator`; CLI und Dashboard rufen nur das Paket auf.
6. Schrumpfung, Black-Litterman, Resampling und Risikoparität folgen dem Buch
   <https://quantseminar.de/book/> (Kapitel 4 bis 7). Liegen Kurs-Notebooks unter
   `notebooks/reference/`, Ergebnisse dagegen prüfen.
7. **Kein kostenpflichtiger Datendienst.** EODHD, SIPA und MSCI nur als deaktivierte Provider.
8. Typannotationen, Docstrings auf Deutsch, `ruff` und `mypy` ohne Fehler.
9. **Keine Secrets** im Code oder Repository; Keys nur über Umgebungsvariablen (`.env` lokal,
   Repository-Secrets in der CI).
10. Wenn eine Datenquelle ausfällt: Ersatzquelle laut Spezifikation, Warnung ins Log, **nie
    stillschweigend falsche oder veraltete Daten verwenden**.
11. Demo-Daten (`--demo`) sind synthetisch. Sie liegen getrennt in `data_demo/` und dürfen
    nie für Aussagen über Märkte, Regime oder Backtests verwendet werden.

## Befehle

```bash
uv sync --all-groups          # Umgebung einrichten
uv run pytest                 # Tests (ohne Netz)
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run navigator --help
uv run navigator data update --demo && uv run navigator data validate --demo   # Ablauf ohne Netz
```

## Aufbau der Datenschicht

| Modul | Aufgabe |
| --- | --- |
| `data/providers/` | Quellen hinter einer Schnittstelle (`fetch_series`, `capabilities`, `license`) |
| `data/cache.py` | Parquet-Cache mit Abrufzeitpunkt, inkrementell, Rückfall mit Kennzeichen `stale` |
| `data/pit.py` | Point-in-Time-Speicher: `obs_date`, `value`, `known_from` |
| `data/fx.py` | Wechselkurse, Geldmarktrenditen, Währungssicherung |
| `data/synthetic.py` | Synthetische Anleiherenditen aus Renditereihen |
| `data/backfill.py` | Verkettung von Proxy und Backfill mit gleitender Kalibrierung |
| `data/universe.py` | Monatliche Total-Return-Reihen aller Klassen je Basiswährung und Stichtag |
| `data/validate.py` | Prüfungen und Validierungsbericht |
| `data/pipeline.py` | Abläufe: Abruf, Snapshot, Validierung |
| `features/scores.py` | Point-in-Time-z-Werte je Indikator (`pit_values`), Achsen-Scores je Region |
| `features/credit_cycle.py` | Kurzfristiger Schuldenzyklus (Mehrheitsregel, Schwellen in `regime_map.yaml`) |
| `regimes/rules.py` | Quadranten-Wahrscheinlichkeiten, neutrales Band, Bestätigungsregel |
| `regimes/method_a.py` | Methode A gesamt, Episoden-Check, Bericht (`navigator regime run --method a`) |
| `features/market.py` | Merkmale der Methode B (Indikatoren plus Marktmerkmale, standardisiert) |
| `regimes/hmm.py` | HMM mit eigenem Vorwärtsfilter (nur gefiltert), GMM-Gegencheck, Benennung |
| `regimes/compare.py` | Übereinstimmung, Kreuztabelle, Begründung, Überzeugung |
| `regimes/method_b.py` | Methode B gesamt und Bericht (`navigator regime run --method both`) |
| `data/debt.py` | Rohreihen des Schuldenstress-Scores (Schlüssel `debt.*`) |
| `features/debt_stress.py` | Langfristiger Schuldenzyklus: Score 0–100, Perzentile, Phasen, Kalibrierung |
| `allocation/overlay.py` | Overlay-Vektoren mit λ je Phase, vorläufige Basis bis M5 |
| `reporting/debt.py` | Bericht Schuldenzyklus (`navigator debt run`) |
