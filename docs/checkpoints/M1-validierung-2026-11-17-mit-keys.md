# Validierungsbericht Datenschicht (echte Daten mit API-Keys, 17.11.2026)

> Erzeugt vom GitHub-Workflow „Live-Daten (manuell)", Lauf 44073656403, mit FRED- und Tiingo-Key.

Erstellt: 2026-11-17T11:26:48+00:00 · Konfigurations-Hash: `8d39e8c03ee0`

**1 Fehler, 24 Warnungen, 7 Hinweise.**

- Assetklassen mit Monatsreihe je Basiswährung: EUR: 18/18, USD: 18/18, CHF: 18/18, GBP: 18/18

## Befunde

| Stufe | Bereich | Prüfung | Befund |
| --- | --- | --- | --- |
| Fehler | indicator.ea_unrate | Abruf | keine Daten im Cache |
| Warnung | asset.bitcoin.btc_reference_rate [coinmetrics] | Zweitquelle | coinmetrics gegen yfinance: 31 Monate über 0.5% (größte: -3.24% im 2017-05) |
| Warnung | asset.bond_corp_ig.vwesx [yfinance] | Startdatum | Daten ab 1980-01, erwartet 1973-07 (+78 Monate) |
| Warnung | asset.bond_corp_ig.vwesx [yfinance] | Zweitquelle | yfinance gegen tiingo: 130 Monate über 0.5% (größte: +3.39% im 1982-01) |
| Warnung | asset.bond_em.premx [yfinance] | Zweitquelle | yfinance gegen tiingo: 13 Monate über 0.5% (größte: +1.29% im 1998-01) |
| Warnung | asset.bond_eur_short.ishares_eur_govt_1_3 [yfinance] | Dividenden | keine Ausschüttung im bereinigten Kurs erkennbar in: 2022, 2023; Zweitquelle prüfen |
| Warnung | asset.bond_high_yield.vwehx [yfinance] | Zweitquelle | yfinance gegen tiingo: 132 Monate über 0.5% (größte: +2.75% im 1983-01) |
| Warnung | asset.bond_inflation_linked.vipsx [yfinance] | Zweitquelle | yfinance gegen tiingo: 6 Monate über 0.5% (größte: -1.65% im 2002-12) |
| Warnung | asset.bond_us_long.vustx [yfinance] | Zweitquelle | yfinance gegen tiingo: 49 Monate über 0.5% (größte: +6.05% im 1992-12) |
| Warnung | asset.commodities.pcrix [yfinance] | Zweitquelle | yfinance gegen tiingo: 51 Monate über 0.5% (größte: +14.67% im 2008-12) |
| Warnung | asset.equity_em.veiex [yfinance] | Zweitquelle | yfinance gegen tiingo: 12 Monate über 0.5% (größte: -4.81% im 2008-12) |
| Warnung | asset.equity_europe.vgk [yfinance] | Zweitquelle | yfinance gegen tiingo: 1 Monate über 0.5% (größte: +0.66% im 2020-12) |
| Warnung | asset.equity_japan.ewj [yfinance] | Zweitquelle | yfinance gegen tiingo: 10 Monate über 0.5% (größte: +7.68% im 1996-09) |
| Warnung | asset.reits.vgsix [yfinance] | Zweitquelle | yfinance gegen tiingo: 5 Monate über 0.5% (größte: +2.05% im 1996-12) |
| Warnung | bond_corp_ig/synth_baa_daily | Synthetik | Korrelation 0.93 zum Fonds vwesx liegt unter 0,95 |
| Warnung | bond_corp_ig/synth_baa_monthly | Synthetik | Korrelation 0.64 zum Fonds vwesx liegt unter 0,95 |
| Warnung | bond_eur_long/synth_bund_10y | Synthetik | Korrelation 0.86 zum Fonds ishares_core_eur_govt liegt unter 0,95 |
| Warnung | bond_eur_short/synth_bund_2y | Backfill | passt schlecht zu ishares_eur_govt_1_3 (Korrelation 0.12); unkalibriert verkettet |
| Warnung | bond_eur_short/synth_bund_2y | Synthetik | Korrelation 0.47 zum Fonds ishares_eur_govt_1_3 liegt unter 0,95 |
| Warnung | bond_us_long/synth_ust_10y | Synthetik | Korrelation 0.94 zum Fonds vustx liegt unter 0,95 |
| Warnung | fx.EUR.dem_per_usd [bundesbank] | Lücken | Lücken über 10 Tage: 1 (größte: 18 Tage bis 1973-03-19) |
| Warnung | fx.JPY.per_usd [fred] | Lücken | Lücken über 10 Tage: 1 (größte: 18 Tage bis 1971-08-31) |
| Warnung | gold/gold_london_fix | Backfill | passt schlecht zu gld (Korrelation 0.53); unkalibriert verkettet |
| Warnung | indicator.ea_core_hicp [ecb] | Aktualität | letzte Beobachtung 2025-12-31 ist 321 Tage alt (Grenze 200) |
| Warnung | reference.three_i_infra [yfinance] | Sprünge | 1 Sprünge über 25% (größter: +27.4% am 2020-03-24) |
| Hinweis | asset.bond_eur_long.ishares_core_eur_govt [yfinance] | Zweitquelle | keine Zweitquelle im Cache |
| Hinweis | asset.bond_eur_short.ishares_eur_govt_1_3 [yfinance] | Startdatum | Daten ab 2008-12, erwartet 2006-06 (+30 Monate) |
| Hinweis | asset.bond_eur_short.ishares_eur_govt_1_3 [yfinance] | Zweitquelle | keine Zweitquelle im Cache |
| Hinweis | asset.bond_high_yield.vwehx [yfinance] | Startdatum | Daten ab 1980-01, erwartet 1978-12 (+13 Monate) |
| Hinweis | asset.equity_us.vfinx [yfinance] | Startdatum | Daten ab 1980-01, erwartet 1976-08 (+41 Monate) |
| Hinweis | asset.infrastructure.ishares_global_infra_ucits [yfinance] | Startdatum | Daten ab 2008-12, erwartet 2006-10 (+26 Monate) |
| Hinweis | asset.infrastructure.ishares_global_infra_ucits [yfinance] | Zweitquelle | keine Zweitquelle im Cache |

## Universum in EUR

| asset | start | end | months | proxy_start | original | proxy | synthetisch | backfill | return_pa | vol_pa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| equity_us | 1948-07 | 2026-10 | 940 | 1980-02 | 0.403 | 0.597 | 0.000 | 0.403 | 0.101 | 0.165 |
| equity_europe | 1975-01 | 2026-10 | 622 | 2005-04 | 0.494 | 0.506 | 0.000 | 0.584 | 0.098 | 0.160 |
| equity_japan | 1975-01 | 2026-10 | 622 | 1996-04 | 0.410 | 0.590 | 0.000 | 0.410 | 0.071 | 0.198 |
| equity_em | 1989-07 | 2026-10 | 448 | 1994-06 | 0.132 | 0.868 | 0.000 | 0.132 | 0.080 | 0.209 |
| bond_eur_short | 1972-10 | 2026-10 | 649 | 2009-01 | 0.000 | 0.330 | 0.670 | 0.670 | 0.043 | 0.021 |
| bond_eur_long | 1972-10 | 2026-10 | 649 | 2009-05 | 0.000 | 0.324 | 0.676 | 0.676 | 0.043 | 0.048 |
| bond_us_long | 1962-02 | 2026-10 | 777 | 1986-06 | 0.000 | 0.624 | 0.376 | 0.376 | 0.052 | 0.100 |
| bond_inflation_linked | 2000-07 | 2026-10 | 316 | 2000-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.033 | 0.057 |
| bond_corp_ig | 1960-01 | 2026-10 | 802 | 1980-02 | 0.000 | 0.700 | 0.300 | 0.300 | 0.057 | 0.080 |
| bond_high_yield | 1980-02 | 2026-10 | 561 | 1980-02 | 0.000 | 1.000 | 0.000 | 0.000 | 0.068 | 0.074 |
| bond_em | 1995-01 | 2026-10 | 382 | 1995-01 | 0.000 | 1.000 | 0.000 | 0.000 | 0.070 | 0.125 |
| gold | 1960-02 | 2026-10 | 801 | 2004-12 | 0.672 | 0.328 | 0.000 | 0.672 | 0.057 | 0.168 |
| commodities | 1954-07 | 2026-10 | 868 | 2002-08 | 0.000 | 0.335 | 0.665 | 0.665 | 0.071 | 0.161 |
| reits | 1972-01 | 2026-10 | 658 | 1996-06 | 0.445 | 0.555 | 0.000 | 0.445 | 0.094 | 0.189 |
| infrastructure | 1948-07 | 2026-10 | 940 | 2009-01 | 0.000 | 0.240 | 0.760 | 0.772 | 0.071 | 0.127 |
| trend | 1985-01 | 2026-10 | 502 | 2019-06 | 0.000 | 0.177 | 0.823 | 0.823 | 0.118 | 0.129 |
| bitcoin | 2010-08 | 2026-10 | 195 | 2010-08 | 1.000 | 0.000 | 0.000 | 0.000 | 1.382 | 1.747 |
| cash | 1960-01 | 2026-10 | 802 | 1960-01 | 1.000 | 0.000 | 0.000 | 0.000 | 0.042 | 0.009 |

