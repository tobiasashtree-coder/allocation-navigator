# Allokations-Navigator

Strategisches Asset-Allocation-Tool nach Ray Dalios Zyklenlogik: Es bestimmt monatlich das
makroökonomische Regime und leitet daraus Empfehlungen für 18 Assetklassen ab. Basiswährung
EUR, umstellbar auf USD, CHF, GBP. Spezifikation: [`docs/SPEC.md`](docs/SPEC.md).

**Stand:** M0 (Grundgerüst) und M1 (Datenschicht) sind gebaut und offline getestet.
Regime-Erkennung, Empfehlungen, Backtest und Dashboard folgen in M2 bis M8.
Offene Punkte am Prüfpunkt: [`docs/checkpoints/M1.md`](docs/checkpoints/M1.md).

Das Tool liefert Analysen für die eigene Entscheidungsfindung, keine Anlageberatung.

## Einrichten

Voraussetzung: [uv](https://docs.astral.sh/uv/) (installiert auch Python 3.12).

```bash
git clone https://github.com/tobiasashtree-coder/allocation-navigator.git
cd allocation-navigator
uv sync --all-groups
uv run navigator --help
```

API-Keys: `.env.example` nach `.env` kopieren und eintragen. `.env` wird nie eingecheckt.

| Key | Wofür | Pflicht |
| --- | --- | --- |
| `FRED_API_KEY` | US-Makrodaten mit Datenständen zu früheren Zeitpunkten (ALFRED) | ja |
| `TIINGO_API_KEY` | Zweitquelle für US-Fonds und ETFs (Kreuzprüfung) | empfohlen |

## Daten laden und prüfen

```bash
uv run navigator config check            # Konfiguration prüfen, Hash anzeigen
uv run navigator data sources --probe    # jede Reihe bei jeder Quelle abrufen (Ticker, IDs, Startdaten)
uv run navigator data update             # alle Reihen laden, Point-in-Time-Speicher pflegen, Snapshot
uv run navigator data validate           # Validierungsbericht nach reports/validation_latest.html
```

Ohne Netz und Keys lässt sich der Ablauf mit synthetischen Daten ausprobieren:

```bash
uv run navigator data update --demo
uv run navigator data validate --demo
```

Demo-Daten sind Zufallsreihen. Sie liegen getrennt in `data_demo/` und `reports_demo/` und
sagen nichts über echte Märkte aus.

### Über GitHub statt lokal

Der Workflow **Live-Daten (manuell)** unter *Actions* führt dieselben drei Schritte auf
GitHub aus und legt den Bericht als Artefakt und in der Zusammenfassung des Laufs ab.
Dazu unter *Settings → Secrets and variables → Actions* die Secrets `FRED_API_KEY` und
`TIINGO_API_KEY` anlegen.

### Dateien, die du von Hand ablegen kannst

Manche Quellen erlauben keinen automatischen Abruf oder verlangen eine Registrierung.
Das Tool meldet dann, welche Datei fehlt.

| Datei | Inhalt |
| --- | --- |
| `data/static/manual/<Datensatz>.<Endung>` | Ersatz für einen gescheiterten Download (z. B. `aqr_tsmom.xlsx`, `nareit.xls`) |
| `data/static/manual/gold_monthly_usd.csv` | Goldpreis des World Gold Council: Spalten `date,USD` |
| `data/static/issuer_nav/<Fonds>.xls` | NAV-Historie eines UCITS-ETF von der Emittenten-Seite |

Eckwerte privater Infrastruktur:

```bash
uv run navigator data infra import                       # Seiten abrufen bzw. Erinnerung anlegen
uv run navigator data infra list
uv run navigator data infra confirm 0001                 # erst bestätigte Werte werden verwendet
uv run navigator data infra add msci_private_infra_12m 2026-Q1 8.4 --source <URL>
```

## Leitprinzipien

- **Point-in-Time-Korrektheit:** Jede Entscheidung zum Zeitpunkt t nutzt nur Daten, die zu t
  veröffentlicht waren. Look-ahead-Tests verändern alle Daten nach t und prüfen, dass sich
  nichts bis t ändert.
- **Transparenz:** Jede Reihe trägt Quelle, Abrufzeitpunkt und Qualitätskennzeichen
  (Original, Proxy, synthetisch); Backfill ist je Monat markiert.
- **Reproduzierbarkeit:** Datenstände als Snapshots, Konfiguration in Git, jeder Lauf mit
  Zeitstempel und Konfigurations-Hash in `data/runs/runs.jsonl`.
- **Robustheit vor Optimierung:** wenige, ökonomisch begründete Parameter in `config/`.

## Entwicklung

```bash
uv run pytest                                   # 100+ Tests, ohne Netz
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit install                       # Prüfungen vor jedem Commit
```

Entscheidungen und Abweichungen von der Spezifikation: [`docs/decisions.md`](docs/decisions.md).
Arbeitsregeln für den Coding-Agenten: [`CLAUDE.md`](CLAUDE.md).

## Lizenzen der Daten

Yahoo-Daten, Tiingo (Gratis-Tarif), AQR und die Jordà-Schularick-Taylor-Datenbank sind nur
für private, nicht-kommerzielle Nutzung freigegeben. Eine Weitergabe der Ergebnisse an Dritte
wäre lizenz- und aufsichtsrechtlich gesondert zu prüfen.
