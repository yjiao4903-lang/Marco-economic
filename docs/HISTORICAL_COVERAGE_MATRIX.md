# Historical Coverage Matrix (V4.5 Historical Completion)

> Generated 2026-08-30 by `python scripts/historical_coverage.py` from live canonical data + declared source-transition metadata. Read-only: nothing modified, no weights/thresholds/signal declarations touched, no synthetic rows. Target: 2012-present (minimum priority 2015-present); never splice incomparable data to hit a date target.

## Legend

- **earliest_observation**: first real canonical observation for the input series.
- **comparable_history_start / minimum_validation_start**: PIT first day the signal scored. Comparable history is shortened rather than fabricated if a splice is not definition-equivalent.
- **current_source**: route primary+fallback from data_sources.yaml.
- **historical_source**: declared historical/backfill leg (Wind one-shot, FRED, etc.).
- **revision_risk**: HIGH=full_refresh / MEDIUM=replace_window / LOW=append.
- **breakpoints**: declared structural breaks.
- **status**: shared resolved status (READY/WARMUP/PARTIAL/MISSING_INPUT).
- **blocker**: declared honest blocker (empty = none).

## Core signals

| signal_id   | name                      | input_series            | role       | earliest_observation   | current_source      | historical_source                                                     | frequency   | revision_risk   | status   | comparable_history_start   | blocker                                                                             |
|:------------|:--------------------------|:------------------------|:-----------|:-----------------------|:--------------------|:----------------------------------------------------------------------|:------------|:----------------|:---------|:---------------------------|:------------------------------------------------------------------------------------|
| G1          | China CLI                 | CHN_CLI                 | level      | 1992-05-01             | oecd                | same as current / n/a                                                 | monthly     | MEDIUM          | READY    | 1992-05-01                 |                                                                                     |
| G2          | PMI New Orders            | CHN_PMI_NEW_ORDERS      | level      | 2025-10-31             | nbs+wind_manual     | same as current / n/a                                                 | monthly     | LOW             | READY    | 2025-10-31                 |                                                                                     |
| G3          | Hard Activity Composite   | CN_IND_PROD_YOY         | preferred  | 2008-02-29             | akshare+wind_manual | same as current / n/a                                                 | monthly     | LOW             | READY    | 2008-02-29                 |                                                                                     |
| G3          | Hard Activity Composite   | CN_RETAIL_SALES_YOY     | preferred  | 2008-01-31             | akshare+wind_manual | same as current / n/a                                                 | monthly     | LOW             | READY    | 2008-02-29                 |                                                                                     |
| G3          | Hard Activity Composite   | CHN_IND_PROD_INDEX      | fallback   | 1996-01-01             | oecd                | same as current / n/a                                                 | monthly     | MEDIUM          | READY    | 2008-02-29                 |                                                                                     |
| G3          | Hard Activity Composite   | CHN_RETAIL_SALES_INDEX  | fallback   | 1978-01-01             | oecd                | same as current / n/a                                                 | monthly     | MEDIUM          | READY    | 2008-02-29                 |                                                                                     |
| G4          | Property Demand Composite | CN_PROPERTY_SALES_AREA  | component  | 2025-09-30             | nbs+wind_manual     | same as current / n/a                                                 | monthly     | LOW             | READY    | 2025-09-30                 |                                                                                     |
| G4          | Property Demand Composite | CN_PROPERTY_SALES_VALUE | component  | 2025-09-30             | nbs+wind_manual     | same as current / n/a                                                 | monthly     | LOW             | READY    | 2025-09-30                 |                                                                                     |
| G5          | Export Demand             | CHN_EXPORT_YOY          | level      | 1992-02-01             | oecd                | same as current / n/a                                                 | monthly     | MEDIUM          | READY    | 1992-02-01                 |                                                                                     |
| I1          | Consumer Inflation        | CN_CORE_CPI_YOY         | preferred  | 2025-10-31             | nbs+wind_manual     | NBS CPI release historical (via update pipeline)                      | monthly     | LOW             | READY    | 2012-12-31                 |                                                                                     |
| I1          | Consumer Inflation        | CN_CPI_YOY              | fallback   | 2008-01-31             | akshare+wind_manual | same as current / n/a                                                 | monthly     | LOW             | READY    | 2012-12-31                 |                                                                                     |
| I2          | Industrial Inflation      | CN_PPI_YOY              | level      | 2006-01-31             | akshare+wind_manual | same as current / n/a                                                 | monthly     | LOW             | READY    | 2010-12-31                 |                                                                                     |
| I3          | Cost Pressure Composite   | CHN_PMI_INPUT_PRICE     | component  | 2024-10-31             | nbs+wind_manual     | same as current / n/a                                                 | monthly     | LOW             | READY    | 2002-08-31                 |                                                                                     |
| I3          | Cost Pressure Composite   | US_GSCPI                | component  | 1997-09-30             | nyfed               | same as current / n/a                                                 | monthly     | HIGH            | READY    | 2002-08-31                 |                                                                                     |
| D1          | Funding Condition         | CN_DR007                | spread_leg | 2017-05-31             | chinamoney+akshare  | same as current / n/a                                                 | daily       | LOW             | READY    | 2024-12-30                 |                                                                                     |
| D1          | Funding Condition         | CN_POLICY_RATE_7D       | spread_leg | 2024-01-01             | pbc+manual_series   | Committed step file data/manual_series/ (MANUAL provenance bootstrap) | daily       | MEDIUM          | READY    | 2024-12-30                 |                                                                                     |
| D2          | Private Credit Impulse    | CN_TSF_TOTAL            | spread_leg | 2026-04-30             | pbc+akshare         | Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)           | monthly     | MEDIUM          | WARMUP   |                            | wind_backfill_tsf.csv NOT yet provided by user (P0-1) - WARMUP, no splice           |
| D2          | Private Credit Impulse    | CN_GOV_BOND_FINANCING   | spread_leg | 2026-04-30             | pbc                 | Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)           | monthly     | MEDIUM          | WARMUP   |                            | wind_backfill_tsf.csv NOT yet provided by user (P0-1) - WARMUP, no splice           |
| D3          | Excess Liquidity          | CN_M2_YOY               | spread_leg | 2008-01-31             | akshare+wind_manual | same as current / n/a                                                 | monthly     | LOW             | READY    | 2026-04-30                 |                                                                                     |
| D3          | Excess Liquidity          | CN_PRIVATE_TSF_YOY      | spread_leg | 2026-04-30             | pbc                 | same as current / n/a                                                 | monthly     | LOW             | READY    | 2026-04-30                 |                                                                                     |
| D4          | Fiscal Support            | CN_GOV_BOND_FINANCING   | level      | 2026-04-30             | pbc                 | Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)           | monthly     | MEDIUM          | WARMUP   |                            | wind_backfill_tsf.csv NOT yet provided by user (P0-1) - WARMUP, no splice           |
| X1          | US 10Y Real Yield         | US_REAL_YIELD_10Y       | level      | 2024-01-02             | treasury+fred       | FRED DFII10 (fallback; NOT merged - overlap BLOCKED by FRED network)  | daily       | LOW             | READY    | 2024-12-31                 | FRED DFII10 unreachable (overlap BLOCKED 2026-08-30) - no FRED rows merged yet      |
| X2          | Broad USD                 | USD_BROAD               | level      | 2026-08-17             | fred+fed_h10        | FRED DTWEXBGS (network BLOCKED; only H.10 fallback live so far)       | daily       | LOW             | WARMUP   |                            | FRED DTWEXBGS unreachable - only H.10 fallback weeks, history insufficient (WARMUP) |
| X3          | ANFCI                     | ANFCI                   | level      | 1971-01-08             | chicagofed+fred     | same as current / n/a                                                 | weekly      | MEDIUM          | READY    | 1973-12-28                 |                                                                                     |

