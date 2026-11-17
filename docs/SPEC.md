<!-- Exportiert aus dem Claude-Doc https://claude.ai/artifact/Tjjme9Y2hcaVsWqth8qEGL (Revision 45, Stand 2026-11-16). Abbildungen sind als Tabelle bzw. Text wiedergegeben. -->

# Projektspezifikation: Strategischer Asset-Allocation-Navigator (Dalio-Zyklen)

2026-11-16 · Tobias

## 1. Zielbild und Leitprinzipien

Der **Allokations-Navigator** (Arbeitstitel) bestimmt jeden Monat das makroökonomische Regime nach Ray Dalios Zyklenlogik und leitet daraus strategische Empfehlungen für Assetklassen ab. Perspektive: ein langfristig orientierter institutioneller Investor mit Basiswährung EUR. Das Tool ist für die eigene Nutzung bestimmt, soll aber methodisch so sauber sein, dass es einem Investmentkomitee standhalten würde.

**Kernfunktionen**

1. Total-Return-Zeitreihen aller Assetklassen und Makrodaten automatisiert laden, prüfen und versioniert speichern.
2. Regime zweifach bestimmen: regelbasiert (Methode A) und statistisch (Methode B), getrennt dargestellt, Abweichungen erklärt.
3. Langfristigen Schuldenzyklus als qualitatives Overlay einbeziehen, das die Allokation spürbar verschiebt.
4. Drei Empfehlungsformen ausgeben: Regime-Ampel, Über-/Untergewichtung gegenüber einer Basisallokation, konkrete Zielgewichte.
5. Alles backtesten, gegen statische Benchmarks vergleichen und robust gegen Überanpassung absichern.
6. Bereitstellung als Python-Paket mit Kommandozeile (CLI) und als interaktives Dashboard.

**Leitprinzipien**

- **Point-in-Time-Korrektheit:** Jede Entscheidung zum Zeitpunkt t nutzt nur Daten, die zu t veröffentlicht waren (Veröffentlichungsverzögerungen und Datenrevisionen berücksichtigen). Das ist die wichtigste Qualitätsanforderung.
- **Transparenz:** Jede Empfehlung lässt sich bis auf die einzelnen Indikatoren und ihre Werte zurückverfolgen.
- **Robustheit vor Optimierung:** Wenige, ökonomisch begründete Parameter; keine Feinjustierung auf die Historie.
- **Reproduzierbarkeit:** Datenstände als Snapshots, Konfiguration in Versionskontrolle, jeder Lauf mit Zeitstempel und Konfigurations-Hash protokolliert.
- **Strategische Restriktionen:** nur Long-Positionen, kein Hebel, Analyse monatlich, Umschichtung höchstens quartalsweise mit No-Trade-Bändern.
- **Währung:** Basis EUR, umstellbar (z. B. USD, CHF, GBP). Anleihen abgesichert; Aktien, Sachwerte und Bitcoin ungesichert. Währungseinflüsse werden stets getrennt ausgewiesen (Abschnitt 7.6).

**Nicht-Ziele:** keine Einzeltitel- oder ETF-Auswahl, kein Trading oder Market-Timing auf Tages- oder Wochenbasis, keine Orderausführung, keine Steueroptimierung, keine Beratung Dritter.

## 2. Anlageuniversum

Das Universum umfasst 18 Assetklassen in fünf Gruppen. Gegenüber dem ersten Entwurf sind drei Aufsplittungen neu, weil sie für Dalios Logik entscheidend sind:

- **Aktien nach Regionen** (USA, Europa, Japan, Schwellenländer): Das Schuldenzyklus-Overlay bewertet Länder unterschiedlich, insbesondere die USA als Reservewährungsland mit hoher Verschuldung.
- **Staatsanleihen nach Währung und Laufzeit** (EUR kurz/lang, US-Treasuries lang): Lange Laufzeiten reagieren am stärksten auf Wachstums- und Inflationsüberraschungen sowie auf ein Spannungsszenario am Anleihemarkt.
- **Gold getrennt von Rohstoffen:** Gold ist in Dalios Rahmen eine Währungsalternative, kein Konjunkturrohstoff, und verhält sich in späten Schuldenzyklus-Phasen anders.

Dazu kommen **Infrastruktur** als eigene Klasse, optional **Trendfolge (Managed Futures)** als Diversifikator, der in stagflationären Phasen wie 2022 häufig positiv war, sowie **Bitcoin** als aktivierte optionale Klasse. Für Bitcoin gelten Sonderregeln: Obergrenze 3 % Gesamtgewicht; kein Merkmal in der Regime-Erkennung; Regime-Renditen wegen der kurzen Historie (ab etwa 2010) stark zur ökonomischen Annahme geschrumpft. Das Schuldenzyklus-Overlay darf Bitcoin bis zur Obergrenze anheben, weil Dalio eine kleine Beimischung als Schutz vor Währungsabwertung nennt.

| Gruppe | Assetklasse | Rolle im Regime | Freier Proxy (Start ca.) | Backfill vor Proxy-Start |
| --- | --- | --- | --- | --- |
| Aktien | USA | Wachstum steigend | VFINX (1976), SPY | Kenneth French Marktportfolio (ab 1926) |
| Aktien | Europa | Wachstum steigend | VGK (2005), EZU (2000) | French International Data (Europa, ab 1975) |
| Aktien | Japan | Wachstum steigend | EWJ (1996) | French International Data (Japan, ab 1975) |
| Aktien | Schwellenländer | Wachstum steigend, schwacher USD | VEIEX (1994), EEM | French Emerging Markets (ab 1989) |
| Anleihen | EUR-Staatsanleihen kurz (1–3 J.) | Deflation, Rezession | iShares € Govt 1-3yr UCITS | synthetisch aus Bund-Renditen (Bundesbank) |
| Anleihen | EUR-Staatsanleihen lang (7–10+ J.) | Wachstum und Inflation fallend | iShares Core € Govt Bond UCITS | synthetisch aus 10J.-Bund-Rendite (OECD/FRED, ab 1956) |
| Anleihen | US-Treasuries lang (gesichert) | Wachstum und Inflation fallend | VUSTX (1986), TLT (2002) | synthetisch aus FRED DGS10/DGS30 |
| Anleihen | Inflationsindexiert (TIPS / €-Linker) | Inflation steigend, Wachstum fallend | VIPSX (2000), TIP (2003) | synthetisch aus Realrenditen (FRED DFII10, ab 2003); davor Lücke |
| Anleihen | Unternehmensanleihen IG | Wachstum moderat, Inflation fallend | VWESX (1973), LQD (2002) | Moody's-Baa-Rendite (FRED) |
| Anleihen | High Yield | Wachstum steigend | VWEHX (1978), HYG (2007) | Spread-Reihe ICE BofA HY (FRED) |
| Anleihen | Schwellenländeranleihen (optional) | Wachstum steigend, schwacher USD | PREMX (1994), EMB (2007) | keine; Start 1994 |
| Sachwerte | Gold | Inflation steigend, Währungsabwertung | GLD (2004), GC=F | World Gold Council Monatspreise (ab 1978) |
| Sachwerte | Rohstoffe breit | Inflation steigend, Wachstum steigend | PCRIX (2002), DBC (2006) | S&P GSCI TR, Verfügbarkeit prüfen |
| Sachwerte | Immobilien (REITs) | Wachstum steigend, Inflation moderat | VGSIX (1996), VNQ (2004) | FTSE Nareit All Equity REITs (ab 1972) |
| Sachwerte | Infrastruktur (börsennotiert) | Inflation steigend, defensiv | INFR UCITS (2006), IGF (2007) | French-Industrieportfolios Versorger + Telekom (ab 1926) |
| Diversifikatoren | Trendfolge (optional) | Krisen und Stagflation | DBMF (2019), KMLM (2020) | AQR Time Series Momentum (ab 1985) |
| Diversifikatoren | Bitcoin (optional, aktiviert) | Währungsabwertung, reichliche Liquidität | BTC-USD über yfinance (2014) | Coin Metrics Referenzkurs (ab ca. 2010, prüfen) |
| Liquidität | Cash in Basiswährung | Deflation, Unsicherheit | €STR (EZB) | Euribor/EONIA (EZB), davor Geldmarktsatz DE (OECD) |

