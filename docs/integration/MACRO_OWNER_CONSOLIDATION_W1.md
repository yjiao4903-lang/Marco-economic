# Marco Macro Owner Consolidation — W1

**As-of**: 2026-09-05
**Status**: **CONDITIONAL / Marco capability complete; Cross migration pending**

This note records the boundary between the Marco macro-production owner and
Cross's existing compatibility consumers. It does not change the Integration
Contract v1 schema, add JSON fields, delete Cross ingestion, or authorize a
merge. The source/PIT questions that still block a real-data readiness claim
are tracked in Cross Issue #37.

## Canonical ownership map

| Marco canonical ID | Marco production route | Cross current ID/path | Migration treatment |
|---|---|---|---|
| `CN_PMI` | NBS headline PMI, with the existing Wind `PMI` mapping as manual fallback | No `CN_PMI` entry in the inspected Cross macro shadow list | Future Cross consumption should request Marco `CN_PMI`; do not create `CN_NBS_PMI_MFG` |
| `CN_PPI_YOY` | AKShare access layer for official NBS PPI YoY; explicit Wind fallback | Legacy `CN_PPI` in `src/cross_asset/ingestion/evidence_shadow.py:MACRO_SERIES` | Keep `CN_PPI` as a compatibility input until a separately reviewed consumer migration; it is not a second Marco owner |
| `US_INITIAL_CLAIMS` | FRED `ICSA` mapping | `US_INITIAL_CLAIMS` in `src/cross_asset/providers/fred.py:SERIES` and research-admission mapping | Keep Cross access compatibility; future production consumption points to Marco's canonical series |
| `US_CORE_CPI` | FRED `CPILFESL`, raw index level | Cross FRED provider includes `CPILFESL` as a provider code, but no separate inspected `US_CORE_CPI` production definition | Do not introduce Core PCE or another CPI alias; migrate by consumer contract when approved |
| `CN_DR007` / `CN_POLICY_RATE_7D` | Existing Marco legs; `CN_DR007_SPREAD` is Marco's diagnostic | Legacy `CN_DR007` remains in Cross macro compatibility inputs | Keep existing Cross path until a reviewed consumer change; do not duplicate the spread definition in Cross |
| `US_10Y2Y_SPREAD` | Marco derives from existing nominal 10Y plus FRED DGS2 2Y | No Cross production spread is added in this W1 | Future consumer only; no short-cycle allocation behavior |

The Cross IDs above are compatibility surfaces, not permission to delete or
rewrite Cross code in this Marco PR. A future migration must establish the
consumer's required fields and PIT semantics before replacing an ID.

## Target consumer path

The intended path is:

```text
approved Marco source route
        -> Marco canonical series + causal temporal metadata
        -> reviewed Cross consumer adapter / future contract proposal
        -> existing Integration Contract v1 objects only
```

This W1 branch stops at the Marco capability boundary. The four new macro
inputs and two diagnostics are not exported into the existing JSON payload.
If a future consumer needs them, it requires a separate contract proposal and
WEB-CONTROL review; no field is added by inference.

## What remains Cross Market State

Cross remains the owner of market-state and positioning work, including the
Risk Stress inputs (VIX/VIX3M, HY OAS, and the separately governed BAA10Y
shadow proxy), CFTC positioning, China leverage positioning, and related
market-state reporting. Those inputs must not be republished as Marco macro
canonical series by this task. BAA10Y and HY OAS remain separate definitions;
positioning remains a diagnostic and is not converted into directional alpha.

## Explicit no-scope confirmation

- Integration Contract v1 schema and exporter surface are unchanged.
- Existing factor weights, structural/fragility semantics, strategic weights,
  and allocation constraints are unchanged.
- Cross legacy compatibility routes are not deleted.
- No fixture is treated as real data, and no source/PIT uncertainty is resolved
  by guessing.
