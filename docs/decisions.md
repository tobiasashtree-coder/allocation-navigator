# Designentscheidungen

Jede Entscheidung mit Datum, Alternativen und Grund. Abweichungen von `docs/SPEC.md` sind mit
**Abweichung** markiert. Die Einträge stammen vom 16. und 17.11.2026 (M0 und M1); wo ein
Eintrag auf dem Lauf mit echten Daten vom 17.11.2026 beruht, steht „Live-Lauf" dabei.

## Rahmen

| Nr. | Entscheidung | Alternativen | Grund |
| --- | --- | --- | --- |
| E-01 | Stopp am Prüfpunkt M1; M2 beginnt erst nach Freigabe. | M0 bis M8 in einem Zug gegen Testdaten. | Vom Nutzer so gewählt. Die Entwicklungsumgebung erreicht keine Datenquelle; die Datenschicht muss erst mit echten Daten bestätigt sein. |
| E-02 | Code liegt im privaten GitHub-Repository; CI auf Ubuntu und Windows. | Lokaler Ordner, ZIP. | Vom Nutzer so gewählt. Windows in der CI, weil das Tool dort läuft. |
| E-03 | Workflow „Live-Daten (manuell)" ruft die Quellen auf GitHub ab und legt den Bericht ab. | Nur lokaler Lauf. | So lassen sich Ticker, Reihen-IDs und Startdaten ohne lokalen Aufwand prüfen und nachvollziehen. |
| E-04 | Demo-Modus (`--demo`) mit synthetischen Reihen in eigenen Ordnern (`data_demo`, `reports_demo`). | Aufgezeichnete echte Antworten als Testdaten. | Echte Antworten waren nicht abrufbar. Getrennte Ordner und Kennzeichnung verhindern, dass Zufallsdaten mit echten vermischt werden. |
| E-05 | Abhängigkeiten späterer Meilensteine (statsmodels, scikit-learn, hmmlearn, scipy, cvxpy, Streamlit, Plotly, DuckDB) kommen erst mit ihrem Meilenstein in `pyproject.toml`. | Alles sofort installieren. | Schlanke Umgebung; keine ungenutzten Pakete in der CI. |

## Datenquellen