## Kalibrierung an den Nähten (Basiswährung)

| asset | older | newer | seam | months | alpha | beta | correlation | applied |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| equity_us | french_us_market | vfinx | 1980-02-29 | 36 | -0.000 | 0.992 | 0.981 | True |
| equity_europe | ezu | vgk | 2005-04-30 | 36 | -0.000 | 0.941 | 0.977 | True |
| equity_europe | french_europe | ezu | 2000-08-31 | 36 | -0.000 | 1.058 | 0.985 | True |
| equity_europe | french_intl_europe | french_europe | 1990-07-31 | 36 | -0.000 | 1.014 | 0.992 | True |
| equity_japan | french_japan | ewj | 1996-04-30 | 36 | 0.000 | 1.020 | 0.951 | True |
| equity_japan | french_intl_japan | french_japan | 1990-07-31 | 36 | -0.000 | 1.019 | 0.995 | True |
| equity_em | french_emerging | veiex | 1994-06-30 | 36 | 0.000 | 0.998 | 0.977 | True |
| bond_eur_short | synth_bund_2y | ishares_eur_govt_1_3 | 2009-01-31 | 36 | 0.000 | 1.000 | 0.122 | False |
| bond_eur_long | synth_bund_10y | ishares_core_eur_govt | 2009-05-31 | 36 | -0.000 | 0.747 | 0.711 | True |
| bond_us_long | synth_ust_30y | vustx | 1986-06-30 | 36 | 0.000 | 0.870 | 0.969 | True |
| bond_us_long | synth_ust_10y | synth_ust_30y | 1977-03-31 | 36 | -0.000 | 0.977 | 0.968 | True |
| bond_corp_ig | synth_baa_monthly | vwesx | 1980-02-29 | 36 | 0.000 | 0.839 | 0.631 | True |
| gold | gold_london_fix | gld | 2004-12-31 | 36 | 0.000 | 1.000 | 0.533 | False |
| commodities | aqr_commodities | pcrix | 2002-08-31 | 36 | 0.000 | 1.038 | 0.830 | True |
| reits | nareit_all_equity | vgsix | 1996-06-30 | 36 | 0.000 | 1.006 | 0.996 | True |
| infrastructure | igf | ishares_global_infra_ucits | 2009-01-31 | 36 | -0.000 | 0.832 | 0.710 | True |
| infrastructure | french_utilities_telecom | igf | 2008-01-31 | 36 | -0.000 | 0.845 | 0.794 | True |
| trend | aqr_tsmom | dbmf | 2019-06-30 | 36 | 0.000 | 0.756 | 0.704 | True |

## Synthetische Reihen gegen Fonds

| asset | synthetisch | Fonds | Monate | Korrelation | Tracking Error p.a. | akzeptiert |
| --- | --- | --- | --- | --- | --- | --- |
| bond_eur_short | synth_bund_2y | ishares_eur_govt_1_3 | 214 | 0.469 | 0.014 | nein |
| bond_eur_long | synth_bund_10y | ishares_core_eur_govt | 210 | 0.856 | 0.035 | nein |
| bond_us_long | synth_ust_30y | vustx | 485 | 0.975 | 0.029 | ja |
| bond_us_long | synth_ust_10y | vustx | 485 | 0.939 | 0.044 | nein |
| bond_inflation_linked | synth_tips_10y | vipsx | 284 | 0.957 | 0.024 | ja |
| bond_corp_ig | synth_baa_daily | vwesx | 489 | 0.929 | 0.034 | nein |
| bond_corp_ig | synth_baa_monthly | vwesx | 561 | 0.636 | 0.074 | nein |

## Universum in USD

| asset | start | end | months | proxy_start | original | proxy | synthetisch | backfill | return_pa | vol_pa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| equity_us | 1926-07 | 2026-10 | 1204 | 1980-02 | 0.534 | 0.466 | 0.000 | 0.534 | 0.099 | 0.180 |
| equity_europe | 1975-01 | 2026-10 | 622 | 2005-04 | 0.494 | 0.506 | 0.000 | 0.584 | 0.104 | 0.178 |
| equity_japan | 1975-01 | 2026-10 | 622 | 1996-04 | 0.410 | 0.590 | 0.000 | 0.410 | 0.078 | 0.203 |
| equity_em | 1989-07 | 2026-10 | 448 | 1994-06 | 0.132 | 0.868 | 0.000 | 0.132 | 0.083 | 0.212 |
| bond_eur_short | 1972-10 | 2026-10 | 649 | 2009-01 | 0.000 | 0.330 | 0.670 | 0.670 | 0.053 | 0.022 |
| bond_eur_long | 1972-10 | 2026-10 | 649 | 2009-05 | 0.000 | 0.324 | 0.676 | 0.676 | 0.051 | 0.047 |
| bond_us_long | 1962-02 | 2026-10 | 777 | 1986-06 | 0.000 | 0.624 | 0.376 | 0.376 | 0.059 | 0.099 |
| bond_inflation_linked | 2000-07 | 2026-10 | 316 | 2000-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.039 | 0.057 |
| bond_corp_ig | 1919-02 | 2026-10 | 1293 | 1980-02 | 0.000 | 0.434 | 0.566 | 0.566 | 0.058 | 0.075 |
| bond_high_yield | 1980-02 | 2026-10 | 561 | 1980-02 | 0.000 | 1.000 | 0.000 | 0.000 | 0.077 | 0.074 |
| bond_em | 1995-01 | 2026-10 | 382 | 1995-01 | 0.000 | 1.000 | 0.000 | 0.000 | 0.078 | 0.125 |
| gold | 1960-02 | 2026-10 | 801 | 2004-12 | 0.672 | 0.328 | 0.000 | 0.672 | 0.065 | 0.151 |
| commodities | 1954-07 | 2026-10 | 868 | 2002-08 | 0.000 | 0.335 | 0.665 | 0.665 | 0.094 | 0.166 |
| reits | 1972-01 | 2026-10 | 658 | 1996-06 | 0.445 | 0.555 | 0.000 | 0.445 | 0.107 | 0.173 |
| infrastructure | 1926-07 | 2026-10 | 1204 | 2009-01 | 0.000 | 0.188 | 0.812 | 0.822 | 0.080 | 0.150 |
| trend | 1985-01 | 2026-10 | 502 | 2019-06 | 0.000 | 0.177 | 0.823 | 0.823 | 0.166 | 0.121 |
| bitcoin | 2010-08 | 2026-10 | 195 | 2010-08 | 1.000 | 0.000 | 0.000 | 0.000 | 1.360 | 1.766 |
| cash | 1954-07 | 2026-10 | 868 | 1954-07 | 1.000 | 0.000 | 0.000 | 0.000 | 0.047 | 0.010 |

## Universum in CHF

| asset | start | end | months | proxy_start | original | proxy | synthetisch | backfill | return_pa | vol_pa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| equity_us | 1971-02 | 2026-10 | 669 | 1980-02 | 0.161 | 0.839 | 0.000 | 0.161 | 0.073 | 0.187 |
| equity_europe | 1975-01 | 2026-10 | 622 | 2005-04 | 0.494 | 0.506 | 0.000 | 0.584 | 0.081 | 0.173 |
| equity_japan | 1975-01 | 2026-10 | 622 | 1996-04 | 0.410 | 0.590 | 0.000 | 0.410 | 0.054 | 0.203 |
| equity_em | 1989-07 | 2026-10 | 448 | 1994-06 | 0.132 | 0.868 | 0.000 | 0.132 | 0.063 | 0.220 |
| bond_eur_short | 1999-07 | 2026-10 | 328 | 2009-01 | 0.000 | 0.652 | 0.348 | 0.348 | 0.007 | 0.015 |
| bond_eur_long | 1999-07 | 2026-10 | 328 | 2009-05 | 0.000 | 0.640 | 0.360 | 0.360 | 0.013 | 0.047 |
| bond_us_long | 1999-07 | 2026-10 | 328 | 1999-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.024 | 0.116 |
| bond_inflation_linked | 2000-07 | 2026-10 | 316 | 2000-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.023 | 0.057 |
| bond_corp_ig | 1999-07 | 2026-10 | 328 | 1999-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.034 | 0.101 |
| bond_high_yield | 1999-07 | 2026-10 | 328 | 1999-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.037 | 0.075 |
| bond_em | 1999-07 | 2026-10 | 328 | 1999-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.056 | 0.100 |
| gold | 1971-02 | 2026-10 | 669 | 2004-12 | 0.607 | 0.393 | 0.000 | 0.607 | 0.053 | 0.186 |
| commodities | 1971-02 | 2026-10 | 669 | 2002-08 | 0.000 | 0.435 | 0.565 | 0.565 | 0.059 | 0.182 |
| reits | 1972-01 | 2026-10 | 658 | 1996-06 | 0.445 | 0.555 | 0.000 | 0.445 | 0.076 | 0.195 |
| infrastructure | 1971-02 | 2026-10 | 669 | 2009-01 | 0.000 | 0.338 | 0.662 | 0.680 | 0.047 | 0.147 |
| trend | 1985-01 | 2026-10 | 502 | 2019-06 | 0.000 | 0.177 | 0.823 | 0.823 | 0.105 | 0.128 |
| bitcoin | 2010-08 | 2026-10 | 195 | 2010-08 | 1.000 | 0.000 | 0.000 | 0.000 | 1.326 | 1.744 |
| cash | 1999-07 | 2026-10 | 328 | 1999-07 | 1.000 | 0.000 | 0.000 | 0.000 | 0.004 | 0.003 |

