# Allokations-Navigator

Strategisches Asset-Allocation-Tool nach Ray Dalios Zyklenlogik: Es bestimmt monatlich das
makroökonomische Regime und leitet daraus Empfehlungen für 18 Assetklassen ab. Basiswährung
EUR, umstellbar auf USD, CHF, GBP. Spezifikation: [`docs/SPEC.md`](docs/SPEC.md).

**Stand:** Alle Meilensteine M0 bis M8 sind gebaut und getestet: Datenschicht, Regime-Erkennung
(Methode A regelbasiert, Methode B mit Hidden-Markov-Modell), langfristiger Schuldenzyklus als
Overlay, Empfehlungs-Engine, Backtest, Dashboard und Monatsbetrieb. Abnahmen und Prüfpunkte:
[`docs/checkpoints/`](docs/checkpoints/).

Das Tool liefert Analysen für die eigene Entscheidungsfindung, keine Anlageberatung. Im
Backtest war der Vorsprung der Regime-Steuerung gegenüber der Basis nicht statistisch
gesichert (Placebo-p-Wert 0,11, siehe [`docs/checkpoints/M6.md`](docs/checkpoints/M6.md)).

## Kurzanleitung: der Monatslauf

Einmal im Monat, nach dem Monatsende:

```bash
uv run navigator monthly        # Datenabruf, Validierung, Regime, Schuldenzyklus, Empfehlung, Bericht
uv run navigator dashboard      # Ergebnis ansehen: http://localhost:8501
```

`navigator monthly` läuft ohne Eingriffe durch. Am Ende steht je Schritt der Status
(`ok`, `Warnung`, `Fehler`, `übersprungen`). Scheitert ein Schritt, laufen die übrigen weiter,
soweit sie nicht auf ihm aufbauen. Ohne erfolgreichen Datenabruf entfallen alle Auswertungen,
damit nie alte Daten als neu erscheinen. Der Rückgabewert ist 1, wenn ein Schritt
gescheitert ist.

| Ergebnis | Inhalt |
| --- | --- |
| `reports/monthly_latest.md` und `.html` | Monatsbericht: Ablauf, **empfohlene Gewichtung zum Stichtag** mit Ampel, Begründung und Änderung zum Vormonat, Regime, Schuldenzyklus |
| `reports/monthly/<Stichtag>.md` | Archiv der Monatsberichte |
| `reports/recommend_latest.md`, `recommend_targets.csv` | Empfehlung im Detail, alle Varianten |
| `reports/validation_latest.html` | Datenqualität |
| `reports/regime_a_latest.md`, `regime_b_latest.md`, `debt_latest.md` | Regime und Schuldenzyklus im Detail |

Optionen: `--asof 2026-10-31` (Stichtag), `--backtest` (Backtest mitrechnen, rund
30 Minuten), `--simulations 100` (schnelleres Resampling). `navigator report` schreibt den
Monatsbericht aus den vorhandenen Ergebnissen neu, ohne etwas neu zu rechnen.

**Stichtag** ist das letzte Monatsende: Viele Reihen erscheinen nur monatlich.

### Automatisch jeden Monat (Windows)

In der Aufgabenplanung eine Aufgabe anlegen, z. B. am 3. jedes Monats um 7 Uhr:

- Programm: `powershell.exe`
- Argumente: `-NoProfile -Command "cd 'C:\Pfad\zum\allocation-navigator'; uv run navigator monthly *> reports\monthly_log.txt"`

Unter macOS/Linux entsprechend per `cron`:
`0 7 3 * * cd ~/allocation-navigator && uv run navigator monthly > reports/monthly_log.txt 2>&1`

## Einzelne Schritte

```bash
uv run navigator data update                      # Daten laden
uv run navigator data validate                    # Datenqualität prüfen
uv run navigator regime run --method both         # Regime nach Methode A und B
uv run navigator debt run                         # langfristiger Schuldenzyklus
uv run navigator recommend [--portfolio ist.csv]  # Empfehlung; optional aktuelles Portfolio (asset,weight)
uv run navigator backtest                         # Backtest aller Vergleichsstrategien (rund 30 Min.)
uv run navigator dashboard                        # Dashboard mit sechs Reitern
```

Mit `--portfolio` bezieht sich das No-Trade-Band und die Umschlaggrenze auf dein tatsächliches
Portfolio statt auf die Basis. Die Datei hat die Spalten `asset,weight`; die Kürzel stehen in
`config/universe.yaml`.

Im Dashboard ändern Einstellungen in der Seitenleiste (Methode, Overlay, Basis, Tracking Error,
Umschlag, Basiswährung) nie die Konfiguration; sie werden als **Szenario** gerechnet und so
gekennzeichnet. Das Dashboard beendest du mit Strg + C im Terminal (das Schließen des
Browser-Tabs reicht nicht).

## Einrichten

Voraussetzung: [uv](https://docs.astral.sh/uv/) (installiert auch Python 3.12).

```bash
git clone https://github.com/tobiasashtree-coder/allocation-navigator.git   # oder ZIP von GitHub entpacken
cd allocation-navigator                                                      # Pfade mit Leerzeichen in Anführungszeichen
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

Der Workflow **Live-Daten (manuell)** unter *Actions* führt Datenabruf, Validierung, Regime,
Schuldenzyklus, Empfehlung und (abschaltbar) Backtest auf GitHub aus und legt die Berichte als
Artefakt und in der Zusammenfassung des Laufs ab.
Dazu unter *Settings → Secrets and variables → Actions* die Secrets `FRED_API_KEY` und
`TIINGO_API_KEY` anlegen.

### Dateien, die du von Hand ablegen kannst

Manche Quellen erlauben keinen automatischen Abruf oder verlangen eine Registrierung.
Das Tool meldet dann, welche Datei fehlt.

| Datei | Inhalt |
| --- | --- |
| `data/static/manual/<Datensatz>.<Endung>` | Ersatz für einen gescheiterten Download (z. B. `aqr_tsmom.xlsx`, `nareit.xls`) |
| `data/static/manual/gold_monthly_usd.csv` | Optional: Monatsendpreise Gold des World Gold Council, Spalten `date,USD`; danach in `config/universe.yaml` beim Gold-Backfill `static: "gold_manual:USD"` eintragen |
| `data/static/issuer_nav/<Fonds>.xls` | NAV-Historie eines UCITS-ETF von der Emittenten-Seite |
| `data/static/manual/gold_reserves_manual.csv` | Optional: Gold-Anteil an den Weltreserven (World Gold Council), Spalten `date,share` |

Eckwerte privater Infrastruktur:

```bash
uv run navigator data infra import                       # Seiten abrufen bzw. Erinnerung anlegen
uv run navigator data infra list
uv run navigator data infra confirm 0001                 # erst bestätigte Werte werden verwendet
uv run navigator data infra add msci_private_infra_12m 2026-Q1 8.4 --source <URL>
```

## Häufige Meldungen

| Meldung | Abhilfe |
| --- | --- |
| `No pyproject.toml found` | Im falschen Ordner: in den Ordner wechseln, in dem `pyproject.toml` liegt |
| `failed to remove file …navigator.exe` (os error 32) | Das Dashboard läuft noch: Strg + C im Terminal oder `navigator.exe` im Task-Manager beenden |
| `HTTP 403` bei `imf` | Der IMF blockt Abrufe aus manchen Netzen; der Schuldenzyklus rechnet dann mit JST, BIS und FRED weiter |
| `manuelle Datei fehlt … gold_reserves_manual.csv` | Erwartet: optionale Datei, siehe oben |

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
uv run pytest                                   # rund 180 Tests, ohne Netz
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