## Market signals

| signal_id   | name                                | input_series         | role         | earliest_observation   | current_source         | historical_source     | frequency   | revision_risk   | status   | comparable_history_start   | blocker   |
|:------------|:------------------------------------|:---------------------|:-------------|:-----------------------|:-----------------------|:----------------------|:------------|:----------------|:---------|:---------------------------|:----------|
| M1          | CSI 300                             | CSI300               | confirmation | 2002-01-04             | eastmoney+akshare      | same as current / n/a | daily       | LOW             | READY    |                            |           |
| M2          | Hang Seng Index                     | HSI                  | confirmation | 2013-08-20             | eastmoney+akshare      | same as current / n/a | daily       | LOW             | READY    |                            |           |
| M3          | China 10Y Government Yield          | CN_GOV_YIELD_10Y     | confirmation | 2023-05-17             | chinabond+wind_manual  | same as current / n/a | daily       | LOW             | READY    |                            |           |
| M4          | AAA Credit Spread                   | CN_AAA_CREDIT_SPREAD | confirmation | 2007-12-21             | chinabond+wind_manual  | same as current / n/a | daily       | LOW             | READY    |                            |           |
| M5          | USD/CNY                             | USD_CNY              | confirmation | 2016-01-04             | chinamoney+wind_manual | same as current / n/a | daily       | LOW             | READY    |                            |           |
| M6          | Industrial Commodity / Copper Proxy | COPPER_PRICE         | confirmation | 2016-08-30             | akshare                | same as current / n/a | daily       | LOW             | READY    |                            |           |

## Structural signals

| signal_id   | name               | input_series         | role   | earliest_observation   | current_source   | historical_source     | frequency   | revision_risk   | status   | comparable_history_start   | blocker   |
|:------------|:-------------------|:---------------------|:-------|:-----------------------|:-----------------|:----------------------|:------------|:----------------|:---------|:---------------------------|:----------|
| S1          | Credit-to-GDP Gap  | CN_CREDIT_TO_GDP_GAP | level  | 1995-12-31             | bis              | same as current / n/a | quarterly   | HIGH            | READY    |                            |           |
| S2          | Debt Service Ratio | CN_DSR               | level  | 1999-03-31             | bis              | same as current / n/a | quarterly   | HIGH            | READY    |                            |           |

