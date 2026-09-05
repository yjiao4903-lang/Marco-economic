# EXTDATA W1 Macro Ownership Baseline

**As-of**: 2026-09-05 (Asia/Shanghai)
**Repository**: `yjiao4903-lang/Marco-economic`
**Task**: Marco Issue #4 / `REQ-MARCO-EXTDATA-W1-20260905.md`
**Gate**: **CONDITIONAL** — the owner/provider routes, parser gates, temporal
metadata plumbing, and isolated derived diagnostics are implemented. Cross #37
has accepted the source-definition/PIT evidence baseline, but real-data
readiness and formal production admission remain **DATA_BLOCKED** pending the
remaining acceptance and live-evidence gates.

## Baseline and scope

- Task document's known main: `f962e43f613bb6d8364aa61d385c46b00851940c`.
- Current `origin/main` before implementation:
  `1caad085f249d08f67f56702652e5a6997686a89`.
- The only intervening commit was `1caad08` (`docs: add W1 external macro
  data requirement`); the difference was task documentation only and had no
  semantic conflict with the implementation.
- Development branch: `feature/extdata-w1-macro-owner-spreads`, created from
  the current `origin/main`.
- Integration Contract v1 files and the signal/asset engines were not changed.
  No existing factor weight, structural meaning, fragility meaning, or
  allocation constraint was changed.

## M1 owner/provider baseline

The indicator registry is `config/indicators.yaml`; provider routing is
`config/data_sources.yaml`; adapter implementations are under
`src/macro_compass/data_sources/`. “Route configured” is not a live-data claim:
this branch did not promote an unverified endpoint, fixture, or inferred
publication timestamp to real-data readiness.

| canonical | registry path | provider route | live status | fallback | Cross duplicate / compatibility | action |
|---|---|---|---|---|---|---|
| `CN_PMI` | `config/indicators.yaml` (`CN_PMI`) | `data_sources.yaml` (`CN_PMI`): NBS `PMI_HEADLINE`; parser `nbs.py:parse_pmi_headline` | **CONDITIONAL** — route and offline parser are present; no live refresh accepted; #37 binds NBS semantics/release-calendar evidence | Wind manual export through the existing `config/wind_mapping.yaml` `PMI` mapping | No `CN_PMI` entry in the inspected Cross `MACRO_SERIES`; keep Cross consumers compatibility-only if later introduced | **KEEP/UPGRADE** |
| `CN_PPI_YOY` | `config/indicators.yaml` (`CN_PPI_YOY`) | `data_sources.yaml` (`CN_PPI_YOY`): AKShare access layer; schema gate `akshare_source.py:parse_monthly_macro_frame` | **CONDITIONAL** — YoY percent route is explicit; #37 binds NBS semantics/release-calendar evidence, but source health/live response is unverified | Wind manual route remains explicit; no index-level substitution | Cross `src/cross_asset/ingestion/evidence_shadow.py:MACRO_SERIES` contains legacy `CN_PPI`; it is not a second Marco canonical definition | **KEEP/UPGRADE** |
| `US_INITIAL_CLAIMS` | `config/indicators.yaml` (`US_INITIAL_CLAIMS`) | `data_sources.yaml` (`US_INITIAL_CLAIMS`): FRED provider code `ICSA` | **CONDITIONAL** — mapping/parser path is implemented; #37 binds week-ending and normal release timing, while live response and actual historical calendar remain unverified | None; provider failure is surfaced | Cross `src/cross_asset/providers/fred.py:SERIES` and `src/cross_asset/reports/research_admission.py:SERIES` retain an access/consumer compatibility mapping | **ADD/PROMOTE** |
| `US_CORE_CPI` | `config/indicators.yaml` (`US_CORE_CPI`) | `data_sources.yaml` (`US_CORE_CPI`): FRED provider code `CPILFESL`; raw index level | **CONDITIONAL** — route is explicit; #37 binds the raw index semantic, but live response and vintage/revision handling remain unverified | None; Core PCE is not an allowed fallback | Cross FRED provider code `CPILFESL` is an access compatibility entry; no separate Cross `US_CORE_CPI` production definition was found in the inspected paths | **ADD/PROMOTE** |

The nominal Treasury legs used by the second diagnostic are also explicit:

- Existing canonical `US_TREASURY_NOMINAL_YIELD_10Y` now routes to FRED
  `DGS10`, with the existing dedicated Wind mapping as manual fallback.
- New `US_TREASURY_NOMINAL_YIELD_2Y` routes to FRED `DGS2`. No guessed Wind
  header or semantic proxy was added.
- `US_10Y2Y_SPREAD` is derived from those two exact canonical IDs; it is not a
  second `US_10Y` series.

## Temporal and failure contract

The legacy `CANONICAL_COLUMNS` surface in
`src/macro_compass/ingestion/normalizer.py` is unchanged. Source adapters may
add the optional `observation_date`, `release_at`, and `available_at` columns
only when `FreshnessMeta.availability_rule` is explicitly configured.

For the W1 routes, the configured rule is
`end_of_day_after_lag`: the adapter uses the reference/observation date plus a
declared lag, then treats the end of that date in the configured IANA timezone
as a conservative availability boundary. The resulting `release_at` and
`available_at` are deterministic safety boundaries, not assertions that the
exact official release timestamp was observed. The observation date is never
used as an inferred publication timestamp. Cross #37 now supplies the accepted
source-definition and release/PIT evidence baseline; exact historical
calendar/vintage mapping and live source admission remain unverified here.

`src/macro_compass/ingestion/validator.py` rejects partial temporal metadata,
timezone-naive release/availability timestamps, mismatched observation dates,
and `available_at` values that precede the observation or release boundary.
`src/macro_compass/data_sources/updater.py` retains explicit `FAILED`,
`FALLBACK_USED`, and `MANUAL_REQUIRED` outcomes; a provider error does not
create a default value or silently switch definitions.

## PKG-06 derived diagnostics

`config/data_sources.yaml:derived_series` declares both diagnostics with
`owner: MARCO` and `production_enabled: false`.

- `CN_DR007_SPREAD` is implemented in
  `src/macro_compass/data_sources/derived.py:derive_cn_dr007_spread`.
  It selects the latest policy observation whose `available_at` is no later
  than the relevant decision time and whose effective observation date is not
  in the future. Missing policy history, missing DR007 rows, temporal
  violations, or unit mismatch fail closed. It does not alter D1, weights, or
  allocation.
- `US_10Y2Y_SPREAD` is implemented in
  `src/macro_compass/data_sources/derived.py:derive_us_10y2y_spread`. It uses
  an exact-date inner join of the two nominal Treasury legs, requires both
  legs to pass the same cutoff, and does not use latest-value or nearest-date
  filling. It is a curve-state diagnostic, not a short-cycle trigger.

Neither diagnostic is inserted into `config/signals.yaml`, the factor engine,
the asset allocator, or the Integration Contract v1 JSON surface.

## Evidence and remaining blockers

Offline acceptance is in `tests/data_sources/test_w1_macro.py` and covers
registry mapping, NBS PMI headline parsing, malformed PPI schema, conservative
temporal boundaries, FRED mapping, policy publication before/after cutoffs,
exact-date Treasury joining, missing overlap, and unit mismatch. The tests do
not establish provider entitlement, endpoint stability, exact historical
release/vintage mapping, holiday exceptions, or real-data coverage. Cross #37's
evidence package is accepted as the source-definition/PIT baseline; the
remaining live and formal-admission gates keep this branch conditional.