| Nr. | Entscheidung | Alternativen | Grund |
| --- | --- | --- | --- |
| E-10 | **Abweichung:** FRED/ALFRED, die SDMX-Quellen, Tiingo und Coin Metrics werden direkt per HTTP angesprochen, nicht über `fredapi`, `sdmx1`, `coinmetrics-api-client`. yfinance bleibt als Bibliothek. | Bibliotheken laut Tech-Stack (9.1). | ALFRED braucht Seitenweises Laden und das Aufteilen vieler Vintages, was `fredapi` nicht leistet. Ein gemeinsamer SDMX-CSV-Client deckt fünf Quellen ab. Die Parser sind ohne Netz gegen die dokumentierten Antwortformate getestet. |
| E-11 | **Abweichung:** Bundesbank als zusätzliche Quelle (Zinsstruktur der Bundeswertpapiere ab 1972 als Monatsendstände; D-Mark-Kurse 1948 bis 1998). | Nur OECD/FRED-Monatsdurchschnitte der 10J.-Rendite. | Die Spezifikation nennt die Bundesbank als Herkunft der Bund-Renditen. Monatsendstände ergeben sauberere synthetische Renditen als Monatsdurchschnitte. Frei, ohne Key. |
| E-12 | **Abweichung:** Kein Backfill für High Yield. Im Wachstumsscore ersetzt der Spread Moody's Baa minus 10J.-Treasury (`BAA10Y`) den High-Yield-Spread. | ICE-Lizenz; High Yield synthetisch aus Baa-Renditen. | FRED liefert die ICE-BofA-Reihen seit April 2026 nur noch für drei Jahre. Eine synthetische High-Yield-Reihe aus Baa wäre nicht belastbar. Folge: High Yield fehlt in der langen Historie vor Fondsstart. |
| E-13 | **Abweichung:** Rohstoff-Backfill über AQR „Commodities for the Long Run" (gleichgewichtete Futures-Überrendite plus USD-Geldmarkt). | S&P GSCI Total Return. | Der GSCI Total Return ist nicht frei verfügbar. Einschränkung: gleichgewichtet statt energielastig. |
| E-14 | **Abweichung:** Gold-Backfill über die Monatsdurchschnitte der Weltbank („Pink Sheet", ab 1960). World-Gold-Council-Daten nur als manuell abgelegte CSV. | WGC-Download; Londoner Fixing der Bundesbank. | WGC verlangt eine Registrierung. Die Bundesbank liefert das Londoner Fixing nicht mehr (Live-Lauf: HTTP 404). Nachteil: Durchschnitte glätten die Monatsrenditen; die Naht zu GLD bleibt unkalibriert (Korrelation 0,53). |
| E-15 | Aktien Europa und Japan: French-Regionalfaktoren ab 07/1990, davor French International Indices bzw. Countries (`.Dat`) ab 1975. | Nur ab 1990. | Die lange Historie soll 1973 beginnen; 1975 ist der früheste freie Start. Im Live-Lauf bestätigt (Naht-Korrelationen 0,99). |
| E-19 | **Abweichung:** Bitcoin über die Coin-Metrics-Metrik `PriceUSD` statt des Referenzkurses. | `ReferenceRateUSD`. | Live-Lauf: Der Referenzkurs kommt ohne Lizenz nur für sieben Tage; `PriceUSD` reicht bis 07/2010 zurück. Der Provider bevorzugt jetzt die Metrik mit voller Historie. |
| E-16 | Das zweite Instrument der Proxy-Spalte (SPY, EEM, TLT, TIP, LQD, HYG, EMB, DBC, VNQ, KMLM, GC=F) ist Ersatzinstrument: Es greift nur, wenn der Hauptproxy bei allen Quellen ausfällt. | Als eigenes Segment verketten. | Der Hauptproxy hat jeweils die längere Historie; ein zweites Segment brächte keinen früheren Start. |
| E-17 | Automatische Abrufe von Webseiten (MSCI, Infrastructure Investor, Emittenten) sind standardmäßig **nicht** freigegeben (`automated_access: unknown`). Das Tool legt dann eine Erinnerung an bzw. liest manuell abgelegte Dateien. Zusätzlich wird `robots.txt` geprüft. | Standardmäßig abrufen. | Die Spezifikation verlangt, die Nutzungsbedingungen zu beachten. Ob sie den Abruf erlauben, muss ein Mensch entscheiden und dann je Seite `allowed` setzen. |
| E-18 | EUR-Staatsanleihen lang: iShares Core € Govt Bond wie spezifiziert, obwohl der ETF alle Laufzeiten abdeckt (Duration rund 7 Jahre). | iShares € Govt Bond 7-10yr oder 15-30yr. | Spezifikation befolgt. **Offene Frage am Prüfpunkt**, weil die Klasse „lang (7–10+ J.)" heißt. |

## Point-in-Time und Datenaufbereitung

| Nr. | Entscheidung | Alternativen | Grund |
| --- | --- | --- | --- |
| E-20 | Jede Makroreihe speichert `obs_date`, `value`, `known_from`. Herkunft von `known_from`: echte ALFRED-Vintages; sonst Verzögerungsregel je Reihe; für Werte vor Beginn der ALFRED-Historie ebenfalls die Regel (Kennzeichen `approx`); selbst beobachtete Revisionen ab Abrufdatum. | Nur Verzögerungsregel für alles. | Größtmögliche Genauigkeit, wo Vintages existieren, und eine ehrliche Kennzeichnung, wo nicht. |
| E-21 | Neue Beobachtungen einer Quelle ohne Vintages gelten ab dem früheren von Verzögerungsregel und Abrufdatum. | Immer die Regel. | Im Monatsbetrieb soll ein Wert nutzbar sein, sobald er tatsächlich vorliegt. |
| E-22 | Gleitende Kalibrierung an der Naht: beta der Ersatzreihe im Fenster von 36 Monaten nach Proxy-Start, zur Hälfte Richtung 1 geschrumpft, begrenzt auf 0,5 bis 2; mindestens 12 Monate und Korrelation 0,6, sonst unkalibriert mit Warnung. Es zählen nur Daten bis zum Stichtag. **Kein Niveauausgleich (alpha = 0).** | Kalibrierung über die ganze Überlappung (nutzt künftige Daten); keine Kalibrierung; zusätzlich alpha. | Point-in-Time hat Vorrang. Folge: In den ersten 36 Monaten nach einem Proxy-Start kann sich die Backfill-Historie von Stichtag zu Stichtag leicht ändern. Zu alpha: Ein Renditeunterschied aus 36 Monaten ist statistisch nicht belastbar. Im Live-Lauf hätte er die Trendfolge-Historie um rund 5 % p. a. angehoben und EUR-Anleihen um rund 2 % p. a. gedrückt. |
| E-23 | Die Naht bestimmt sich aus den vorhandenen Daten, nicht aus `expected_start`. Abweichungen über 12 Monate meldet der Bericht. | Feste Startdaten. | Yahoo liefert manche Fonds später als ihr Auflagedatum. |
| E-24 | Wechselkurse: ab 1999 EZB-Referenzkurse, davor Fed-Tageskurse (H.10) für GBP, CHF, JPY; der Euro vor 1999 synthetisch über die D-Mark (1,95583) aus dem Frankfurter Fixing der Bundesbank (1948 bis 1998), ersatzweise Monatsmittel der Fed (`EXGEUS`). Intern „USD je Einheit". | Nur ab 1999; FRED `DEXGEUS`. | Die lange Historie braucht EUR-Renditen ab 1973. `DEXGEUS` existiert bei FRED nicht (Live-Lauf). Frankfurter und New Yorker Kurse haben verschiedene Uhrzeiten; das erzeugt vor 1999 kleines Rauschen in den Kreuzkursen. |
| E-25 | Cash-Rendite = Monatsmittel des Kurzfristzinses / 12. Sicherung = Lokalrendite + Cash Basis − Cash Fremdwährung. EUR: €STR, davor EONIA, davor 3M-Geldmarkt Deutschland. | Terminkurse. | Näherung laut Spezifikation. Tagesgeld und 3M-Sätze werden gemischt; das ist ungenau, aber frei verfügbar. |
| E-26 | Währungseinfluss je Monat = Rendite in Basiswährung − Lokalrendite in Notierungswährung; bei gesicherten Klassen ist das die Zinsdifferenz. Die Durchschau auf Regionen (`fx_exposure`) ist konfiguriert und wird in M5 ausgewertet. | Volle Durchschau schon in M1. | M1 braucht Umrechnung und Sicherung; die Zerlegung der Empfehlung gehört zu M5. |
| E-27 | Synthetische Anleihen: Duration und Konvexität einer Pari-Anleihe mit halbjährlichem Kupon. Bundesbank-Nullkuponrenditen gelten näherungsweise als Pari-Renditen. US lang: 30J.-Rendite (Laufzeit 25) ab 1977, davor 10J.-Rendite mit Kalibrierung. | Exakte Nullkupon-Bewertung. | Formel aus Abschnitt 9.5. Die Prüfung gegen Fondsrenditen (Korrelation über 0,95) zeigt, ob die Näherung trägt. |
| E-28 | Synthetische TIPS dienen nur als Gegenprüfung und Ersatz. | Als Backfill. | Der Fonds (2000) beginnt früher als die Realrenditen (2003). Vor 2000 bleibt die Klasse eine Lücke. |
| E-29 | Jeder `data update` legt einen Snapshot an: Kopie der Rohdaten und des Point-in-Time-Speichers mit SHA-256 je Datei, Konfigurations-Hash und Abrufergebnissen. | Nur Hashes. | Reproduzierbarkeit: Ein Backtest lässt sich später exakt auf einem Datenstand wiederholen. |

## Festzuschreibende Parameter mit Status „Entwurf"

Diese Werte stehen in `config/`, sind aber in der Spezifikation nicht oder nicht eindeutig
beziffert. Sie müssen bestätigt sein, bevor der jeweilige Meilenstein beginnt, und sind
danach festgeschrieben.

| Datei | Parameter | Entwurf | Fällig vor |
| --- | --- | --- | --- |
| `regime_map.yaml` | Erwartungsvektoren je Klasse und Quadrant (−2 bis +2) | aus Abbildung 4.2 und „Rolle im Regime" abgeleitet | M2 |
| `indicators.yaml` | Eurozone: OECD-Frühindikator Deutschland als Näherung; kein freier 5J5J-Inflationsswap; Lohnreihe fehlt | siehe Datei | M2 |
| `base.yaml` | Bitcoin im Stagflations-Korb; Halbwertszeit 30 Monate; tau 0,05; „kleine Klassen" für ±5 Pp. | siehe Datei | M5 |
| `debt_cycle.yaml` | lambda je Phase; Anteil der US-Aktien-Umschichtung (25 %); Obergrenze ungesichertes USD-Exposure (30 %) | siehe Datei | M4 |
| `backtest.yaml` | Kosten für Trendfolge (20 Bp.) und Bitcoin (25 Bp.) | siehe Datei | M6 |

## Prüfstatus der Kennungen

Arbeitsregel: Ticker, Startdaten und Reihen-IDs vor Verwendung prüfen. Geprüft wurde im
Lauf mit echten Daten vom 17.11.2026 (GitHub-Workflow „Live-Daten", ohne API-Keys). Die
vollständige Liste mit Start, Ende und Anzahl der Werte je Reihe steht in
`docs/checkpoints/M1-validierung-2026-11-17.md`, Tabelle „Rohreihen je Quelle".

| Bereich | Stand |
| --- | --- |
| Alle Yahoo-Ticker (US-Fonds und ETFs, `IBCA.DE`, `EUNH.DE`, `IQQI.DE`, `HICL.L`, `INPP.L`, `3IN.L`, `URTH`, `BTC-USD`, `GC=F`) | bestätigt |
| FRED-Reihen über den CSV-Abruf (Renditen, Wechselkurse, Makro) | bestätigt; ICE-BofA-Spread nur drei Jahre |
| EZB (Wechselkurse, €STR, EONIA, Euribor), OECD (Zinsen, Frühindikatoren), BIS (Kreditlücke, Schuldendienst), Bundesbank (Zinsstruktur, D-Mark) | bestätigt |
| Kenneth French (alle sieben Dateien, auch `.Dat`), AQR (Trendfolge, Rohstoffe), Nareit, Weltbank | bestätigt |
| Coin Metrics | bestätigt mit `PriceUSD` |
| Eurostat | drei von vier Reihen bestätigt; Arbeitslosenquote (`une_rt_m`) wird abgelehnt |
| EZB Kern-HVPI (`ICP/M.U2.N.XEF000.4.INX`) | liefert Daten, endet aber 12/2025 |
| FRED mit API-Key (ALFRED-Vintages), Tiingo | **ungeprüft**, braucht die Keys |
| Emittenten-NAVs, MSCI, Infrastructure Investor, JST | **ungeprüft** (kein automatischer Abruf freigegeben bzw. erst ab M4 gebraucht) |