## Universum in GBP

| asset | start | end | months | proxy_start | original | proxy | synthetisch | backfill | return_pa | vol_pa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| equity_us | 1971-02 | 2026-10 | 669 | 1980-02 | 0.161 | 0.839 | 0.000 | 0.161 | 0.117 | 0.169 |
| equity_europe | 1975-01 | 2026-10 | 622 | 2005-04 | 0.494 | 0.506 | 0.000 | 0.584 | 0.116 | 0.156 |
| equity_japan | 1975-01 | 2026-10 | 622 | 1996-04 | 0.410 | 0.590 | 0.000 | 0.410 | 0.090 | 0.198 |
| equity_em | 1989-07 | 2026-10 | 448 | 1994-06 | 0.132 | 0.868 | 0.000 | 0.132 | 0.087 | 0.209 |
| bond_eur_short | 1972-10 | 2026-10 | 649 | 2009-01 | 0.000 | 0.330 | 0.670 | 0.670 | 0.068 | 0.023 |
| bond_eur_long | 1972-10 | 2026-10 | 649 | 2009-05 | 0.000 | 0.324 | 0.676 | 0.676 | 0.062 | 0.048 |
| bond_us_long | 1962-02 | 2026-10 | 777 | 1986-06 | 0.000 | 0.624 | 0.376 | 0.376 | 0.074 | 0.100 |
| bond_inflation_linked | 2000-07 | 2026-10 | 316 | 2000-07 | 0.000 | 1.000 | 0.000 | 0.000 | 0.044 | 0.057 |
| bond_corp_ig | 1957-01 | 2026-10 | 838 | 1980-02 | 0.000 | 0.669 | 0.331 | 0.331 | 0.075 | 0.079 |
| bond_high_yield | 1980-02 | 2026-10 | 561 | 1980-02 | 0.000 | 1.000 | 0.000 | 0.000 | 0.090 | 0.074 |
| bond_em | 1995-01 | 2026-10 | 382 | 1995-01 | 0.000 | 1.000 | 0.000 | 0.000 | 0.083 | 0.125 |
| gold | 1971-02 | 2026-10 | 669 | 2004-12 | 0.607 | 0.393 | 0.000 | 0.607 | 0.096 | 0.191 |
| commodities | 1971-02 | 2026-10 | 669 | 2002-08 | 0.000 | 0.435 | 0.565 | 0.565 | 0.106 | 0.180 |
| reits | 1972-01 | 2026-10 | 658 | 1996-06 | 0.445 | 0.555 | 0.000 | 0.445 | 0.120 | 0.185 |
| infrastructure | 1971-02 | 2026-10 | 669 | 2009-01 | 0.000 | 0.338 | 0.662 | 0.680 | 0.087 | 0.140 |
| trend | 1985-01 | 2026-10 | 502 | 2019-06 | 0.000 | 0.177 | 0.823 | 0.823 | 0.126 | 0.129 |
| bitcoin | 2010-08 | 2026-10 | 195 | 2010-08 | 1.000 | 0.000 | 0.000 | 0.000 | 1.382 | 1.734 |
| cash | 1957-01 | 2026-10 | 838 | 1957-01 | 1.000 | 0.000 | 0.000 | 0.000 | 0.063 | 0.012 |

## Point-in-Time-Speicher (Makroreihen)

| Indikator | Beobachtungen | von | bis | Revisionen | Anteil Verzögerungsregel | echte Vintages | zuletzt bekannt ab |
| --- | --- | --- | --- | --- | --- | --- | --- |
| us_cli | 862 | 1955-01-31 | 2026-10-31 | 0 | 100% | nein | 2026-12-31 |
| us_indpro | 1293 | 1919-01-01 | 2026-09-01 | 37449 | 0% | ja | 2026-10-16 |
| us_unrate | 945 | 1948-01-01 | 2026-10-01 | 1254 | 7% | ja | 2026-11-06 |
| us_curve_10y3m | 11220 | 1982-01-04 | 2026-11-16 | 0 | 100% | nein | 2026-11-16 |
| us_credit_spread | 10217 | 1986-01-02 | 2026-11-13 | 0 | 100% | nein | 2026-11-13 |
| us_hy_spread_recent | 784 | 2023-11-17 | 2026-11-13 | 0 | 100% | nein | 2026-11-13 |
| us_real_retail | 416 | 1992-01-01 | 2026-09-01 | 6444 | 2% | ja | 2026-10-15 |
| us_core_cpi | 837 | 1957-01-01 | 2026-10-01 | 1424 | 21% | ja | 2026-11-10 |
| us_breakeven_5y5y | 5972 | 2003-01-02 | 2026-11-16 | 0 | 100% | nein | 2026-11-16 |
| us_wages | 754 | 1964-01-01 | 2026-10-01 | 3239 | 11% | ja | 2026-11-06 |
| us_ppi | 1366 | 1913-01-01 | 2026-10-01 | 473 | 33% | ja | 2026-11-13 |
| us_cpi_nsa | 1365 | 1913-01-01 | 2026-10-01 | 0 | 100% | nein | 2026-11-30 |
| ea_cli | 790 | 1961-01-31 | 2026-10-31 | 0 | 100% | nein | 2026-12-31 |
| ea_indpro | 429 | 1991-01-31 | 2026-09-30 | 0 | 100% | nein | 2026-11-30 |
| ea_unrate | 0 |  |  | 0 |  |  |  |
| ea_euribor_3m | 394 | 1994-01-31 | 2026-10-31 | 0 | 100% | nein | 2026-10-31 |
| ea_retail | 321 | 2000-01-31 | 2026-09-30 | 0 | 100% | nein | 2026-11-30 |
| ea_core_hicp | 313 | 1996-01-31 | 2025-12-31 | 0 | 100% | nein | 2026-01-31 |
| ea_ppi | 321 | 2000-01-31 | 2026-09-30 | 0 | 100% | nein | 2026-11-30 |
| us_credit_gap | 274 | 1957-12-31 | 2026-03-31 | 0 | 100% | nein | 2026-09-30 |
| us_dsr_private | 109 | 1999-03-31 | 2026-03-31 | 0 | 100% | nein | 2026-09-30 |
| us_policy_rate | 26434 | 1954-07-01 | 2026-11-13 | 0 | 100% | nein | 2026-11-13 |

## Quellen

| Quelle | Priorität | eingeschaltet | kostenpflichtig | nutzbar | Hinweis | Lizenz |
| --- | --- | --- | --- | --- | --- | --- |
| eodhd | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | EODHD (Abo erforderlich) |
| msci | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | MSCI Private Asset Indexes, Lizenz erforderlich |
| sipa | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | SIPA / Scientific Infra (infra300), Lizenz erforderlich |
| bundesbank | 8 | ja | nein | ja |  | Deutsche Bundesbank, freie Nutzung mit Quellenangabe |
| coinmetrics | 10 | ja | nein | ja |  | Coin Metrics Community Data, Creative Commons (CC BY-NC 4.0) |
| ecb | 10 | ja | nein | ja |  | ECB Data Portal, freie Nutzung mit Quellenangabe |
| fred | 10 | ja | nein | ja |  | FRED Terms of Use |
| bis | 20 | ja | nein | ja |  | BIS, freie Nutzung mit Quellenangabe |
| eurostat | 20 | ja | nein | ja |  | Eurostat, freie Weiterverwendung mit Quellenangabe |
| oecd | 20 | ja | nein | ja |  | OECD Terms and Conditions |
| yfinance | 20 | ja | nein | ja |  | Yahoo Finance, inoffizielle Schnittstelle, nur private Nutzung |
| tiingo | 30 | ja | nein | ja |  | Tiingo, Gratis-Tarif nur für private Nutzung |
| issuer_nav | 40 | ja | nein | ja |  | Emittenten-Websites (iShares), Nutzungsbedingungen je Emittent |
| private_infra | 50 | ja | nein | ja |  | Veröffentlichte Eckwerte Dritter; Nutzungsbedingungen der Seiten beachten |
| static | 60 | ja | nein | ja |  | Je Datensatz (French, AQR, Nareit, JST, Shiller); JST und AQR nur nicht-kommerziell |

## Rohreihen je Quelle

