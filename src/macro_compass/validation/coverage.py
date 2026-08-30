"""Historical Coverage Matrix + backfill gap assessment (V2.5, task 60 section 1-2).

Builds the per-Core-Signal matrix required by the owner plan (spec 47 section
29): for every core signal - and its input series - record earliest
observation, comparable-history start, source, breakpoints, revision risk and
minimum validation start.

Only concrete, current data is used: earliest/validity dates come from the live
canonical series (``series``) and the signal's first computable PIT score
(``first_score_dates``). Breakpoint and revision-risk entries below are the
DECLARED human-maintained record, cross-referenced to the project docs - a
series is never silently "joined" into one continuous history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import pandas as pd


@dataclass
class SeriesRow:
    """One input series of a core signal."""

    series_id: str
    role: str
    earliest_observation: Optional[pd.Timestamp]
    provider: str
    update_policy_mode: str
    revision_risk: str
    note: str


@dataclass
class SignalRow:
    signal_id: str
    name: str
    factor: str
    mechanism: str
    inputs: list[SeriesRow]
    comparable_history_start: Optional[pd.Timestamp]  # = first computable PIT score
    minimum_validation_start: Optional[pd.Timestamp]
    breakpoints: list[str]


# ---- Declared, documented breakpoints (authoritative human-maintained) ------
# These come from the V1.6A handoff / signals.yaml commentary / 47 & 55 specs.
BREAKPOINTS: dict[str, list[str]] = {
    "CHN_IND_PROD_INDEX": [
        "OECD SDMX volume index carries base-rebasing steps that corrupt yoy(12); "
        "declared G3 FALLBACK only (signals.yaml G3, V1.6A)",
    ],
    "CHN_RETAIL_SALES_INDEX": [
        "OECD SDMX volume index; base-rebasing; declared G3 fallback only",
    ],
    "US_REAL_YIELD_10Y": [
        "source switch Treasury par-real-yield (primary, v0.4c) vs FRED DFII10 is "
        "gated on scripts/overlap_check.py >=60 common days; currently BLOCKED by "
        "FRED network - do NOT splice rows until overlap passes",
    ],
    "CN_AAA_CREDIT_SPREAD": [
        "derived series: AAA MTN 3Y minus CGB 3Y, both legs same official curve "
        "table (history from 2006-12-25); composite definition fixed",
    ],
    "CN_PRIVATE_TSF_YOY": [
        "DERIVED series (AFRE stock - gov bond stock growth); published-rounding "
        "precision ~+/-0.1pp (data_sources.yaml)",
    ],
    "CN_M2_YOY": ["served via AKShare access layer (surrogate of official PBOC M2)"],
    "CN_CPI_YOY": ["served via AKShare access layer; I1 FALLBACK leg (core CPI keeps own id)"],
    "G3": [
        "2026-08 G0 owner switch: live inputs OECD volume indices -> NBS YoY percent "
        "(CN_IND_PROD_YOY / CN_RETAIL_SALES_YOY); unit change (index vs %) means "
        "pre/post not numerically continuous",
    ],
    "CN_PROPERTY_SALES_AREA": ["NBS publishes only year-to-date CUMULATIVE YoY; monthly basis is derived"],
    "CN_PROPERTY_SALES_VALUE": ["NBS publishes only year-to-date CUMULATIVE YoY; monthly basis is derived"],
    "CN_POLICY_RATE_7D": [
        "event/step series (flat between cuts); canonical history starts 2024; "
        "legacy committed manual step file is bootstrap-only",
    ],
}

# ---- Declared revision-risk overrides (else derived from update_policy) -----
REVISION_OVERRIDES: dict[str, str] = {
    "US_GSCPI": "HIGH",   # PCA model output; every release revises whole history (data_sources.yaml)
    "CHN_EXPORT_YOY": "MEDIUM",  # OECD revises recent growth rates
    "CN_TSF_TOTAL": "MEDIUM",  # PBOC restates cumulative increments
    "CN_GOV_BOND_FINANCING": "MEDIUM",
    "CN_POLICY_RATE_7D": "LOW",  # step changes, not revised
}

_MODE_TO_RISK = {"full_refresh": "HIGH", "replace_window": "MEDIUM", "append": "LOW"}


def _provider_label(routes, series_id: str) -> str:
    r = routes.series.get(series_id)
    if r is None:
        return "no-route"
    prim = str(r.primary or "")
    fb = str(r.fallback or "")
    return prim + (f"+{fb}" if fb else "")


def _row_note(series_id: str) -> str:
    return "; ".join(BREAKPOINTS.get(series_id, []))


def build_coverage_matrix(
    registry,
    data_sources_cfg,
    macro_config,
    series: Mapping[str, pd.Series],
    first_score_dates: Mapping[str, pd.Timestamp],
) -> list[SignalRow]:
    """Assemble the coverage matrix over all 15 core signals.

    ``first_score_dates`` maps signal_id -> its first computable PIT score date
    (computed by the report once, from the live signal frames). Values may be
    None for signals with no computable history yet.
    """
    rows: list[SignalRow] = []
    for sid, spec in registry.core.items():
        input_rows: list[SeriesRow] = []
        for inp in spec.inputs:
            ser = series.get(inp.series_id)
            earliest = None
            if ser is not None and len(ser):
                earliest = pd.Timestamp(ser.index.min())
            srid = inp.series_id
            policy_mode = "n/a"
            r = data_sources_cfg.series.get(srid)
            if r is not None:
                up = getattr(r, "update_policy", None)
                if hasattr(up, "mode"):
                    policy_mode = str(up.mode)
                elif isinstance(up, dict):
                    policy_mode = str(up.get("mode", "n/a"))
            risk = REVISION_OVERRIDES.get(srid, _MODE_TO_RISK.get(policy_mode, "MEDIUM"))
            input_rows.append(
                SeriesRow(
                    series_id=srid,
                    role=str(inp.role),
                    earliest_observation=earliest,
                    provider=_provider_label(data_sources_cfg, srid),
                    update_policy_mode=policy_mode,
                    revision_risk=risk,
                    note=_row_note(srid),
                )
            )
        start = first_score_dates.get(sid)
        bp = list(BREAKPOINTS.get(sid, BREAKPOINTS.get(str(spec.layer), [])))
        rows.append(
            SignalRow(
                signal_id=sid,
                name=spec.name,
                factor=spec.factor,
                mechanism=(spec.mechanism or ""),
                inputs=input_rows,
                comparable_history_start=start,
                minimum_validation_start=start,
                breakpoints=bp,
            )
        )
    return rows


def first_score_dates(
    computations: Mapping[str, object],
) -> dict[str, Optional[pd.Timestamp]]:
    """First date each core signal produced a PIT score (first non-null score row
    of its frozen frame - valid because every transform is backward-looking)."""
    out: dict[str, Optional[pd.Timestamp]] = {}
    for sid, comp in computations.items():
        frame = comp.frame
        if frame is None or frame.empty:
            out[sid] = None
            continue
        scored = frame[frame["score"].notna()]
        out[sid] = pd.Timestamp(scored["date"].min()) if not scored.empty else None
    return out


# ---- Backfill gap assessment (task 60 section 2) ---------------------------
# The list below is the declared Wind one-shot backfill candidate set (spec 47
# section 30), tagged against the CURRENT coverage so the report tells the user
# exactly which are still short and why.
BACKFILL_SHORTFALL_CAL = 36  # months; a comparable history shorter than this is flagged

BACKFILL_CANDIDATES: dict[str, dict] = {
    "CN_TSF_TOTAL": {"note": "D2 private credit impulse (Total TSF Flow)", "target_months": 120},
    "CN_GOV_BOND_FINANCING": {"note": "D2/D4 fiscal leg (Gov Bond Financing Flow)", "target_months": 120},
    "CHN_PMI_NEW_ORDERS": {"note": "G2 PMI new orders", "target_months": 120},
    "CN_CORE_CPI_YOY": {"note": "I1 core CPI history", "target_months": 120},
    "CHN_PMI_INPUT_PRICE": {"note": "I3 PMI input price history", "target_months": 120},
    "CN_PROPERTY_SALES_AREA": {"note": "G4 property area history", "target_months": 120},
    "CN_PROPERTY_SALES_VALUE": {"note": "G4 property value history", "target_months": 120},
    "CN_POLICY_RATE_7D": {"note": "D1 funding-condition policy leg (history)", "target_months": 120},
    "USD_BROAD": {"note": "X2 broad USD history (FRED DTWEXBGS / H.10)", "target_months": 120},
    "GOLD": {"note": "GOLD spot history for the real-yield decoupling regime test", "target_months": 120},
}


def assess_backfill_gaps(
    series: Mapping[str, pd.Series],
    today: pd.Timestamp,
) -> list[dict]:
    """Evaluate each backfill candidate against its live coverage; emit rows for
    the ones still short, with the observed coverage and the recommended export
    window. Pure data read - never a fetch."""
    today = pd.Timestamp(today)
    gaps: list[dict] = []
    for sid, meta in BACKFILL_CANDIDATES.items():
        ser = series.get(sid)
        if ser is None or not len(ser):
            gaps.append(
                {
                    "series_id": sid, "note": meta["note"],
                    "observed_months": 0, "target_months": meta["target_months"],
                    "recommended": meta["note"],
                }
            )
            continue
        n_months = (today - pd.Timestamp(ser.index.min())).days / 30.44
        if n_months < meta["target_months"]:
            gaps.append(
                {
                    "series_id": sid, "note": meta["note"],
                    "observed_months": round(n_months, 1),
                    "target_months": meta["target_months"],
                    "recommended": meta["note"],
                }
            )
    return gaps