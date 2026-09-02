# Marco → cross-asset Integration Contract v1

## Purpose

Marco remains the Macro / Fundamental / Structural / Regime Engine. Cross-asset
consumes a narrow file contract and does not depend on Marco's internal signal
ids (`G1`, `D2`, etc.). This is an integration boundary, not a repository merge.

Marco exports exactly four JSON files:

- `macro_snapshot.json`
- `structural_snapshot.json`
- `fundamental_asset_view.json`
- `integration_manifest.json`

Schema version is `1.0`.

## Run

```powershell
python scripts/export_cross_asset_snapshot.py `
  --today 2026-09-02 `
  --output-dir artifacts/integration/latest
```

The exporter is read-only with respect to canonical Parquet and DuckDB. It runs
the existing Marco engines from a fixed `--today`. Synthetic rows remain
excluded unless the explicitly test-only `--allow-synthetic` flag is supplied.

## Contract rules

### Macro

The public factor surface is:

- `growth`
- `inflation`
- `domestic_financial`
- `global_financial`
- `fiscal`

Marco currently computes the first four factors. Until a formal fiscal factor is
implemented, `fiscal` is exported as `status=UNAVAILABLE` with `score`,
`confidence`, and `coverage` all `null`. Missing values are never zero-filled.

The regime is Marco's existing Growth × Inflation regime. Regime confidence is
the lower of Growth and Inflation factor confidence when both are computable.

### Structural

`property_fragility` is the already fragility-aligned S3 composite. Its public
scale is fixed:

- `0 = lower fragility`
- `1 = higher fragility`

The integration layer does not infer or reverse S3 signs again.

`structural_risk` is a deliberately simple integration diagnostic: the
equal-weight mean of the available S1/S2/S3 fragility percentiles. Its
confidence discounts both component availability and each reading's input /
history coverage. It is `DEGRADED` when fewer than all three fully READY
components are usable. This diagnostic is not fitted, is not an expected-return
model, and never enters the Fundamental Asset Score.

Stale or missing structural readings are exported as `NO_SIGNAL`/`UNAVAILABLE`
rather than carrying a stale numeric score.

### Fundamental asset view

Canonical allocatable ids, in stable order:

```text
CN_EQ
HK_EQ
US_EQ
CN_GOV_BOND
CN_CREDIT
GOLD
COMMODITY
CASH
```

Boundary aliases:

```text
CN_EQUITY            -> CN_EQ
HK_EQUITY            -> HK_EQ
INDUSTRIAL_COMMODITY -> COMMODITY
CN_BOND               -> CN_GOV_BOND
```

The first three aliases cover Marco's current internal ids; `CN_BOND` is
accepted for compatibility with the cross-asset naming boundary.

Marco currently has no formal `US_EQ` or `CASH` fundamental asset model, so both
are emitted as `UNAVAILABLE` with null score/confidence/coverage.

`CNY` is not an allocatable asset in v1. Its existing Marco fundamental read is
preserved under `fx_views`.

`fundamental_score` is the existing Marco Asset Compass score built from
declared macro-factor priors. Market price/trend/confirmation is intentionally
not passed into the exporter. `structural` contribution is explicitly `null`.

### Manifest and determinism

`integration_manifest.json` records:

- schema version
- generation timestamp
- as-of and data cutoff
- Marco package/model version
- Marco Git commit
- deterministic config hash
- SHA-256 of the exact bytes of each of the three data files

The JSON writer uses stable key ordering and formatting. With identical inputs
and a fixed `generated_at`, all four files are byte-for-byte deterministic.
Under normal runs, only `generated_at` is expected to change when the underlying
state is unchanged.

The config hash covers the model dependencies used by this export:

```text
config/indicators.yaml
config/data_sources.yaml
config/signals.yaml
config/macro.yaml
config/assets.yaml
config/structural.yaml
```

## Failure semantics

The live CLI fails loudly if there is no canonical data on or before the
requested as-of date, if the Git commit cannot be resolved, if a required config
file is missing, or if an unknown asset/status reaches the integration boundary.

At the contract adapter level, unavailable supported dimensions are represented
explicitly with null values and a non-READY status; they are never silently
converted to zero.