| Reihe | Quelle | Symbol | vorhanden | von | bis | Werte | erwartet ab | abgerufen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| asset.equity_us.vfinx | tiingo | VFINX | ja | 1976-08-31 | 2026-11-16 | 12578 | 1976-08 | 2026-11-17T11:24 |
| asset.equity_us.vfinx | yfinance | VFINX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1976-08 | 2026-11-17T11:24 |
| asset.equity_us.vfinx.fallback | tiingo | SPY | ja | 1993-01-29 | 2026-11-16 | 8508 |  | 2026-11-17T11:24 |
| asset.equity_us.vfinx.fallback | yfinance | SPY | ja | 1993-01-29 | 2026-11-16 | 8508 |  | 2026-11-17T11:24 |
| asset.equity_us.french_us_market | static | french_us_factors:Mkt-RF+RF | ja | 1926-07-31 | 2026-09-30 | 1203 | 1926-07 | 2026-11-17T11:24 |
| asset.equity_europe.vgk | tiingo | VGK | ja | 2005-03-10 | 2026-11-16 | 5457 | 2005-03 | 2026-11-17T11:24 |
| asset.equity_europe.vgk | yfinance | VGK | ja | 2005-03-10 | 2026-11-16 | 5457 | 2005-03 | 2026-11-17T11:24 |
| asset.equity_europe.ezu | tiingo | EZU | ja | 2001-01-02 | 2026-11-16 | 6507 | 2000-07 | 2026-11-17T11:24 |
| asset.equity_europe.ezu | yfinance | EZU | ja | 2000-07-31 | 2026-11-16 | 6614 | 2000-07 | 2026-11-17T11:24 |
| asset.equity_europe.french_europe | static | french_europe:Mkt-RF+RF | ja | 1990-07-31 | 2026-09-30 | 435 | 1990-07 | 2026-11-17T11:24 |
| asset.equity_europe.french_intl_europe | static | french_intl_europe:Mkt | ja | 1975-01-31 | 2025-12-31 | 612 | 1975-01 | 2026-11-17T11:24 |
| asset.equity_japan.ewj | tiingo | EWJ | ja | 1996-04-01 | 2026-11-16 | 7707 | 1996-03 | 2026-11-17T11:24 |
| asset.equity_japan.ewj | yfinance | EWJ | ja | 1996-03-18 | 2026-11-16 | 7717 | 1996-03 | 2026-11-17T11:24 |
| asset.equity_japan.french_japan | static | french_japan:Mkt-RF+RF | ja | 1990-07-31 | 2026-09-30 | 435 | 1990-07 | 2026-11-17T11:24 |
| asset.equity_japan.french_intl_japan | static | french_intl_japan:Mkt | ja | 1975-01-31 | 2025-12-31 | 612 | 1975-01 | 2026-11-17T11:24 |
| asset.equity_em.veiex | tiingo | VEIEX | ja | 1994-05-04 | 2026-11-16 | 8190 | 1994-05 | 2026-11-17T11:24 |
| asset.equity_em.veiex | yfinance | VEIEX | ja | 1994-05-04 | 2026-11-16 | 8190 | 1994-05 | 2026-11-17T11:24 |
| asset.equity_em.veiex.fallback | tiingo | EEM | ja | 2003-04-11 | 2026-11-16 | 5938 |  | 2026-11-17T11:24 |
| asset.equity_em.veiex.fallback | yfinance | EEM | ja | 2003-04-14 | 2026-11-16 | 5937 |  | 2026-11-17T11:24 |
| asset.equity_em.french_emerging | static | french_emerging:Mkt-RF+RF | ja | 1989-07-31 | 2026-09-30 | 447 | 1989-07 | 2026-11-17T11:24 |
| asset.bond_eur_short.ishares_eur_govt_1_3 | issuer_nav | ishares_eur_govt_1_3 | NEIN |  |  | 0 | 2006-06 |  |
| asset.bond_eur_short.ishares_eur_govt_1_3 | yfinance | IBCA.DE | ja | 2008-12-23 | 2026-11-17 | 4543 | 2006-06 | 2026-11-17T11:24 |
| asset.bond_eur_short.synth_bund_2y.yield | bundesbank | BBSIS/M.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A | ja | 1972-09-30 | 2026-10-31 | 650 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.ishares_core_eur_govt | issuer_nav | ishares_core_eur_govt | NEIN |  |  | 0 | 2009-04 |  |
| asset.bond_eur_long.ishares_core_eur_govt | yfinance | EUNH.DE | ja | 2009-04-17 | 2026-11-17 | 4469 | 2009-04 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | bundesbank | BBSIS/M.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A | ja | 1972-09-30 | 2026-10-31 | 650 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | fred | IRLTLT01DEM156N | ja | 1956-05-01 | 2026-10-01 | 846 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/DEU.M.IRLT.PA._Z._Z._Z._Z.N | ja | 1956-05-31 | 2026-10-31 | 846 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx | tiingo | VUSTX | ja | 1986-05-19 | 2026-11-16 | 10203 | 1986-05 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx | yfinance | VUSTX | ja | 1986-05-19 | 2026-11-16 | 10203 | 1986-05 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx.fallback | tiingo | TLT | ja | 2002-07-26 | 2026-11-16 | 6117 |  | 2026-11-17T11:24 |
| asset.bond_us_long.vustx.fallback | yfinance | TLT | ja | 2002-07-30 | 2026-11-16 | 6115 |  | 2026-11-17T11:24 |
| asset.bond_us_long.synth_ust_30y.yield | fred | DGS30 | ja | 1977-02-15 | 2026-11-13 | 12432 | 1977-02 | 2026-11-17T11:24 |
| asset.bond_us_long.synth_ust_10y.yield | fred | DGS10 | ja | 1962-01-02 | 2026-11-13 | 16202 | 1962-01 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx | tiingo | VIPSX | ja | 2000-06-29 | 2026-11-16 | 6635 | 2000-06 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx | yfinance | VIPSX | ja | 2000-06-29 | 2026-11-16 | 6635 | 2000-06 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx.fallback | tiingo | TIP | ja | 2003-12-05 | 2026-11-16 | 5773 |  | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx.fallback | yfinance | TIP | ja | 2003-12-05 | 2026-11-16 | 5773 |  | 2026-11-17T11:24 |
| asset.bond_inflation_linked.synth_tips_10y.yield | fred | DFII10 | ja | 2003-01-02 | 2026-11-13 | 5971 | 2003-01 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.synth_tips_10y.cpi | fred | CPIAUCNS | ja | 1913-01-01 | 2026-10-01 | 1365 |  | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx | tiingo | VWESX | ja | 1980-01-02 | 2026-11-16 | 11816 | 1973-07 | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx | yfinance | VWESX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1973-07 | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx.fallback | tiingo | LQD | ja | 2002-07-26 | 2026-11-16 | 6117 |  | 2026-11-17T11:25 |
| asset.bond_corp_ig.vwesx.fallback | yfinance | LQD | ja | 2002-07-30 | 2026-11-16 | 6115 |  | 2026-11-17T11:24 |
| asset.bond_corp_ig.synth_baa_daily.yield | fred | DBAA | ja | 1986-01-02 | 2026-11-13 | 10253 | 1986-01 | 2026-11-17T11:25 |
| asset.bond_corp_ig.synth_baa_monthly.yield | fred | BAA | ja | 1919-01-01 | 2026-10-01 | 1294 | 1919-01 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx | tiingo | VWEHX | ja | 1980-01-02 | 2026-11-16 | 11816 | 1978-12 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx | yfinance | VWEHX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1978-12 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx.fallback | tiingo | HYG | ja | 2007-04-11 | 2026-11-16 | 4933 |  | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx.fallback | yfinance | HYG | ja | 2007-04-11 | 2026-11-16 | 4933 |  | 2026-11-17T11:25 |
| asset.bond_em.premx | tiingo | PREMX | ja | 1995-01-03 | 2026-11-16 | 8022 | 1994-12 | 2026-11-17T11:25 |
| asset.bond_em.premx | yfinance | PREMX | ja | 1994-12-30 | 2026-11-16 | 8023 | 1994-12 | 2026-11-17T11:25 |
| asset.bond_em.premx.fallback | tiingo | EMB | ja | 2007-12-19 | 2026-11-16 | 4757 |  | 2026-11-17T11:25 |
| asset.bond_em.premx.fallback | yfinance | EMB | ja | 2007-12-19 | 2026-11-16 | 4757 |  | 2026-11-17T11:25 |
| asset.gold.gld | tiingo | GLD | ja | 2004-11-18 | 2026-11-16 | 5533 | 2004-11 | 2026-11-17T11:25 |
| asset.gold.gld | yfinance | GLD | ja | 2004-11-18 | 2026-11-16 | 5533 | 2004-11 | 2026-11-17T11:25 |
| asset.gold.gld.fallback | yfinance | GC=F | ja | 2000-08-30 | 2026-11-17 | 6580 |  | 2026-11-17T11:25 |
| asset.gold.gold_london_fix | static | worldbank_pinksheet:Gold | ja | 1960-01-31 | 2024-12-31 | 780 | 1960-01 | 2026-11-17T11:25 |
| asset.commodities.pcrix | tiingo | PCRIX | ja | 2002-07-01 | 2026-11-16 | 6134 | 2002-06 | 2026-11-17T11:25 |
| asset.commodities.pcrix | yfinance | PCRIX | ja | 2002-07-01 | 2026-11-16 | 6135 | 2002-06 | 2026-11-17T11:25 |
| asset.commodities.pcrix.fallback | tiingo | DBC | ja | 2006-02-03 | 2026-11-16 | 5229 |  | 2026-11-17T11:25 |
| asset.commodities.pcrix.fallback | yfinance | DBC | ja | 2006-02-06 | 2026-11-16 | 5228 |  | 2026-11-17T11:25 |
| asset.commodities.aqr_commodities | static | aqr_commodities:Excess return of equal-weight commodities portfolio | ja | 1877-02-28 | 2025-05-31 | 1780 | 1877-02 | 2026-11-17T11:25 |
| asset.reits.vgsix | tiingo | VGSIX | ja | 1996-05-13 | 2026-11-16 | 7678 | 1996-05 | 2026-11-17T11:25 |
| asset.reits.vgsix | yfinance | VGSIX | ja | 1996-05-13 | 2026-11-16 | 7678 | 1996-05 | 2026-11-17T11:25 |
| asset.reits.vgsix.fallback | tiingo | VNQ | ja | 2004-09-29 | 2026-11-16 | 5569 |  | 2026-11-17T11:25 |
| asset.reits.vgsix.fallback | yfinance | VNQ | ja | 2004-09-29 | 2026-11-16 | 5569 |  | 2026-11-17T11:25 |
| asset.reits.nareit_all_equity | static | nareit:all_equity | ja | 1972-01-31 | 2026-10-31 | 658 | 1972-01 | 2026-11-17T11:25 |
| asset.infrastructure.ishares_global_infra_ucits | issuer_nav | ishares_global_infra | NEIN |  |  | 0 | 2006-10 |  |
| asset.infrastructure.ishares_global_infra_ucits | yfinance | IQQI.DE | ja | 2008-12-23 | 2026-11-17 | 4535 | 2006-10 | 2026-11-17T11:25 |
| asset.infrastructure.igf | tiingo | IGF | ja | 2007-12-12 | 2026-11-16 | 4762 | 2007-12 | 2026-11-17T11:25 |
| asset.infrastructure.igf | yfinance | IGF | ja | 2007-12-12 | 2026-11-16 | 4762 | 2007-12 | 2026-11-17T11:25 |
| asset.infrastructure.french_utilities_telecom.c0 | static | french_ind12:Utils | ja | 1926-07-31 | 2026-09-30 | 1203 |  | 2026-11-17T11:25 |
| asset.infrastructure.french_utilities_telecom.c1 | static | french_ind12:Telcm | ja | 1926-07-31 | 2026-09-30 | 1203 |  | 2026-11-17T11:25 |
| asset.trend.dbmf | tiingo | DBMF | ja | 2019-05-08 | 2026-11-16 | 1893 | 2019-05 | 2026-11-17T11:25 |
| asset.trend.dbmf | yfinance | DBMF | ja | 2019-05-08 | 2026-11-16 | 1893 | 2019-05 | 2026-11-17T11:25 |
| asset.trend.dbmf.fallback | tiingo | KMLM | ja | 2020-12-02 | 2026-11-16 | 1496 |  | 2026-11-17T11:25 |
| asset.trend.dbmf.fallback | yfinance | KMLM | ja | 2020-12-02 | 2026-11-16 | 1496 |  | 2026-11-17T11:25 |
| asset.trend.aqr_tsmom | static | aqr_tsmom:TSMOM | ja | 1985-01-31 | 2026-05-31 | 497 | 1985-01 | 2026-11-17T11:25 |
| asset.bitcoin.btc_reference_rate | coinmetrics | btc | ja | 2010-07-18 | 2026-11-16 | 5966 | 2010-07 | 2026-11-17T11:25 |
| asset.bitcoin.btc_reference_rate | yfinance | BTC-USD | ja | 2014-09-17 | 2026-11-17 | 4445 | 2010-07 | 2026-11-17T11:25 |
| reference.hicl | yfinance | HICL.L | ja | 2006-03-28 | 2026-11-17 | 5216 |  | 2026-11-17T11:25 |
| reference.inpp | yfinance | INPP.L | ja | 2006-11-08 | 2026-11-17 | 5060 |  | 2026-11-17T11:25 |
| reference.three_i_infra | yfinance | 3IN.L | ja | 2007-03-08 | 2026-11-17 | 4977 |  | 2026-11-17T11:25 |
| reference.msci_world | tiingo | URTH | ja | 2012-01-12 | 2026-11-16 | 3733 |  | 2026-11-17T11:25 |
| reference.msci_world | yfinance | URTH | ja | 2012-01-12 | 2026-11-16 | 3733 |  | 2026-11-17T11:25 |
| fx.USD.per_eur | ecb | EXR/D.USD.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.GBP.per_eur | ecb | EXR/D.GBP.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.CHF.per_eur | ecb | EXR/D.CHF.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.JPY.per_eur | ecb | EXR/D.JPY.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.EUR.usd_per_unit | fred | DEXUSEU | ja | 1999-01-04 | 2026-11-13 | 6988 |  | 2026-11-17T11:25 |
| fx.EUR.dem_per_usd | bundesbank | BBEX3/D.USD.DEM.AA.AC.000 | ja | 1948-06-21 | 1998-12-30 | 13050 |  | 2026-11-17T11:25 |
| fx.EUR.dem_per_usd | fred | EXGEUS | ja | 1971-01-01 | 2001-12-01 | 372 |  | 2026-11-17T11:25 |
| fx.GBP.usd_per_unit | fred | DEXUSUK | ja | 1971-01-04 | 2026-11-13 | 14009 |  | 2026-11-17T11:25 |
| fx.CHF.per_usd | fred | DEXSZUS | ja | 1971-01-04 | 2026-11-13 | 14009 |  | 2026-11-17T11:25 |
| fx.JPY.per_usd | fred | DEXJPUS | ja | 1971-01-04 | 2026-11-13 | 14003 |  | 2026-11-17T11:25 |
| rate.EUR.estr | ecb | EST/B.EU000A2X2A25.WT | ja | 2019-10-01 | 2026-11-16 | 1826 |  | 2026-11-17T11:26 |
| rate.EUR.eonia | ecb | EON/D.EONIA_TO.RATE | ja | 1999-01-04 | 2021-12-31 | 5890 |  | 2026-11-17T11:26 |
| rate.EUR.de_3m_interbank | fred | IR3TIB01DEM156N | ja | 1960-01-01 | 2026-10-01 | 802 |  | 2026-11-17T11:26 |
| rate.EUR.de_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/DEU.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1960-01-31 | 2026-10-31 | 802 |  | 2026-11-17T11:26 |
| rate.USD.fed_funds | fred | DFF | ja | 1954-07-01 | 2026-11-13 | 26434 |  | 2026-11-17T11:26 |
| rate.GBP.sonia | fred | IUDSOIA | ja | 1997-01-02 | 2026-11-13 | 7548 |  | 2026-11-17T11:26 |
| rate.GBP.gb_3m_interbank | fred | IR3TIB01GBM156N | ja | 1957-01-01 | 2026-01-01 | 829 |  | 2026-11-17T11:26 |
| rate.GBP.gb_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/GBR.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1986-01-31 | 2026-02-28 | 482 |  | 2026-11-17T11:26 |
| rate.CHF.ch_3m_interbank | fred | IR3TIB01CHM156N | ja | 1999-07-01 | 2026-10-01 | 328 |  | 2026-11-17T11:26 |
| rate.CHF.ch_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/CHE.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1999-07-31 | 2026-10-31 | 328 |  | 2026-11-17T11:26 |
| rate.JPY.jp_3m_interbank | fred | IR3TIB01JPM156N | ja | 2002-04-01 | 2026-09-01 | 294 |  | 2026-11-17T11:26 |
| rate.JPY.jp_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/JPN.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 2002-04-30 | 2026-09-30 | 294 |  | 2026-11-17T11:26 |
| indicator.us_cli | oecd | OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA.M.LI.IX._Z.AA.IX._Z.H | ja | 1955-01-31 | 2026-10-31 | 862 |  | 2026-11-17T11:26 |
| indicator.us_indpro | fred | INDPRO | ja | 1919-01-01 | 2026-09-01 | 38742 |  | 2026-11-17T11:26 |
| indicator.us_unrate | fred | UNRATE | ja | 1948-01-01 | 2026-10-01 | 2199 |  | 2026-11-17T11:26 |
| indicator.us_curve_10y3m | fred | T10Y3M | ja | 1982-01-04 | 2026-11-16 | 11220 |  | 2026-11-17T11:26 |
| indicator.us_credit_spread | fred | BAA10Y | ja | 1986-01-02 | 2026-11-13 | 10217 |  | 2026-11-17T11:26 |
| indicator.us_hy_spread_recent | fred | BAMLH0A0HYM2 | ja | 2023-11-17 | 2026-11-13 | 784 |  | 2026-11-17T11:26 |
| indicator.us_real_retail | fred | RRSFS | ja | 1992-01-01 | 2026-09-01 | 6860 |  | 2026-11-17T11:26 |
| indicator.us_core_cpi | fred | CPILFESL | ja | 1957-01-01 | 2026-10-01 | 2261 |  | 2026-11-17T11:26 |
| indicator.us_breakeven_5y5y | fred | T5YIFR | ja | 2003-01-02 | 2026-11-16 | 5972 |  | 2026-11-17T11:26 |
| indicator.us_wages | fred | AHETPI | ja | 1964-01-01 | 2026-10-01 | 3993 |  | 2026-11-17T11:26 |
| indicator.us_ppi | fred | PPIACO | ja | 1913-01-01 | 2026-10-01 | 1839 |  | 2026-11-17T11:26 |
| indicator.us_cpi_nsa | fred | CPIAUCNS | ja | 1913-01-01 | 2026-10-01 | 1365 |  | 2026-11-17T11:24 |
| indicator.ea_cli | oecd | OECD.SDD.STES,DSD_STES@DF_CLI,4.1/DEU.M.LI.IX._Z.AA.IX._Z.H | ja | 1961-01-31 | 2026-10-31 | 790 |  | 2026-11-17T11:26 |
| indicator.ea_indpro | eurostat | sts_inpr_m/M.PRD.B-D.SCA.I21.EA20 | ja | 1991-01-31 | 2026-09-30 | 429 |  | 2026-11-17T11:26 |
| indicator.ea_unrate | eurostat | une_rt_m/M.SA.TOTAL.PC_ACT.T.EA20 | NEIN |  |  | 0 |  |  |
| indicator.ea_euribor_3m | ecb | FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA | ja | 1994-01-31 | 2026-10-31 | 394 |  | 2026-11-17T11:26 |
| indicator.ea_retail | eurostat | sts_trtu_m/M.VOL_SLS.G47.SCA.I21.EA20 | ja | 2000-01-31 | 2026-09-30 | 321 |  | 2026-11-17T11:26 |
| indicator.ea_core_hicp | ecb | ICP/M.U2.N.XEF000.4.INX | ja | 1996-01-31 | 2025-12-31 | 313 |  | 2026-11-17T11:26 |
| indicator.ea_ppi | eurostat | sts_inpp_m/M.PRC_PRR.B-E36.NSA.I21.EA20 | ja | 2000-01-31 | 2026-09-30 | 321 |  | 2026-11-17T11:26 |
| indicator.us_credit_gap | bis | WS_CREDIT_GAP/Q.US.P.A.C | ja | 1957-12-31 | 2026-03-31 | 274 |  | 2026-11-17T11:26 |
| indicator.us_dsr_private | bis | WS_DSR/Q.US.P | ja | 1999-03-31 | 2026-03-31 | 109 |  | 2026-11-17T11:26 |
| indicator.us_policy_rate | fred | DFF | ja | 1954-07-01 | 2026-11-13 | 26434 |  | 2026-11-17T11:26 |
##[endgroup]
##[group]reports/sources_latest.md
# Quellen und Reihen