**Infrastruktur im Detail.** Primärer Referenzindex ist der [FTSE Global Core Infrastructure Index](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/ftse-global-core-infrastructure-indexes.pdf). Aufgenommen werden nur Unternehmen mit mindestens 65 % Umsatz aus Kerninfrastruktur. Der [iShares Global Infrastructure UCITS ETF](https://www.ishares.com/uk/professional/en/products/251809/ishares-global-infrastructure-ucits-etf) bildet ihn seit Oktober 2006 ab und ist der längste UCITS-Proxy. Als Gegencheck dient der S&P Global Infrastructure Index (über IGF).

**Private Infrastruktur, automatischer Import.** Börsennotierte Infrastruktur korreliert kurzfristig stark mit Aktien. Deshalb importiert das Tool Vergleichswerte für nicht börsennotierte Infrastruktur in drei Stufen:

1. **Veröffentlichte Eckwerte:** Ein Parser liest die frei zugänglichen Quartalsergebnisse des [MSCI Global Quarterly Private Infrastructure Asset Index](https://www.msci.com/data-and-analytics/private-asset-solutions/global-private-infrastructure-asset-index-q1-2026-results) (z. B. 12-Monats-Rendite) und die monatlichen infra300-Meldungen von [Infrastructure Investor](https://www.infrastructureinvestor.com/infra300-posts-best-monthly-return-in-2026/). Jeder neue Wert wird mit Quelle und Abrufdatum gespeichert und erst nach Bestätigung im Dashboard verwendet. Erlauben die Nutzungsbedingungen einer Seite kein automatisches Abrufen, erzeugt das Tool stattdessen eine Erinnerung zur manuellen Eingabe.
2. **Börsennotierte NAV-Näherung:** NAV-basierte Total Returns britischer Infrastruktur-Investmentgesellschaften mit nicht börsennotierten Portfolios (z. B. HICL Infrastructure, International Public Partnerships, 3i Infrastructure). Kurse kommen automatisch über yfinance, NAV-Werte per Parser aus den Unternehmensmeldungen. Ihre NAVs folgen Bewertungen privater Infrastruktur und sind damit eine frei verfügbare, automatisierbare Näherung.
3. **Lizenz-Schnittstelle (vorbereitet):** Provider-Platzhalter für SIPA (infra300) und MSCI, deaktiviert, bis eine Lizenz vorliegt.

Eine vollständige Quartalsreihe der lizenzierten Indizes ist ohne Lizenz nicht automatisch zu bekommen; die kostenlose Bereitstellung des infra300 über AWS Data Exchange wurde [zum 30.06.2023 eingestellt](https://aws.amazon.com/marketplace/pp/prodview-4fa6qefiwyoiy). Private Werte sind bewertungsbasiert und geglättet. Sie dienen deshalb nur der Plausibilisierung, nach Entglättung (Geltner-Verfahren), nicht der Optimierung.

**Regeln für Proxies:** Alle Proxies sind bereinigte Total-Return-Reihen (Dividenden reinvestiert). Backfill-Reihen werden nur für den Zeitraum vor Proxy-Start verwendet, an der Naht mit gleitender Kalibrierung verkettet und im Dashboard sichtbar markiert. Jede Klasse trägt ein Qualitätskennzeichen (Original, Proxy, synthetisch). Tickers und Startdaten sind beim Implementieren zu verifizieren.

## 3. Datenquellen und Schnittstellen

Empfehlung: **yfinance allein reicht nicht.** Es ist eine inoffizielle Schnittstelle ohne Gewähr, liefert Kurse erst ab ETF-Start und keine Makrodaten. Das Tool nutzt deshalb einen Quellen-Mix in drei Schichten, jede hinter einer gemeinsamen Provider-Schnittstelle, damit Quellen austauschbar bleiben.

| Schicht | Quelle | Inhalt | Zugang | Bewertung |
| --- | --- | --- | --- | --- |
| Makro | [FRED / ALFRED](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) (Python: fredapi) | US-Makro, Renditen, Spreads, Inflationserwartungen; **Datenstände zu früheren Zeitpunkten (Vintages)** | kostenlos, API-Key | Pflicht. Einzige freie Quelle mit sauberer Point-in-Time-Historie |
| Makro | EZB Data Portal | €STR, Euribor, HVPI, Geldmenge, Kredite, EUR-Wechselkurse | kostenlos, ohne Key | Pflicht für EUR-Sicht |
| Makro | Eurostat, OECD (SDMX) | BIP, Industrieproduktion, Composite Leading Indicators, Kurzfristzinsen weiterer Währungen | kostenlos, ohne Key | Pflicht für Europa/Japan und andere Basiswährungen |
| Makro | [BIS Data Portal](https://data.bis.org/topics/CREDIT_GAPS) | Kredit/BIP-Lücke (44 Länder, ab 1961), Schuldendienstquoten, Staatsverschuldung, Wechselkurse | kostenlos, SDMX ohne Key | Pflicht für Schuldenzyklus |
| Markt | yfinance (Yahoo Finance) | Bereinigte Kurse von ETFs, Fonds, Indizes, Futures, auch UCITS-Notierungen an Xetra (.DE) und London (.L) | kostenlos, inoffiziell | Primärquelle für Kurse, mit Cache und Validierung |
| Markt | [Tiingo](https://api.tiingo.com/documentation) | US-Aktien, ETFs, Investmentfonds, dividendenbereinigt | kostenlos mit Key (ca. 50 Anfragen/Std., 1.000/Tag) | Zweitquelle für US-Proxies |
| Markt | NAV-Downloads der Emittenten (iShares, Xtrackers, Amundi) | Historische NAVs von UCITS-ETFs als Excel/CSV | kostenlos, Verfügbarkeit je Emittent prüfen | Zweitquelle für EUR-notierte Proxies, ersetzt vorerst EODHD |
| Markt | [Coin Metrics Community API](https://docs.coinmetrics.io/packages/coin-metrics-community-data) | Bitcoin-Referenzkurse, volle Tageshistorie | kostenlos ohne Key, max. 10 Anfragen je 6 Sek., Creative-Commons-Lizenz | Primärquelle Bitcoin, yfinance als Zweitquelle |
| Markt | Private Infrastruktur | MSCI-Quartalsergebnisse, infra300-Meldungen, Infrastruktur-Investmentgesellschaften | öffentliche Seiten und yfinance | Automatischer Import laut Abschnitt 2 |
| Markt | [EODHD](https://eodhd.com/pricing), SIPA, MSCI | Weltweite Kurse und Indizes bzw. lizenzierte Private-Markets-Indizes | kostenpflichtig | **Schnittstelle vorbereitet, deaktiviert** (kein Abo) |
| Historie | [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) | Aktienrenditen USA ab 1926, international ab 1975, Industrieportfolios | kostenlos, Download | Backfill Aktien und Infrastruktur |
| Historie | [Jordà-Schularick-Taylor Macrohistory](https://www.nber.org/research/data/jorda-schularick-taylor-macrohistory) | 17 Industrieländer ab 1870, jährlich: Total Returns von Aktien, Anleihen, Immobilien, Bills; Kredit und Verschuldung | kostenlos (nicht kommerziell) | Langfristiger Schuldenzyklus, Plausibilisierung |
| Historie | AQR Data Library, World Gold Council, FTSE Nareit, Shiller | Trendfolge, Gold, REITs, US-Bewertung | kostenlos, teils Registrierung | Backfill einzelner Klassen |

**Verworfen oder nur Notfall:** [Stooq](https://github.com/pydata/pandas-datareader/issues/1012) verlangt seit März 2026 einen API-Key und hat ein Tageslimit. Alpha Vantage ist mit 25 Aufrufen pro Tag im Gratis-Tarif zu knapp. Bloomberg, Refinitiv und MSCI-Direktdaten sind ohne Abo nicht verfügbar.

**Provider-Schnittstelle für spätere Abos.** Jede Quelle implementiert dieselbe Schnittstelle (`fetch_series`, `capabilities`, `license`) und steht mit einer Priorität in `config/sources.yaml`. Ein späteres Abo wird aktiviert, indem man den API-Key in `.env` setzt und den Provider in der Konfiguration einschaltet. Er übernimmt dann automatisch die höchste Priorität für die Reihen, die er abdeckt; ein Codeumbau ist nicht nötig. Bis dahin liefern die kostenlosen Quellen alle Reihen.

**Anforderungen an die Datenschicht**

- Lokaler Cache (Parquet) mit Abrufzeitpunkt pro Reihe; erneute Abrufe nur inkrementell.
- Jede Marktreihe wird gegen eine Zweitquelle geprüft; Abweichungen über 0,5 % Monatsrendite werden protokolliert und im Dashboard gezeigt.
- Prüfungen auf Lücken, Sprünge, fehlende Dividenden und Split-Fehler.
- Makrodaten tragen Beobachtungs- **und** Veröffentlichungsdatum. Wo keine Vintages existieren (EZB, Eurostat, OECD), gilt eine konservative Veröffentlichungsverzögerung je Reihe (z. B. BIP +2 Monate, Inflation +1 Monat).
- Währungsumrechnung in EUR über EZB-Referenzkurse; Währungssicherung näherungsweise als Lokalrendite plus Zinsdifferenz (EUR minus Fremdwährung) auf Monatsbasis.
- Kalenderbasis für alle Analysen: Monatsende.

## 4. Methodik A: Regelbasierte Regime-Erkennung

Methode A ordnet jeden Monat einem von vier Quadranten zu, gebildet aus zwei Achsen: Wachstum und Inflation, jeweils **in ihrer Veränderung**, nicht im Niveau. Das folgt Dalios Kernaussage, dass Märkte auf Abweichungen von den Erwartungen reagieren. Darauf liegt als zweite Schicht der kurzfristige Schuldenzyklus.

### 4.1 Wachstums- und Inflationsscore

Je Region (USA, Eurozone, optional Japan, China) und als BIP-gewichtetes globales Aggregat:

| Score | Indikatoren (Quelle) | Transformation |
| --- | --- | --- |
| Wachstum | OECD Composite Leading Indicator; Industrieproduktion; Arbeitslosenquote (invertiert); Zinskurve 10J.–3M; High-Yield-Spread (invertiert); reale Einzelhandelsumsätze | 6-Monats-Veränderung, als z-Wert gegen ein rollierendes 10-Jahres-Fenster |
| Inflation | Kerninflation (3M annualisiert minus 12M); 5J5J-Breakeven-Inflation; Rohstoffpreis-Momentum; Lohnwachstum; Erzeugerpreise | wie oben |

Der Score einer Achse ist der Mittelwert der z-Werte ihrer Indikatoren, begrenzt auf ±3:

```latex
S_t = \frac{1}{N}\sum_{i=1}^{N} \operatorname{clip}\left(\frac{\Delta_6 x_{i,t} - \mu_{i,t}^{(120)}}{\sigma_{i,t}^{(120)}},\,-3,\,3\right)
```

### 4.2 Quadranten und Wahrscheinlichkeiten

**Abbildung: Vier Regime (Wachstum × Inflation). Jedes Regime begünstigt andere Assetklassen.**

| | Inflation fällt | Inflation steigt |
| --- | --- | --- |
| **Wachstum steigt** | **Disinflationärer Aufschwung:** Aktien aller Regionen; Unternehmensanleihen IG und HY; Immobilien (REITs) | **Reflation / Überhitzung:** Rohstoffe, Schwellenländeraktien; High Yield, Schwellenländeranleihen; Infrastruktur |
| **Wachstum fällt** | **Deflationäre Rezession:** Lange Staatsanleihen (EUR, USA); Kurze Staatsanleihen, Cash; Gold bei Finanzstress | **Stagflation:** Gold; Inflationsindexierte Anleihen; Infrastruktur, Trendfolge |

Die Zuordnung ist die ökonomische Ausgangsannahme aus `regime_map.yaml`; Abschnitt 4.4 beschreibt, wie der Backtest sie prüft.

Damit Methode A mit Methode B vergleichbar ist, werden die Scores über eine logistische Funktion in Wahrscheinlichkeiten übersetzt: P(Wachstum steigt) = 1 / (1 + e^(−k · S)), mit k = 1,5. Die vier Quadranten-Wahrscheinlichkeiten ergeben sich als Produkt der Achsen-Wahrscheinlichkeiten. Gegen hektisches Hin- und Herspringen gilt: Ein Regimewechsel zählt erst, wenn der neue Quadrant zwei Monate in Folge führt oder seine Wahrscheinlichkeit 60 % überschreitet. Scores zwischen −0,25 und +0,25 gelten als neutral.

### 4.3 Kurzfristiger Schuldenzyklus (5–8 Jahre)

Die zweite Schicht bestimmt die Phase der Geld- und Kreditpolitik:

| Phase | Typische Signale | Tendenz der Allokation |
| --- | --- | --- |
| Frühe Expansion | Leitzins sinkt oder tief, Zinskurve steil, Spreads engen ein | Aktien, High Yield, Rohstoffe aufstocken |
| Mittlere Expansion | Leitzins steigt langsam, Kreditwachstum über Trend | neutral, Qualität bevorzugen |
| Späte Expansion | realer Leitzins über neutralem Zins, Kurve flach oder invers, Spreads sehr eng | Duration aufbauen, Kredit reduzieren, Gold halten |
| Kontraktion | Spreads weiten sich, Leitzinssenkungen beginnen, Kreditwachstum fällt | lange Staatsanleihen, Cash, danach Aktien schrittweise zurück |

Indikatoren: realer Leitzins abzüglich geschätztem neutralem Zins (Laubach-Williams-Schätzung der NY Fed), Zinskurve, Kreditwachstum gegen Trend, Spread-Trend, Schuldendienstquote privater Haushalte und Unternehmen (BIS). Jede Phase hat ausdrückliche, im Code dokumentierte Schwellenwerte.

### 4.4 Zuordnung von Assetklassen zu Regimen

Die Grundzuordnung folgt der All-Weather-Logik: Jede Klasse hat einen Erwartungsvektor (Vorzeichen und Stärke) je Quadrant, hinterlegt in einer YAML-Datei. Diese Werte sind **ökonomische Annahmen**, nicht optimiert. Der Backtest prüft, ob die historischen Durchschnittsrenditen je Regime die Vorzeichen bestätigen; Abweichungen werden berichtet, aber nicht automatisch übernommen.

## 5. Methodik B: Statistische Regime-Erkennung und Vergleich

Methode B lässt die Daten die Regime selbst finden. Hauptmodell ist ein **Hidden-Markov-Modell (HMM)** mit gaußschen Verteilungen; ein Mischverteilungsmodell (Gaussian Mixture) ohne Zeitdynamik dient als Gegencheck.

### 5.1 Modell

- **Merkmale (monatlich):** die Rohindikatoren aus 4.1 ohne Handgewichtung, ergänzt um Marktmerkmale: Korrelation Aktien/Anleihen (rollierend 12 Monate), realisierte Aktienvolatilität, Veränderung der Realrendite, High-Yield-Spread. Alle Merkmale standardisiert, mit derselben Veröffentlichungsverzögerung wie in Methode A.
- **Anzahl Zustände:** Standard 4, damit der Vergleich zu den Quadranten möglich ist. Zusätzlich 3 bis 6 testen und per BIC berichten.
- **Benennung:** Zustände werden über ihre mittleren Wachstums- und Inflationswerte den Quadranten zugeordnet (Ungarische Methode). Ein Zustand, der zu keinem Quadranten passt (z. B. „Finanzstress“), behält einen eigenen Namen.
- **Point-in-Time-Pflicht:** Neuer Fit mit expandierendem Fenster (mindestens jährlich, monatlich gefiltert). Es werden **nur gefilterte Wahrscheinlichkeiten** verwendet. Geglättete Wahrscheinlichkeiten oder der Viterbi-Pfad nutzen künftige Daten und sind im Backtest verboten.
- **Stabilität:** mehrere Startwerte, bestes Modell nach Log-Likelihood; Zustandsbezeichnungen über Refits hinweg konsistent halten (Label Switching).
- **Ausgabe:** Wahrscheinlichkeit je Zustand, Übergangsmatrix, erwartete Verweildauer je Zustand.

### 5.2 Getrennte Darstellung

Das Dashboard zeigt beide Methoden nebeneinander: je ein Zeitstrahl mit farbigen Regime-Bändern, die aktuellen Wahrscheinlichkeiten beider Methoden, eine Übereinstimmungsquote über die gesamte Historie und eine Kreuztabelle (wie oft A Regime X sieht, während B Regime Y sieht).

### 5.3 Warum die Ergebnisse abweichen

Abweichungen sind erwartbar und werden **jeden Monat automatisch begründet**. Typische Ursachen:

| Ursache | Wirkung |
| --- | --- |
| Informationsmenge | B nutzt Marktmerkmale, die Wendepunkte vorwegnehmen; A stützt sich stärker auf verzögert veröffentlichte Realwirtschaftsdaten |
| Trägheit | Die Übergangsmatrix des HMM bevorzugt das bisherige Regime; B reagiert daher an Wendepunkten später oder übergeht kurze Ausreißer |
| Grenzbereiche | A schneidet hart an Schwellenwerten; B berücksichtigt Korrelationen zwischen Merkmalen und kann denselben Punkt anders einordnen |
| Regime-Definition | HMM-Zustände sind statistische Cluster, keine Dalio-Quadranten; ein Zustand kann z. B. Finanzstress statt Stagflation abbilden |
| Strukturbrüche | B lernt aus der Vergangenheit; Phasen ohne historisches Vorbild (z. B. Inflation nach 2021) werden zunächst falsch eingeordnet |

**Technik der Begründung:** Für A werden die Beiträge jedes Indikators zum Score ausgewiesen. Für B wird bei diagonaler Kovarianz die Log-Likelihood-Differenz zwischen den beiden wahrscheinlichsten Zuständen pro Merkmal zerlegt. Daraus erzeugt eine Textvorlage einen Satz wie: „B sieht Stagflation vor allem wegen steigender Realrenditen und positiver Aktien-Anleihen-Korrelation; A sieht noch Reflation, weil die Industrieproduktion weiter anzieht.“

### 5.4 Zusammenführung

Die Methoden werden nicht gemittelt, sondern bestimmen gemeinsam die **Überzeugung**: Je ähnlicher die beiden Wahrscheinlichkeitsvektoren, desto größer die zulässigen aktiven Abweichungen. Gemessen wird das über 1 minus die Totalvariationsdistanz der Vektoren. Bei Uneinigkeit bleibt die Allokation näher an der Basis.

## 6. Langfristiger Schuldenzyklus als Overlay

Das Overlay verschiebt die **strategische Basisallokation selbst**, nicht nur die zyklischen Abweichungen. Es wirkt damit stärker und dauerhafter als die Regime aus Abschnitt 4 und 5. Standardeinstellung ist „hohe Wirkung“, entsprechend Dalios aktueller Einschätzung.

### 6.1 Dalios aktuelle Einschätzung (Stand Nov. 2026)

- In einem [Gastbeitrag im März 2026](https://fortune.com/2026/03/14/ray-dalio-big-cycle-debt-crisis-political-disorder-world-order/) verortet Dalio die Welt in Stufe 5 seines sechsstufigen „Big Cycle“, also unmittelbar vor Stufe 6, dem Zusammenbruch der bestehenden Ordnung.
- Im [August 2026](https://www.businesstoday.in/world/story/us-debt-hits-danger-zone-ray-dalio-explains-why-a-big-debt-cycle-could-trigger-a-crisis-550775-2026-08-23) beschreibt er die Spätphase des US-Schuldenzyklus über steigende Langfristzinsen, Währungsschwäche und sinkende Nachfrage nach langlaufenden Staatsanleihen. Er beziffert das US-Defizit auf rund 2 Bio. USD (Einnahmen ca. 5,5 Bio., Ausgaben ca. 7,5 Bio.).
- Als Positionierung nennt er laut [Berichten](https://www.livewiremarkets.com/wires/why-ray-dalio-is-backing-gold-and-bitcoin-to-hedge-against-the-debt-crisis): breit über Länder mit soliden Bilanzen streuen, Schuldtitel untergewichten, [10 bis 15 % Gold](https://fortune.com/2026/01/09/ray-dalio-on-38-trillion-national-debt-grandchildren-will-be-paying-devalued-dollar-currency/?rand=8593) und inflationsindexierte Staatsanleihen.

Das sind Dalios Einschätzungen, keine gesicherten Fakten. Das Tool bildet sie daher zweifach ab: messbar über Indikatoren (6.2) und als manuell gepflegte Einschätzung mit Datum und Quelle (6.3).

### 6.2 Messbarer Schuldenstress-Score je Land

Für USA, Eurozone (Deutschland, Frankreich, Italien einzeln), Japan, Vereinigtes Königreich, China wird ein Score von 0 bis 100 gebildet:

| Indikator | Quelle |
| --- | --- |
| Staatsverschuldung in % des BIP und deren Trend | BIS, IMF |
| Zinsausgaben in % der Staatseinnahmen | OECD, CBO (USA) |
| Realzins minus nominales Wachstum (r − g) | FRED, EZB, OECD |
| Primärdefizit in % des BIP | IMF, OECD |
| Laufzeitprämie langer Staatsanleihen | ACM-Modell der NY Fed (USA), eigene Schätzung sonst |
| Zentralbankbilanz in % des BIP | FRED, EZB |
| Gold-Anteil an den Währungsreserven der Zentralbanken weltweit | World Gold Council |
| Handelsgewichteter Wechselkurs (Trend) | BIS |
| Private Kredit/BIP-Lücke und Schuldendienstquote | BIS |

Der Score wird in eine an Dalio angelehnte Phase übersetzt: **gesund**, **Aufbau**, **Übertreibung**, **Spätphase (Finanzierungsstress)**, **Entschuldung / Monetarisierung**, **Neuordnung**. Schwellenwerte werden mit der Jordà-Schularick-Taylor-Datenbank an historischen Episoden kalibriert (z. B. USA und UK 1940er bis 1970er, Japan ab 1990).

### 6.3 Manuelle Einschätzung

In `config/debt_cycle.yaml` wird je Land eine Phase mit Datum, Quelle und Begründung gepflegt (Voreinstellung USA: Spätphase, entsprechend Dalio 2026). Weichen gemessener Score und manuelle Einschätzung um mehr als eine Phase ab, zeigt das Dashboard eine Warnung. Ein Feld „Gegenposition“ hält fest, was gegen die Einschätzung spricht, etwa der Status des US-Dollar als Reservewährung oder Produktivitätsgewinne durch KI.

### 6.4 Wirkung auf die Allokation

Die Basisgewichte werden um einen Overlay-Vektor verschoben, skaliert mit der Phase des jeweiligen Landes (λ von 0 bis 1). Bei Spätphase der USA und λ = 1:

| Assetklasse | Verschiebung gegenüber Basis |
| --- | --- |
| Gold | auf 10–15 % Gesamtgewicht anheben |
| Inflationsindexierte Anleihen | +5 Prozentpunkte |
| Infrastruktur | +2 bis +3 Prozentpunkte (inflationsgekoppelte Erlöse) |
| US-Treasuries lang | −5 bis −8 Prozentpunkte |
| Aktien USA | zugunsten von Ländern mit niedrigem Schuldenstress umschichten |
| Ungesichertes USD-Exposure | Obergrenze senken |

Die Zahlen sind Startwerte in der Konfiguration. Das Dashboard zeigt jede Empfehlung zusätzlich **ohne Overlay**, damit dessen Einfluss sichtbar bleibt. Weil es nur wenige historische Episoden gibt, lässt sich das Overlay nicht statistisch belastbar backtesten; es wird mit den jährlichen JST-Daten nur qualitativ plausibilisiert.

## 7. Empfehlungs-Engine

Alle drei Empfehlungsformen entstehen aus derselben Kette: Regime-Wahrscheinlichkeiten → erwartete Regime-Renditen je Klasse → Ausgabeform. Jede Form wird für Methode A, Methode B und die Zusammenführung berechnet, jeweils mit und ohne Schuldenzyklus-Overlay.

### 7.1 Basisallokation

- **Festgelegt: Risikoparität.** Je Quadrant ein „Umfeldkorb“ aus den Klassen, die dort profitieren. Die vier Körbe tragen gleich viel Risiko, innerhalb der Körbe gilt gleicher Risikobeitrag (Equal Risk Contribution). Ohne Hebel ergibt das einen hohen Anleiheanteil; das ist bewusst und wird dokumentiert.
- **Bitcoin** nimmt an der Risikoparität teil, ist aber bei 3 % gedeckelt.
- **Risikoschätzung:** Kovarianz aus 5 Jahren Monatsdaten, exponentiell gewichtet, mit Ledoit-Wolf-Schrumpfung. Berechnet in der Basiswährung, damit das Währungsrisiko in die Risikobeiträge eingeht.

### 7.2 Erwartete Renditen: Black-Litterman mit Regime-Sichten

Ausgangspunkt (Prior) sind die impliziten Renditen der Risikoparitäts-Basis, gewonnen durch Reverse Optimization. Die Regime-Einschätzung geht als Black-Litterman-Sicht ein: Für jede Klasse ist das die Summe über die Quadranten aus Wahrscheinlichkeit des Quadranten mal Regime-Rendite der Klasse. Die Regime-Renditen mischen die ökonomische Annahme (4.4) mit dem historischen Mittel je Regime, geschrumpft nach James-Stein.

Die Unsicherheit der Sichten (Omega) sinkt mit der Überzeugung aus 5.4: Stimmen A und B überein, wirken die Sichten stärker. Das Schuldenzyklus-Overlay geht als eigene Sicht ein, damit sein Beitrag getrennt sichtbar bleibt.

### 7.3 Die drei Ausgabeformen

| Form | Inhalt | Regeln |
| --- | --- | --- |
| (i) Regime-Ampel | je Klasse grün / gelb / rot plus kurze Begründung | Grenzen bei ±0,5 Standardabweichungen der erwarteten Überrendite; zusätzlich Pfeil für Veränderung zum Vormonat |
| (ii) Über-/Untergewichtung | aktive Abweichung je Klasse in Prozentpunkten zur Basis | Abweichung = Skalierung × Überzeugung (5.4) × Signal; je Klasse begrenzt (Standard ±10 Pp., kleine Klassen ±5 Pp.); Summe null |
| (iii) Zielgewichte | konkrete Gewichte je Klasse und, falls ein aktuelles Portfolio als CSV hinterlegt ist, Umschichtungsliste | Optimierung (cvxpy) mit Black-Litterman-Renditen, stabilisiert durch Michaud-Resampling (500 Simulationen): maximiere erwartete Überrendite, Tracking Error zur Basis höchstens 3 % p. a., nur Long, Obergrenzen je Klasse, Umschlag höchstens 20 % pro Quartal, No-Trade-Band 2 Pp. |

### 7.4 Nachvollziehbarkeit

Jede Empfehlung zerlegt sich in drei Beiträge: zyklisches Regime, Schuldenzyklus-Overlay und bindende Restriktionen. Das Dashboard und der Monatsbericht zeigen diese Zerlegung als Wasserfall je Klasse.

### 7.5 Methoden aus „Quant Portfolio Management mit Python“

Der Kurs von Prof. Dr. Thomas Mählmann (KU Eichstätt-Ingolstadt) deckt die Portfoliokonstruktion ab, also genau die Stufe nach der Regime-Erkennung. Regime-Modelle und Backtesting behandelt er nicht; sie bleiben eigene Bausteine. Das frei verfügbare [Begleitbuch](https://quantseminar.de/book/) ist die methodische Referenz für die Umsetzung.

| Kursmodul | Verwendung im Tool |
| --- | --- |
| Mean-Variance mit Restriktionen (cvxpy) | Grundlage der Zielgewichte (iii) |
| Relative Optimierung, Tracking Error, Active Share | Tracking-Error-Budget gegenüber der Risikoparitäts-Basis; Active Share als Kennzahl im Dashboard |
| Schätzrisiko | Stabilitätskennzahl: Wie stark ändern sich die Zielgewichte bei kleinen Änderungen der Inputs? |
| Schrumpfung (Ledoit-Wolf, James-Stein) | Kovarianz (Ledoit-Wolf) und Regime-Renditen (James-Stein) |
| Black-Litterman | Regime- und Overlay-Sichten auf die Risikoparitäts-Basis (7.2) |
| Resampling (Michaud) | Zielgewichte als Mittel über simulierte Input-Sätze; Bandbreite je Klasse im Dashboard |
| Risikoparität und Minimum-Varianz | Basisallokation (ERC); Minimum-Varianz als Vergleich im Backtest, ausgewertet je Marktphase |
| Index-Tracking | Proxy-Qualität: Tracking Error zwischen Proxy-ETF und Referenzindex |

Falls du die kommentierten Kurs-Notebooks noch hast, lege sie unter `notebooks/reference/` ab. Der Agent prüft seine Implementierung dann gegen sie.

### 7.6 Währungseffekte und Basiswährung

- **Basiswährung umstellbar** in `config/currency.yaml` (Standard EUR; vorgesehen USD, CHF, GBP). Renditen, Risiken und Gewichte werden in der gewählten Basis neu berechnet.
- **Absicherung:** Aktien, Sachwerte und Bitcoin ungesichert, Anleihen gesichert. Die Absicherungsrendite ergibt sich aus der Kurzfristzinsdifferenz zwischen Basis- und Fremdwährung.
- **Zerlegung je Klasse:** Rendite in Basiswährung = (1 + Lokalrendite) × (1 + Währungsrendite) − 1. Lokal- und Währungsbeitrag werden getrennt gezeigt, je Monat und kumuliert.
- **Währungsexposure:** Anteil je Währung (USD, EUR, JPY, GBP, Schwellenländerkorb) nach Durchschau auf die Regionen der Proxies.
- **Risikobeitrag der Währungen:** Anteil des Portfoliorisikos, der auf Wechselkurse entfällt.
- **Szenario:** Wirkung einer Auf- oder Abwertung der Basiswährung um ±10 % gegenüber dem USD auf Portfolio und Empfehlung.
- **In der Empfehlung:** Ausgewiesen wird, welcher Teil einer Über- oder Untergewichtung auf Währungseffekte zurückgeht, etwa beim Overlay-Signal gegen den USD.

## 8. Backtesting

Der Backtest muss zeigen, ob die Regime-Steuerung nach Kosten einen Mehrwert gegenüber der statischen Basis liefert, und zwar so, dass ein kritischer Prüfer das Ergebnis akzeptiert.

### 8.1 Ablauf

- Monatlicher Walk-Forward: Entscheidung am Monatsende t nur mit Daten, die zu t veröffentlicht waren; Umsetzung zum Schlusskurs des ersten Handelstags von t+1.
- Umschichtung quartalsweise mit No-Trade-Band; Transaktionskosten je Klasse in Basispunkten (Standard: Aktien-ETFs 10, Staatsanleihen 5, Unternehmens-, High-Yield- und Schwellenländeranleihen 20, Rohstoffe 15, Gold 10, REITs und Infrastruktur 15).
- Zeiträume: (a) nur echte Proxies (ab ca. 2008, alle Klassen vorhanden), (b) lange Historie mit Backfill (ab 1973, im Bericht als synthetisch markiert), (c) Stressphasen einzeln: 1970er-Stagflation, 2000–2002, 2008, 2020, 2022.

### 8.2 Vergleichsstrategien

1. Statische Basisallokation.
2. Methode A.
3. Methode B.
4. Zusammenführung A + B.
5. Zusammenführung plus Schuldenzyklus-Overlay.
6. 60/40 aus EUR-Sicht (MSCI-World-Proxy / EUR-Staatsanleihen).
7. Gleichgewichtung aller Klassen sowie Minimum-Varianz-Portfolio.
8. **Obergrenze:** Regime mit perfekter Voraussicht (geglättete, rückblickende Regime). Zeigt, wie viel Wert die Regime-Erkennung höchstens liefern könnte; klar als nicht umsetzbar markiert.
9. **Placebo:** 1.000 zufällige Regimefolgen mit gleicher Verweildauer. Ergibt einen p-Wert dafür, ob die Ergebnisse besser als Zufall sind.

### 8.3 Kennzahlen

Rendite p. a., Volatilität, Sharpe- und Sortino-Ratio (gegen €STR), maximaler Drawdown, Calmar-Ratio, schlechteste 12 Monate, CVaR 5 %, Tracking Error und Information Ratio gegenüber der Basis, Umschlag, Kosten, Trefferquote der Regime-Signale, Rendite je Regime, Active Share, Stabilität der Gewichte, Währungsbeitrag zur Rendite.

### 8.4 Schutz gegen Überanpassung

- Parameter werden **vor** dem ersten Backtest in der Konfiguration festgeschrieben und versioniert.
- Trennung in Entwicklungszeitraum (bis 2007) und Prüfzeitraum (ab 2008); der Prüfzeitraum wird erst am Ende ausgewertet.
- Sensitivitätsanalyse: zentrale Parameter jeweils ±50 % variieren, Ergebnisse als Heatmap.
- Deflated Sharpe Ratio (Bailey / López de Prado) unter Angabe der Anzahl getesteter Varianten.
- Automatischer Look-ahead-Test: Werden alle Daten nach t verändert, darf sich keine Entscheidung bis t ändern.

### 8.5 Ausgabe

Bericht als HTML (optional PDF) und eigener Reiter im Dashboard, mit Kurven, Drawdown-Grafik, Regime-Bändern unter der Wertentwicklung und Kennzahlentabelle.

## 9. Architektur und Tech-Stack

Ein Python-Paket `navigator` enthält die gesamte Logik; Kommandozeile und Dashboard sind nur dünne Oberflächen darüber. So liefern beide garantiert dieselben Zahlen.

**Abbildung: Architektur. Eine Datenpipeline speist drei Analysen und eine Empfehlungs-Engine.**

```text
Makrodaten (FRED/ALFRED, EZB, Eurostat, OECD, BIS)   Marktdaten (yfinance, Tiingo, Coin Metrics, Emittenten-NAVs)   Historische Daten (French, JST, AQR, World Gold Council, Nareit)
                                   |
Datenschicht: Cache (Parquet), Validierung und Kreuzprüfung, Point-in-Time-Speicher,
              EUR-Umrechnung und Absicherung, synthetische Anleihen, Backfill-Verkettung
                                   |
Merkmale: Wachstum, Inflation, Kreditzyklus, Schuldenstress, jeweils mit Veröffentlichungsverzögerung
          |                               |                               |
Methode A: regelbasiert        Methode B: statistisch          Schuldenzyklus-Overlay
(Quadranten aus Scores,        (Hidden-Markov-Modell,          (Stress-Score je Land plus
kurzfristiger Schuldenzyklus)  nur gefilterte Signale)         manuelle Einschätzung)
          |                               |                               |
Vergleich und Überzeugung (Abweichungen werden begründet;                 |
Übereinstimmung skaliert die Tilts)                                       |
                                   |                                      |
Empfehlungs-Engine: Basisallokation (Risikoparität) + Regime-Tilts + Overlay
                    Ausgabe: Ampel, Über-/Untergewichtung, Zielgewichte (cvxpy)
          |                               |                               |
Backtest (Walk-forward,        Kommandozeile, Bericht          Dashboard (Streamlit, sechs
Placebo, Robustheitstests)     (navigator monthly,             Reiter, Szenarien per
                               HTML-Monatsbericht)             Seitenleiste)
```

Kommandozeile, Bericht und Dashboard greifen auf dieselbe Engine zu; der Backtest ruft sie Monat für Monat mit dem jeweiligen Datenstand auf.

### 9.1 Tech-Stack

| Bereich | Wahl |
| --- | --- |
| Sprache und Umgebung | Python 3.12, Paketverwaltung mit uv, `pyproject.toml` |
| Daten | pandas, numpy, pyarrow (Parquet-Cache), optional DuckDB für Abfragen |
| Datenquellen | yfinance, fredapi, sdmx1 (EZB, Eurostat, OECD, BIS), coinmetrics-api-client, requests und BeautifulSoup (Tiingo, Emittenten-NAVs, private Infrastruktur, statische Downloads); EODHD, SIPA und MSCI als deaktivierte Provider |
| Modelle | statsmodels, scikit-learn, hmmlearn, scipy |
| Optimierung | cvxpy |
| Konfiguration | YAML, validiert mit pydantic |
| Kommandozeile | typer |
| Dashboard | Streamlit mit Plotly |
| Berichte | Jinja2-HTML-Vorlagen mit Plotly, optional PDF |
| Qualität | pytest, ruff, mypy, pre-commit |

### 9.2 Ordnerstruktur

```text
allocation-navigator/
  pyproject.toml
  README.md
  CLAUDE.md                 # Arbeitsregeln für den Coding-Agenten
  config/
    universe.yaml           # Assetklassen, Proxies, Backfill, Währung, Absicherung
    sources.yaml            # Datenquellen, API-Keys per Umgebungsvariable
    indicators.yaml         # Indikatoren, Veröffentlichungsverzögerung, Transformation
    regime_map.yaml         # Erwartungsvektoren je Klasse und Quadrant
    base.yaml               # Basisallokation (Risikoparität), Basiswährung in currency.yaml
    debt_cycle.yaml         # manuelle Einschätzung, Overlay-Vektoren
    backtest.yaml           # Zeiträume, Kosten, Restriktionen
  src/navigator/
    data/
      providers/            # yfinance, fred, ecb, eurostat, oecd, bis, tiingo, coinmetrics, issuer_nav, private_infra, static; eodhd, sipa, msci (deaktiviert)
      cache.py  validate.py  pit.py  fx.py  synthetic.py
    features/               # growth, inflation, credit_cycle, debt_cycle
    regimes/                # rules (A), hmm (B), gmm, compare, explain
    allocation/             # base, expected, signals, optimizer, overlay
    backtest/               # engine, costs, metrics, placebo, robustness
    reporting/              # report, templates/
    cli.py
  dashboard/
    app.py
    pages/
  data/                     # raw/, processed/, snapshots/ (nicht in Git)
  tests/
  notebooks/
```

### 9.3 Kommandozeile

- `navigator data update` und `navigator data validate`
- `navigator regime run --method a|b|both --asof 2026-10-31`
- `navigator recommend --asof 2026-10-31 --overlay on|off`
- `navigator backtest --config config/backtest.yaml`
- `navigator report --month 2026-10`
- `navigator dashboard`

### 9.4 Dashboard-Reiter

1. **Übersicht:** aktuelles Regime nach A und B, Überzeugung, Schuldenzyklus-Phase, Ampel.
2. **Regime:** Zeitsträhle beider Methoden, Wahrscheinlichkeiten, Kreuztabelle, automatische Begründung der Abweichungen.
3. **Schuldenzyklus:** Score je Land, gemessene vs. manuelle Phase, Gegenposition.
4. **Empfehlungen:** alle drei Formen, mit und ohne Overlay, Zerlegung als Wasserfall, Währungsbeiträge und Wechsel der Basiswährung.
5. **Backtest:** Vergleichsstrategien, Kennzahlen, Sensitivitäten, Placebo-Test.
6. **Daten und Qualität:** Aktualität je Reihe, Proxy- und Backfill-Kennzeichen, Abweichungen zwischen Quellen, Bestätigung neu importierter Werte privater Infrastruktur.

Seitenleiste mit Einstellungen: Methode, Overlay-Stärke, Wahl der Basisallokation, Restriktionen. Änderungen dort werden nicht in die Konfiguration zurückgeschrieben, sondern als Szenario gekennzeichnet.

### 9.5 Synthetische Anleiherenditen

Wo keine Fondshistorie existiert, entsteht die Monatsrendite aus Renditereihen: Kupon-Ertrag (Vormonatsrendite / 12) minus Duration mal Renditeveränderung plus halbe Konvexität mal quadrierte Renditeveränderung. Duration und Konvexität werden aus der Laufzeit abgeleitet. Die synthetische Reihe wird in überlappenden Zeiträumen gegen echte Fondsrenditen geprüft (Korrelation über 0,95 als Akzeptanzkriterium).

## 10. Umsetzungsplan

Neun Meilensteine, strikt nacheinander. Nach M1, M3 und M6 hält der Agent an und legt die Ergebnisse zur Prüfung vor, bevor er weitermacht.

| # | Meilenstein | Inhalt | Abnahmekriterium |
| --- | --- | --- | --- |
| M0 | Grundgerüst | Repository, uv, `pyproject.toml`, CLAUDE.md, Konfigurationsschemas, pre-commit, CI | `pytest` grün, `navigator --help` funktioniert |
| M1 | Datenschicht | Provider inkl. Bitcoin, Emittenten-NAVs und privater Infrastruktur (EODHD, SIPA, MSCI als deaktivierte Platzhalter), Cache, Validierung, Point-in-Time-Speicher, Währungsumrechnung, synthetische Anleihen, Backfill-Verkettung | Alle 18 Klassen als monatliche Total-Return-Reihen in jeder unterstützten Basiswährung; Validierungsbericht; Look-ahead-Test der Makrodaten grün. **Prüfpunkt** |
| M2 | Methode A | Wachstums- und Inflationsscore, Quadranten, kurzfristiger Schuldenzyklus | Bekannte Episoden plausibel eingeordnet (z. B. 1974 Stagflation, 2008 deflationäre Rezession, 2021/22 steigende Inflation); Einordnung dokumentiert |
| M3 | Methode B und Vergleich | HMM, GMM-Gegencheck, Zuordnung, Vergleich, automatische Begründung | Nur gefilterte Wahrscheinlichkeiten; stabile Zustandsnamen; Begründungstext für jeden Monat. **Prüfpunkt** |
| M4 | Schuldenzyklus-Overlay | Score je Land, manuelle Einschätzung, Overlay-Vektoren | Kalibrierung mit JST-Daten dokumentiert; Wirkung mit und ohne Overlay sichtbar |
| M5 | Empfehlungs-Engine | Risikoparitäts-Basis, Black-Litterman, Resampling, drei Ausgabeformen, Währungszerlegung | Alle Restriktionen eingehalten; Zerlegung summiert sich exakt zur Empfehlung |
| M6 | Backtest | Engine, Kosten, neun Vergleichsstrategien, Kennzahlen, Robustheit, Placebo | Look-ahead-Test grün; HTML-Bericht erzeugt; Prüfzeitraum ab 2008 separat ausgewiesen. **Prüfpunkt** |
| M7 | Dashboard | Sechs Reiter, Einstellungen, Szenarien | Zahlen identisch mit der Kommandozeile (automatischer Test) |
| M8 | Monatsbetrieb | `navigator monthly` führt Update, Regime, Empfehlung und Bericht aus; README mit Bedienung | Ein vollständiger Lauf ohne manuelle Eingriffe |

## 11. Arbeitsanweisung für Fable 5.2

So übergibst du das Projekt:

1. Dieses Dokument als Markdown exportieren und im neuen Repository als `docs/SPEC.md` ablegen.
2. API-Keys besorgen (FRED, Tiingo, optional EODHD) und in eine lokale `.env`-Datei schreiben, nie ins Repository.
3. Fable 5.2 in Claude Code im Repository starten und den folgenden Start-Prompt verwenden.

```markdown
Du bist Senior Quant Developer für ein strategisches Asset-Allocation-Tool.
Die vollständige Spezifikation steht in docs/SPEC.md. Lies sie komplett,
bevor du Code schreibst.

Arbeitsweise:
- Lege zuerst CLAUDE.md mit den Arbeitsregeln unten an und halte dich daran.
- Arbeite die Meilensteine M0 bis M8 aus Abschnitt 10 strikt nacheinander ab.
  Ein Meilenstein ist erst fertig, wenn sein Abnahmekriterium erfüllt und
  getestet ist.
- Halte nach M1, M3 und M6 an: Fasse Ergebnisse, Abweichungen von der Spezifikation
  und offene Fragen zusammen und warte auf meine Freigabe.
- Führe docs/decisions.md: jede Designentscheidung mit Datum, Alternativen, Grund.

Arbeitsregeln (in CLAUDE.md übernehmen):
- Point-in-Time-Korrektheit hat Vorrang vor allem anderen. Jede Funktion, die
  Daten für ein Datum t liefert, bekommt einen Test, der beweist, dass keine
  Daten nach t einfließen.
- Im Backtest nur gefilterte HMM-Wahrscheinlichkeiten, nie geglättete oder Viterbi.
- Keine Parameter auf die Historie optimieren. Alle Parameter stehen in config/
  und werden vor dem Backtest festgeschrieben.
- Ticker, Startdaten und Datenreihen-IDs aus der Spezifikation vor Verwendung
  prüfen; Abweichungen in docs/decisions.md festhalten.
- Alle Logik im Paket src/navigator; CLI und Dashboard rufen nur das Paket auf.
- Schrumpfung, Black-Litterman, Resampling und Risikoparität folgen dem Buch
  https://quantseminar.de/book/ (Kapitel 4 bis 7). Liegen Kurs-Notebooks unter
  notebooks/reference/, Ergebnisse dagegen prüfen.
- Kein kostenpflichtiger Datendienst. EODHD, SIPA und MSCI nur als deaktivierte
  Provider anlegen.
- Typannotationen, Docstrings auf Deutsch, ruff und mypy ohne Fehler.
- Keine Secrets im Code oder Repository; Keys nur über Umgebungsvariablen.
- Wenn eine Datenquelle ausfällt: Fallback laut Spezifikation, Warnung ins Log,
  nie stillschweigend falsche oder veraltete Daten verwenden.

Beginne mit M0 und zeige mir danach den Plan für M1.
```

Tipp: Pro Meilenstein eine neue Sitzung beginnen und auf `docs/SPEC.md`, `CLAUDE.md` und `docs/decisions.md` verweisen. So bleibt der Kontext schlank.

## 12. Risiken, Grenzen und offene Punkte

**Risiken und Grenzen**

- **Datenstabilität:** yfinance kann ohne Vorwarnung brechen, wie nach der [Umgestaltung von Yahoo Finance im Februar 2025](https://deepcharts.substack.com/p/why-did-the-yfinance-python-library). Gegenmittel: Cache, Zweitquelle, Fallback.
- **Kurze Historien:** Infrastruktur, inflationsindexierte Anleihen, Trendfolge und Bitcoin haben echte Daten erst ab 2000 bis 2019 (Bitcoin ab etwa 2010). Lizenzierte Indizes privater Infrastruktur sind ohne Abo nur über veröffentlichte Eckwerte und börsennotierte Näherungen zugänglich. Ergebnisse vor Proxy-Start beruhen auf Backfill und sind entsprechend vorsichtig zu lesen.
- **Wenige Regimewechsel:** 50 Jahre Monatsdaten enthalten nur etwa 15 bis 25 Regimewechsel. Statistische Aussagen über Regime bleiben unsicher, auch bei sauberem Backtest.
- **Verzögerung an Wendepunkten:** Beide Methoden erkennen Regime erst im Nachhinein; das Tool ist kein Prognoseinstrument für Wendepunkte.
- **Ermessen im Overlay:** Die Schuldenzyklus-Einschätzung beruht teilweise auf Dalios Urteil und lässt sich kaum testen. Daher ist sie immer abschaltbar und getrennt ausgewiesen.
- **Lizenzen:** Yahoo-Daten und die JST-Datenbank nur für nicht-kommerzielle, private Nutzung. Eine Weitergabe der Ergebnisse an Dritte wäre lizenz- und aufsichtsrechtlich gesondert zu prüfen.
- Das Tool liefert Analysen für die eigene Entscheidungsfindung, keine Anlageberatung.

**Entscheidungen vom 16.11.2026**

- Basisallokation: Risikoparität über vier Umfeldkörbe (7.1).
- Kein Daten-Abo; Schnittstellen für EODHD, SIPA und MSCI vorbereitet, aber deaktiviert (3).
- Aktien ungesichert; Währungseinflüsse getrennt ausgewiesen; Basiswährung umstellbar, Standard EUR (7.6).
- Bitcoin als optionale Klasse aktiviert, Obergrenze 3 % (2).
- Private Infrastruktur: automatischer Import in drei Stufen (2).
- Methoden aus „Quant Portfolio Management mit Python“ integriert (7.5).

**Quellen**

- Dalio, Big Cycle Stufe 5: [Fortune, 14.03.2026](https://fortune.com/2026/03/14/ray-dalio-big-cycle-debt-crisis-political-disorder-world-order/)
- Dalio, US-Schuldenzyklus: [Business Today, 23.08.2026](https://www.businesstoday.in/world/story/us-debt-hits-danger-zone-ray-dalio-explains-why-a-big-debt-cycle-could-trigger-a-crisis-550775-2026-08-23)
- Dalio, Gold und TIPS: [Fortune, 09.01.2026](https://fortune.com/2026/01/09/ray-dalio-on-38-trillion-national-debt-grandchildren-will-be-paying-devalued-dollar-currency/?rand=8593); [Livewire Markets](https://www.livewiremarkets.com/wires/why-ray-dalio-is-backing-gold-and-bitcoin-to-hedge-against-the-debt-crisis)
- Infrastruktur-Indizes: [FTSE Core Infrastructure](https://www.lseg.com/content/dam/ftse-russell/en_us/documents/other/ftse-global-core-infrastructure-indexes.pdf); [iShares Global Infrastructure UCITS ETF](https://www.ishares.com/uk/professional/en/products/251809/ishares-global-infrastructure-ucits-etf); [SIPA infra300](https://www.pei.group/?p=4919); [MSCI Private Infrastructure](https://www.msci.com/data-and-analytics/private-asset-solutions/global-private-infrastructure-asset-index-q1-2026-results)
- Daten: [FRED Real-Time Periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html); [BIS Credit Gaps](https://data.bis.org/topics/CREDIT_GAPS); [Tiingo API](https://api.tiingo.com/documentation); [EODHD Preise](https://eodhd.com/pricing); [Stooq API-Key](https://github.com/pydata/pandas-datareader/issues/1012); [JST Macrohistory](https://www.nber.org/research/data/jorda-schularick-taylor-macrohistory)

- Methoden: [Quant Portfolio Management mit Python](https://www.quantseminar.de/) und [Begleitbuch](https://quantseminar.de/book/)
- Bitcoin-Daten: [Coin Metrics Community Data](https://docs.coinmetrics.io/packages/coin-metrics-community-data)
- Private Infrastruktur: [infra300 auf AWS Data Exchange (eingestellt)](https://aws.amazon.com/marketplace/pp/prodview-4fa6qefiwyoiy); [infra300-Meldungen bei Infrastructure Investor](https://www.infrastructureinvestor.com/infra300-posts-best-monthly-return-in-2026/)