## Source-Transition notes (Task 4)

### CN_TSF_TOTAL

- **canonical_definition**: Total TSF monthly flow (cumulative increment differenced)
- **historical_source**: Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)
- **live_source**: PBOC monthly financial report (replace_window) / AKShare fallback
- **transition_date**: TBD once backfill imported
- **overlap**: TBD (overlap_check-style diff on shared months after import)
- **unit**: CNY bn monthly flow
- **frequency**: monthly
- **notes**: Same definition expected (both PBOC-sourced monthly flow), so a splice is acceptable AFTER cross-validation with the live leg; do NOT splice before overlap passes. Used by D2.
- **breakpoint**: none declared yet; validate before merging

### CN_GOV_BOND_FINANCING

- **canonical_definition**: Government bond net financing monthly flow
- **historical_source**: Wind one-shot backfill wind_backfill_tsf.csv (PENDING file)
- **live_source**: PBOC monthly financial report (replace_window)
- **transition_date**: TBD once backfill imported
- **overlap**: TBD after import
- **unit**: CNY bn monthly flow
- **frequency**: monthly
- **notes**: Used by D2 and D4. Validate overlap with live leg before merging.
- **breakpoint**: none declared yet; validate before merging

### US_REAL_YIELD_10Y

- **canonical_definition**: US 10Y real yield (Treasury Daily Par Real Yield Curve)
- **historical_source**: FRED DFII10 (fallback; NOT merged - overlap BLOCKED by FRED network)
- **live_source**: Treasury Daily Par Real Yield Curve (primary, v0.4c)
- **transition_date**: not switching until overlap_check PASS (>=60 common days)
- **overlap**: overlap_check.py BLOCKED (2026-08-30, FRED timeout)
- **unit**: percent
- **frequency**: daily
- **notes**: DFII10 IS a redistribution of the Treasury curve - same underlying data/definition. Merge gated on overlap_check PASS. Currently NO FRED rows in canonical; earlier history relies on eventual FRED reach.
- **breakpoint**: source-switch gate documented in data_sources.yaml

### USD_BROAD

- **canonical_definition**: Fed broad trade-weighted USD index (Jan2006=100)
- **historical_source**: FRED DTWEXBGS (network BLOCKED; only H.10 fallback live so far)
- **live_source**: Fed H.10 weekly release page (fallback; only recent weeks)
- **transition_date**: FRED restoration required to backfill longer history
- **overlap**: n/a until FRED reachable
- **unit**: index (Jan 2006 = 100)
- **frequency**: daily
- **notes**: Same definition both legs. X2 stays WARMUP until history accumulates. FRED backfill is automatic on update - do NOT splice synthetic rows.
- **breakpoint**: none declared; explicit WARMUP blocker

### CN_POLICY_RATE_7D

- **canonical_definition**: PBOC 7-day reverse-repo operation rate (step series)
- **historical_source**: Committed step file data/manual_series/ (MANUAL provenance bootstrap)
- **live_source**: PBOC OMO transaction announcement (replace_window)
- **transition_date**: 2024 (canonical history starts there)
- **overlap**: same official announcements in both legs - low risk
- **unit**: percent
- **frequency**: daily (step)
- **notes**: Both legs transcribed from the same official announcements - comparable by construction.
- **breakpoint**: event/step series, flat between cuts (non-continuous but defined)

### CN_CORE_CPI_YOY

- **canonical_definition**: Core CPI YoY (NBS, excludes food & energy)
- **historical_source**: NBS CPI release historical (via update pipeline)
- **live_source**: NBS official CPI release page (I1 preferred leg)
- **transition_date**: n/a - same source/definition
- **overlap**: n/a
- **unit**: percent
- **frequency**: monthly
- **notes**: I1 preferred leg; headline CN_CPI_YOY is a declared FALLBACK only (never written into core id).
- **breakpoint**: I1 fallback semantics fixed (core/headline kept as separate series_id)

### G3

- **canonical_definition**: Hard activity composite (industrial output + retail, YoY %)
- **historical_source**: OECD volume indices (declared fallback only post-switch)
- **live_source**: NBS YoY growth (CN_IND_PROD_YOY / CN_RETAIL_SALES_YOY), v1.6A G0
- **transition_date**: 2026-08 (owner-approved G3 switch)
- **overlap**: unit differs (index vs %) - NOT numerically continuous
- **unit**: percent (live) / index (historical fallback)
- **frequency**: monthly
- **notes**: Unit change index->% means pre/post are NOT numerically continuous; OECD entries kept ONLY as fallback when NBS legs are absent. Do NOT splice indices with growth percentages.
- **breakpoint**: declared breakpoint (signals.yaml G3 commentary)


## Summary

- Core signals whose inputs are all live-and-comparable to 2012+: see per-signal `comparable_history_start` above.
- Domestic target (>=3/4 READY) currently D1+D3 READY; D2/D4 held WARMUP until `wind_backfill_tsf.csv` is imported (no splice, no synthetic).
- X1 overlap check = BLOCKED (FRED reach); X2 = WARMUP (FRED blocked).