## Quellen

| Quelle | Priorität | eingeschaltet | kostenpflichtig | nutzbar | Hinweis | Lizenz |
| --- | --- | --- | --- | --- | --- | --- |
| eodhd | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | EODHD (Abo erforderlich) |
| msci | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | MSCI Private Asset Indexes, Lizenz erforderlich |
| sipa | 5 | nein | ja | nein | in config/sources.yaml ausgeschaltet | SIPA / Scientific Infra (infra300), Lizenz erforderlich |
| bundesbank | 8 | ja | nein | ja |  | Deutsche Bundesbank, freie Nutzung mit Quellenangabe |
| coinmetrics | 10 | ja | nein | ja |  | Coin Metrics Community Data, Creative Commons (CC BY-NC 4.0) |
| ecb | 10 | ja | nein | ja |  | ECB Data Portal, freie Nutzung mit Quellenangabe |
| fred | 10 | ja | nein | ja |  | FRED Terms of Use |
| bis | 20 | ja | nein | ja |  | BIS, freie Nutzung mit Quellenangabe |
| eurostat | 20 | ja | nein | ja |  | Eurostat, freie Weiterverwendung mit Quellenangabe |
| oecd | 20 | ja | nein | ja |  | OECD Terms and Conditions |
| yfinance | 20 | ja | nein | ja |  | Yahoo Finance, inoffizielle Schnittstelle, nur private Nutzung |
| tiingo | 30 | ja | nein | ja |  | Tiingo, Gratis-Tarif nur für private Nutzung |
| issuer_nav | 40 | ja | nein | ja |  | Emittenten-Websites (iShares), Nutzungsbedingungen je Emittent |
| private_infra | 50 | ja | nein | ja |  | Veröffentlichte Eckwerte Dritter; Nutzungsbedingungen der Seiten beachten |
| static | 60 | ja | nein | ja |  | Je Datensatz (French, AQR, Nareit, JST, Shiller); JST und AQR nur nicht-kommerziell |

## Rohreihen je Quelle

| Reihe | Quelle | Symbol | vorhanden | von | bis | Werte | erwartet ab | abgerufen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| asset.equity_us.vfinx | tiingo | VFINX | ja | 1976-08-31 | 2026-11-16 | 12578 | 1976-08 | 2026-11-17T11:24 |
| asset.equity_us.vfinx | yfinance | VFINX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1976-08 | 2026-11-17T11:24 |
| asset.equity_us.vfinx.fallback | tiingo | SPY | ja | 1993-01-29 | 2026-11-16 | 8508 |  | 2026-11-17T11:24 |
| asset.equity_us.vfinx.fallback | yfinance | SPY | ja | 1993-01-29 | 2026-11-16 | 8508 |  | 2026-11-17T11:24 |
| asset.equity_us.french_us_market | static | french_us_factors:Mkt-RF+RF | ja | 1926-07-31 | 2026-09-30 | 1203 | 1926-07 | 2026-11-17T11:24 |
| asset.equity_europe.vgk | tiingo | VGK | ja | 2005-03-10 | 2026-11-16 | 5457 | 2005-03 | 2026-11-17T11:24 |
| asset.equity_europe.vgk | yfinance | VGK | ja | 2005-03-10 | 2026-11-16 | 5457 | 2005-03 | 2026-11-17T11:24 |
| asset.equity_europe.ezu | tiingo | EZU | ja | 2001-01-02 | 2026-11-16 | 6507 | 2000-07 | 2026-11-17T11:24 |
| asset.equity_europe.ezu | yfinance | EZU | ja | 2000-07-31 | 2026-11-16 | 6614 | 2000-07 | 2026-11-17T11:24 |
| asset.equity_europe.french_europe | static | french_europe:Mkt-RF+RF | ja | 1990-07-31 | 2026-09-30 | 435 | 1990-07 | 2026-11-17T11:24 |
| asset.equity_europe.french_intl_europe | static | french_intl_europe:Mkt | ja | 1975-01-31 | 2025-12-31 | 612 | 1975-01 | 2026-11-17T11:24 |
| asset.equity_japan.ewj | tiingo | EWJ | ja | 1996-04-01 | 2026-11-16 | 7707 | 1996-03 | 2026-11-17T11:24 |
| asset.equity_japan.ewj | yfinance | EWJ | ja | 1996-03-18 | 2026-11-16 | 7717 | 1996-03 | 2026-11-17T11:24 |
| asset.equity_japan.french_japan | static | french_japan:Mkt-RF+RF | ja | 1990-07-31 | 2026-09-30 | 435 | 1990-07 | 2026-11-17T11:24 |
| asset.equity_japan.french_intl_japan | static | french_intl_japan:Mkt | ja | 1975-01-31 | 2025-12-31 | 612 | 1975-01 | 2026-11-17T11:24 |
| asset.equity_em.veiex | tiingo | VEIEX | ja | 1994-05-04 | 2026-11-16 | 8190 | 1994-05 | 2026-11-17T11:24 |
| asset.equity_em.veiex | yfinance | VEIEX | ja | 1994-05-04 | 2026-11-16 | 8190 | 1994-05 | 2026-11-17T11:24 |
| asset.equity_em.veiex.fallback | tiingo | EEM | ja | 2003-04-11 | 2026-11-16 | 5938 |  | 2026-11-17T11:24 |
| asset.equity_em.veiex.fallback | yfinance | EEM | ja | 2003-04-14 | 2026-11-16 | 5937 |  | 2026-11-17T11:24 |
| asset.equity_em.french_emerging | static | french_emerging:Mkt-RF+RF | ja | 1989-07-31 | 2026-09-30 | 447 | 1989-07 | 2026-11-17T11:24 |
| asset.bond_eur_short.ishares_eur_govt_1_3 | issuer_nav | ishares_eur_govt_1_3 | NEIN |  |  | 0 | 2006-06 |  |
| asset.bond_eur_short.ishares_eur_govt_1_3 | yfinance | IBCA.DE | ja | 2008-12-23 | 2026-11-17 | 4543 | 2006-06 | 2026-11-17T11:24 |
| asset.bond_eur_short.synth_bund_2y.yield | bundesbank | BBSIS/M.I.ZST.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A | ja | 1972-09-30 | 2026-10-31 | 650 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.ishares_core_eur_govt | issuer_nav | ishares_core_eur_govt | NEIN |  |  | 0 | 2009-04 |  |
| asset.bond_eur_long.ishares_core_eur_govt | yfinance | EUNH.DE | ja | 2009-04-17 | 2026-11-17 | 4469 | 2009-04 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | bundesbank | BBSIS/M.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A | ja | 1972-09-30 | 2026-10-31 | 650 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | fred | IRLTLT01DEM156N | ja | 1956-05-01 | 2026-10-01 | 846 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_eur_long.synth_bund_10y.yield | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/DEU.M.IRLT.PA._Z._Z._Z._Z.N | ja | 1956-05-31 | 2026-10-31 | 846 | 1972-09 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx | tiingo | VUSTX | ja | 1986-05-19 | 2026-11-16 | 10203 | 1986-05 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx | yfinance | VUSTX | ja | 1986-05-19 | 2026-11-16 | 10203 | 1986-05 | 2026-11-17T11:24 |
| asset.bond_us_long.vustx.fallback | tiingo | TLT | ja | 2002-07-26 | 2026-11-16 | 6117 |  | 2026-11-17T11:24 |
| asset.bond_us_long.vustx.fallback | yfinance | TLT | ja | 2002-07-30 | 2026-11-16 | 6115 |  | 2026-11-17T11:24 |
| asset.bond_us_long.synth_ust_30y.yield | fred | DGS30 | ja | 1977-02-15 | 2026-11-13 | 12432 | 1977-02 | 2026-11-17T11:24 |
| asset.bond_us_long.synth_ust_10y.yield | fred | DGS10 | ja | 1962-01-02 | 2026-11-13 | 16202 | 1962-01 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx | tiingo | VIPSX | ja | 2000-06-29 | 2026-11-16 | 6635 | 2000-06 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx | yfinance | VIPSX | ja | 2000-06-29 | 2026-11-16 | 6635 | 2000-06 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx.fallback | tiingo | TIP | ja | 2003-12-05 | 2026-11-16 | 5773 |  | 2026-11-17T11:24 |
| asset.bond_inflation_linked.vipsx.fallback | yfinance | TIP | ja | 2003-12-05 | 2026-11-16 | 5773 |  | 2026-11-17T11:24 |
| asset.bond_inflation_linked.synth_tips_10y.yield | fred | DFII10 | ja | 2003-01-02 | 2026-11-13 | 5971 | 2003-01 | 2026-11-17T11:24 |
| asset.bond_inflation_linked.synth_tips_10y.cpi | fred | CPIAUCNS | ja | 1913-01-01 | 2026-10-01 | 1365 |  | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx | tiingo | VWESX | ja | 1980-01-02 | 2026-11-16 | 11816 | 1973-07 | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx | yfinance | VWESX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1973-07 | 2026-11-17T11:24 |
| asset.bond_corp_ig.vwesx.fallback | tiingo | LQD | ja | 2002-07-26 | 2026-11-16 | 6117 |  | 2026-11-17T11:25 |
| asset.bond_corp_ig.vwesx.fallback | yfinance | LQD | ja | 2002-07-30 | 2026-11-16 | 6115 |  | 2026-11-17T11:24 |
| asset.bond_corp_ig.synth_baa_daily.yield | fred | DBAA | ja | 1986-01-02 | 2026-11-13 | 10253 | 1986-01 | 2026-11-17T11:25 |
| asset.bond_corp_ig.synth_baa_monthly.yield | fred | BAA | ja | 1919-01-01 | 2026-10-01 | 1294 | 1919-01 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx | tiingo | VWEHX | ja | 1980-01-02 | 2026-11-16 | 11816 | 1978-12 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx | yfinance | VWEHX | ja | 1980-01-02 | 2026-11-16 | 11815 | 1978-12 | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx.fallback | tiingo | HYG | ja | 2007-04-11 | 2026-11-16 | 4933 |  | 2026-11-17T11:25 |
| asset.bond_high_yield.vwehx.fallback | yfinance | HYG | ja | 2007-04-11 | 2026-11-16 | 4933 |  | 2026-11-17T11:25 |
| asset.bond_em.premx | tiingo | PREMX | ja | 1995-01-03 | 2026-11-16 | 8022 | 1994-12 | 2026-11-17T11:25 |
| asset.bond_em.premx | yfinance | PREMX | ja | 1994-12-30 | 2026-11-16 | 8023 | 1994-12 | 2026-11-17T11:25 |
| asset.bond_em.premx.fallback | tiingo | EMB | ja | 2007-12-19 | 2026-11-16 | 4757 |  | 2026-11-17T11:25 |
| asset.bond_em.premx.fallback | yfinance | EMB | ja | 2007-12-19 | 2026-11-16 | 4757 |  | 2026-11-17T11:25 |
| asset.gold.gld | tiingo | GLD | ja | 2004-11-18 | 2026-11-16 | 5533 | 2004-11 | 2026-11-17T11:25 |
| asset.gold.gld | yfinance | GLD | ja | 2004-11-18 | 2026-11-16 | 5533 | 2004-11 | 2026-11-17T11:25 |
| asset.gold.gld.fallback | yfinance | GC=F | ja | 2000-08-30 | 2026-11-17 | 6580 |  | 2026-11-17T11:25 |
| asset.gold.gold_london_fix | static | worldbank_pinksheet:Gold | ja | 1960-01-31 | 2024-12-31 | 780 | 1960-01 | 2026-11-17T11:25 |
| asset.commodities.pcrix | tiingo | PCRIX | ja | 2002-07-01 | 2026-11-16 | 6134 | 2002-06 | 2026-11-17T11:25 |
| asset.commodities.pcrix | yfinance | PCRIX | ja | 2002-07-01 | 2026-11-16 | 6135 | 2002-06 | 2026-11-17T11:25 |
| asset.commodities.pcrix.fallback | tiingo | DBC | ja | 2006-02-03 | 2026-11-16 | 5229 |  | 2026-11-17T11:25 |
| asset.commodities.pcrix.fallback | yfinance | DBC | ja | 2006-02-06 | 2026-11-16 | 5228 |  | 2026-11-17T11:25 |
| asset.commodities.aqr_commodities | static | aqr_commodities:Excess return of equal-weight commodities portfolio | ja | 1877-02-28 | 2025-05-31 | 1780 | 1877-02 | 2026-11-17T11:25 |
| asset.reits.vgsix | tiingo | VGSIX | ja | 1996-05-13 | 2026-11-16 | 7678 | 1996-05 | 2026-11-17T11:25 |
| asset.reits.vgsix | yfinance | VGSIX | ja | 1996-05-13 | 2026-11-16 | 7678 | 1996-05 | 2026-11-17T11:25 |
| asset.reits.vgsix.fallback | tiingo | VNQ | ja | 2004-09-29 | 2026-11-16 | 5569 |  | 2026-11-17T11:25 |
| asset.reits.vgsix.fallback | yfinance | VNQ | ja | 2004-09-29 | 2026-11-16 | 5569 |  | 2026-11-17T11:25 |
| asset.reits.nareit_all_equity | static | nareit:all_equity | ja | 1972-01-31 | 2026-10-31 | 658 | 1972-01 | 2026-11-17T11:25 |
| asset.infrastructure.ishares_global_infra_ucits | issuer_nav | ishares_global_infra | NEIN |  |  | 0 | 2006-10 |  |
| asset.infrastructure.ishares_global_infra_ucits | yfinance | IQQI.DE | ja | 2008-12-23 | 2026-11-17 | 4535 | 2006-10 | 2026-11-17T11:25 |
| asset.infrastructure.igf | tiingo | IGF | ja | 2007-12-12 | 2026-11-16 | 4762 | 2007-12 | 2026-11-17T11:25 |
| asset.infrastructure.igf | yfinance | IGF | ja | 2007-12-12 | 2026-11-16 | 4762 | 2007-12 | 2026-11-17T11:25 |
| asset.infrastructure.french_utilities_telecom.c0 | static | french_ind12:Utils | ja | 1926-07-31 | 2026-09-30 | 1203 |  | 2026-11-17T11:25 |
| asset.infrastructure.french_utilities_telecom.c1 | static | french_ind12:Telcm | ja | 1926-07-31 | 2026-09-30 | 1203 |  | 2026-11-17T11:25 |
| asset.trend.dbmf | tiingo | DBMF | ja | 2019-05-08 | 2026-11-16 | 1893 | 2019-05 | 2026-11-17T11:25 |
| asset.trend.dbmf | yfinance | DBMF | ja | 2019-05-08 | 2026-11-16 | 1893 | 2019-05 | 2026-11-17T11:25 |
| asset.trend.dbmf.fallback | tiingo | KMLM | ja | 2020-12-02 | 2026-11-16 | 1496 |  | 2026-11-17T11:25 |
| asset.trend.dbmf.fallback | yfinance | KMLM | ja | 2020-12-02 | 2026-11-16 | 1496 |  | 2026-11-17T11:25 |
| asset.trend.aqr_tsmom | static | aqr_tsmom:TSMOM | ja | 1985-01-31 | 2026-05-31 | 497 | 1985-01 | 2026-11-17T11:25 |
| asset.bitcoin.btc_reference_rate | coinmetrics | btc | ja | 2010-07-18 | 2026-11-16 | 5966 | 2010-07 | 2026-11-17T11:25 |
| asset.bitcoin.btc_reference_rate | yfinance | BTC-USD | ja | 2014-09-17 | 2026-11-17 | 4445 | 2010-07 | 2026-11-17T11:25 |
| reference.hicl | yfinance | HICL.L | ja | 2006-03-28 | 2026-11-17 | 5216 |  | 2026-11-17T11:25 |
| reference.inpp | yfinance | INPP.L | ja | 2006-11-08 | 2026-11-17 | 5060 |  | 2026-11-17T11:25 |
| reference.three_i_infra | yfinance | 3IN.L | ja | 2007-03-08 | 2026-11-17 | 4977 |  | 2026-11-17T11:25 |
| reference.msci_world | tiingo | URTH | ja | 2012-01-12 | 2026-11-16 | 3733 |  | 2026-11-17T11:25 |
| reference.msci_world | yfinance | URTH | ja | 2012-01-12 | 2026-11-16 | 3733 |  | 2026-11-17T11:25 |
| fx.USD.per_eur | ecb | EXR/D.USD.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.GBP.per_eur | ecb | EXR/D.GBP.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.CHF.per_eur | ecb | EXR/D.CHF.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.JPY.per_eur | ecb | EXR/D.JPY.EUR.SP00.A | ja | 1999-01-04 | 2026-11-16 | 7137 |  | 2026-11-17T11:25 |
| fx.EUR.usd_per_unit | fred | DEXUSEU | ja | 1999-01-04 | 2026-11-13 | 6988 |  | 2026-11-17T11:25 |
| fx.EUR.dem_per_usd | bundesbank | BBEX3/D.USD.DEM.AA.AC.000 | ja | 1948-06-21 | 1998-12-30 | 13050 |  | 2026-11-17T11:25 |
| fx.EUR.dem_per_usd | fred | EXGEUS | ja | 1971-01-01 | 2001-12-01 | 372 |  | 2026-11-17T11:25 |
| fx.GBP.usd_per_unit | fred | DEXUSUK | ja | 1971-01-04 | 2026-11-13 | 14009 |  | 2026-11-17T11:25 |
| fx.CHF.per_usd | fred | DEXSZUS | ja | 1971-01-04 | 2026-11-13 | 14009 |  | 2026-11-17T11:25 |
| fx.JPY.per_usd | fred | DEXJPUS | ja | 1971-01-04 | 2026-11-13 | 14003 |  | 2026-11-17T11:25 |
| rate.EUR.estr | ecb | EST/B.EU000A2X2A25.WT | ja | 2019-10-01 | 2026-11-16 | 1826 |  | 2026-11-17T11:26 |
| rate.EUR.eonia | ecb | EON/D.EONIA_TO.RATE | ja | 1999-01-04 | 2021-12-31 | 5890 |  | 2026-11-17T11:26 |
| rate.EUR.de_3m_interbank | fred | IR3TIB01DEM156N | ja | 1960-01-01 | 2026-10-01 | 802 |  | 2026-11-17T11:26 |
| rate.EUR.de_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/DEU.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1960-01-31 | 2026-10-31 | 802 |  | 2026-11-17T11:26 |
| rate.USD.fed_funds | fred | DFF | ja | 1954-07-01 | 2026-11-13 | 26434 |  | 2026-11-17T11:26 |
| rate.GBP.sonia | fred | IUDSOIA | ja | 1997-01-02 | 2026-11-13 | 7548 |  | 2026-11-17T11:26 |
| rate.GBP.gb_3m_interbank | fred | IR3TIB01GBM156N | ja | 1957-01-01 | 2026-01-01 | 829 |  | 2026-11-17T11:26 |
| rate.GBP.gb_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/GBR.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1986-01-31 | 2026-02-28 | 482 |  | 2026-11-17T11:26 |
| rate.CHF.ch_3m_interbank | fred | IR3TIB01CHM156N | ja | 1999-07-01 | 2026-10-01 | 328 |  | 2026-11-17T11:26 |
| rate.CHF.ch_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/CHE.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 1999-07-31 | 2026-10-31 | 328 |  | 2026-11-17T11:26 |
| rate.JPY.jp_3m_interbank | fred | IR3TIB01JPM156N | ja | 2002-04-01 | 2026-09-01 | 294 |  | 2026-11-17T11:26 |
| rate.JPY.jp_3m_interbank | oecd | OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/JPN.M.IR3TIB.PA._Z._Z._Z._Z.N | ja | 2002-04-30 | 2026-09-30 | 294 |  | 2026-11-17T11:26 |
| indicator.us_cli | oecd | OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA.M.LI.IX._Z.AA.IX._Z.H | ja | 1955-01-31 | 2026-10-31 | 862 |  | 2026-11-17T11:26 |
| indicator.us_indpro | fred | INDPRO | ja | 1919-01-01 | 2026-09-01 | 38742 |  | 2026-11-17T11:26 |
| indicator.us_unrate | fred | UNRATE | ja | 1948-01-01 | 2026-10-01 | 2199 |  | 2026-11-17T11:26 |
| indicator.us_curve_10y3m | fred | T10Y3M | ja | 1982-01-04 | 2026-11-16 | 11220 |  | 2026-11-17T11:26 |
| indicator.us_credit_spread | fred | BAA10Y | ja | 1986-01-02 | 2026-11-13 | 10217 |  | 2026-11-17T11:26 |
| indicator.us_hy_spread_recent | fred | BAMLH0A0HYM2 | ja | 2023-11-17 | 2026-11-13 | 784 |  | 2026-11-17T11:26 |
| indicator.us_real_retail | fred | RRSFS | ja | 1992-01-01 | 2026-09-01 | 6860 |  | 2026-11-17T11:26 |
| indicator.us_core_cpi | fred | CPILFESL | ja | 1957-01-01 | 2026-10-01 | 2261 |  | 2026-11-17T11:26 |
| indicator.us_breakeven_5y5y | fred | T5YIFR | ja | 2003-01-02 | 2026-11-16 | 5972 |  | 2026-11-17T11:26 |
| indicator.us_wages | fred | AHETPI | ja | 1964-01-01 | 2026-10-01 | 3993 |  | 2026-11-17T11:26 |
| indicator.us_ppi | fred | PPIACO | ja | 1913-01-01 | 2026-10-01 | 1839 |  | 2026-11-17T11:26 |
| indicator.us_cpi_nsa | fred | CPIAUCNS | ja | 1913-01-01 | 2026-10-01 | 1365 |  | 2026-11-17T11:24 |
| indicator.ea_cli | oecd | OECD.SDD.STES,DSD_STES@DF_CLI,4.1/DEU.M.LI.IX._Z.AA.IX._Z.H | ja | 1961-01-31 | 2026-10-31 | 790 |  | 2026-11-17T11:26 |
| indicator.ea_indpro | eurostat | sts_inpr_m/M.PRD.B-D.SCA.I21.EA20 | ja | 1991-01-31 | 2026-09-30 | 429 |  | 2026-11-17T11:26 |
| indicator.ea_unrate | eurostat | une_rt_m/M.SA.TOTAL.PC_ACT.T.EA20 | NEIN |  |  | 0 |  |  |
| indicator.ea_euribor_3m | ecb | FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA | ja | 1994-01-31 | 2026-10-31 | 394 |  | 2026-11-17T11:26 |
| indicator.ea_retail | eurostat | sts_trtu_m/M.VOL_SLS.G47.SCA.I21.EA20 | ja | 2000-01-31 | 2026-09-30 | 321 |  | 2026-11-17T11:26 |
| indicator.ea_core_hicp | ecb | ICP/M.U2.N.XEF000.4.INX | ja | 1996-01-31 | 2025-12-31 | 313 |  | 2026-11-17T11:26 |
| indicator.ea_ppi | eurostat | sts_inpp_m/M.PRC_PRR.B-E36.NSA.I21.EA20 | ja | 2000-01-31 | 2026-09-30 | 321 |  | 2026-11-17T11:26 |
| indicator.us_credit_gap | bis | WS_CREDIT_GAP/Q.US.P.A.C | ja | 1957-12-31 | 2026-03-31 | 274 |  | 2026-11-17T11:26 |
| indicator.us_dsr_private | bis | WS_DSR/Q.US.P | ja | 1999-03-31 | 2026-03-31 | 109 |  | 2026-11-17T11:26 |
| indicator.us_policy_rate | fred | DFF | ja | 1954-07-01 | 2026-11-13 | 26434 |  | 2026-11-17T11:26 |
##[endgroup]
##[group]Run actions/upload-artifact@v4
with:
  name: live-daten-bericht
  path: reports/
live	Run actions/upload-artifact@v4	*.log
live	Run actions/upload-artifact@v4	data/runs/
live	Run actions/upload-artifact@v4	
  if-no-files-found: warn
  compression-level: 6
  overwrite: false
  include-hidden-files: false
env:
  PYTHONUTF8: 1
  FRED_API_KEY: ***
  TIINGO_API_KEY: ***
  UV_PYTHON: 3.12
  VIRTUAL_ENV: /home/runner/work/allocation-navigator/allocation-navigator/.venv
  UV_CACHE_DIR: /home/runner/work/_temp/setup-uv-cache
##[endgroup]
(node:2672) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
With the provided path, there will be 10 files uploaded
Artifact name is valid!
Root directory input is valid!
Beginning upload of artifact content to blob storage
(node:2672) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized and prone to errors that have security implications. Use the WHATWG URL API instead. CVEs are not issued for `url.parse()` vulnerabilities.
Uploaded bytes 41259
Finished uploading artifact content to blob storage!
SHA256 digest of uploaded artifact zip is 85e26e717d35d7312dab0b1a3133f3dffdf033756632d5124ddc8e61b6226990
Finalizing artifact upload
Artifact live-daten-bericht.zip successfully finalized. Artifact ID 14323757662
Artifact live-daten-bericht has been successfully uploaded! Final size is 41259 bytes. Artifact ID is 14323757662
Artifact download URL: https://github.com/tobiasashtree-coder/allocation-navigator/actions/runs/44073656403/artifacts/14323757662
Post job cleanup.
Cache hit occurred on key setup-uv-1-x86_64-unknown-linux-gnu-3.12-cf3749fb4e3ac98e393ee0b8b95ec052b7275563163003745594bd2f6a7b75c3, not saving cache.
(node:2684) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
Post job cleanup.
[command]/usr/bin/git version
git version 2.56.1
Temporarily overriding HOME='/home/runner/work/_temp/d4cff6b1-1d74-43fb-bf42-33747b8d43b5' before making global git config changes
Adding repository directory to the temporary git global config as a safe directory
[command]/usr/bin/git config --global --add safe.directory /home/runner/work/allocation-navigator/allocation-navigator
[command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
[command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
[command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
http.https://github.com/.extraheader
[command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
[command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
[command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
[command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
Cleaning up orphan processes
##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/upload-artifact@v4, astral-sh/setup-uv@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners
