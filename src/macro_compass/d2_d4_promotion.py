"""Previewable, explicitly authorized promotion for the D2/D4 Wind candidates.

The module is intentionally narrow: only the two named candidate series may be
promoted, and only the historical placeholder window is replaced.  Validation
is completed before any file is opened for writing.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from macro_compass.storage.canonical_store import read_canonical
from macro_compass.storage.duckdb_store import rebuild_duckdb_from_canonical

TARGETS = {
    "CN_TSF_TOTAL_WIND_CANDIDATE": "CN_TSF_TOTAL",
    "CN_GOV_BOND_FINANCING_WIND_CANDIDATE": "CN_GOV_BOND_FINANCING",
}
START = pd.Timestamp("2018-01-31")
HISTORY_END = pd.Timestamp("2026-03-31")
TAIL_START = pd.Timestamp("2026-04-01")
ROUNDING_LIMIT_BN = 10.0
RESOLUTION_AWARE_GATE_ID = "public_cumulative_report_resolution_aware"
STRICT_LIVE_PBC_GATE_ID = "strict_live_pbc_tail_comparability"
STRICT_LIVE_PBC_ABS_LIMIT_BN = 0.1
STRICT_LIVE_PBC_REL_LIMIT = 0.005


class PromotionError(ValueError):
    """Raised when a promotion gate fails; no data has been written."""


@dataclass
class PromotionPlan:
    rows: pd.DataFrame
    checks: dict[str, object]
    report: dict[str, object]


def _month_ends(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start, end, freq="ME")


def _load_pbc_reported(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise PromotionError(f"PBC reported candidate file not found: {path}")
    frame = pd.read_csv(path)
    required = {"series_id", "date", "value", "unit", "frequency", "source"}
    missing = required - set(frame.columns)
    if missing:
        raise PromotionError(f"PBC reported candidate missing columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def build_promotion_plan(
    canonical: pd.DataFrame,
    pbc_reported: pd.DataFrame,
) -> PromotionPlan:
    """Validate candidate, placeholder, tail and rounding gates in memory."""
    allowed = set(TARGETS)
    candidate_ids = set(canonical.loc[canonical["series_id"].isin(allowed), "series_id"])
    if candidate_ids != allowed:
        raise PromotionError(f"candidate input must contain exactly the two allowed series: {sorted(allowed)}")

    expected_dates = _month_ends(START, HISTORY_END)
    replacement = []
    checks: dict[str, object] = {
        "selected_release_gate": RESOLUTION_AWARE_GATE_ID,
        "rounding_limit_bn_cny": ROUNDING_LIMIT_BN,
        # This is deliberately metadata-only here.  The strict gate compares
        # the live PBC tail and remains an independent raw-report acceptance
        # gate; it is not silently substituted by the public-report gate.
        "independent_strict_live_pbc_gate": {
            "id": STRICT_LIVE_PBC_GATE_ID,
            "status": "SEPARATE_NOT_EVALUATED",
            "min_common_months": 3,
            "requires_full_tail_coverage": True,
            "absolute_limit_bn_cny": STRICT_LIVE_PBC_ABS_LIMIT_BN,
            "relative_limit": STRICT_LIVE_PBC_REL_LIMIT,
        },
        "series": {},
    }
    for candidate_id, production_id in TARGETS.items():
        cand = canonical[canonical["series_id"] == candidate_id].copy()
        cand["date"] = pd.to_datetime(cand["date"], errors="coerce")
        hist = cand[(cand["date"] >= START) & (cand["date"] <= HISTORY_END)]
        if hist["date"].duplicated().any() or set(hist["date"]) != set(expected_dates):
            raise PromotionError(f"{candidate_id} is not continuous across 2018-01..2026-03")
        if not hist["unit"].eq("bn_cny").all() or not hist["frequency"].eq("monthly").all():
            raise PromotionError(f"{candidate_id} must be monthly bn_cny")

        prod = canonical[canonical["series_id"] == production_id].copy()
        prod["date"] = pd.to_datetime(prod["date"], errors="coerce")
        old = prod[(prod["date"] >= START) & (prod["date"] <= HISTORY_END)]
        if old.empty or not old["source"].eq("WIND_PLACEHOLDER").all():
            raise PromotionError(f"{production_id} historical window is not entirely WIND_PLACEHOLDER")
        tail = prod[prod["date"] >= TAIL_START]
        if tail.empty or not tail["source"].eq("PBC").all():
            raise PromotionError(f"{production_id} production tail must remain PBC sourced")

        pbc_id = production_id + "_PBC_REPORTED_CANDIDATE"
        reported = pbc_reported[pbc_reported["series_id"] == pbc_id].copy()
        reported["date"] = pd.to_datetime(reported["date"], errors="coerce")
        # The reported comparison uses the candidate's live tail (2026-04..07),
        # while the replacement itself is restricted to the historical window.
        joined = cand.set_index("date")["value"].rename("wind").to_frame().join(
            reported.set_index("date")["value"].rename("reported"), how="inner"
        )
        if len(joined) < 3 or not reported["unit"].eq("bn_cny").all():
            raise PromotionError(f"{production_id} lacks the required reported-candidate gate")
        absolute = (joined["wind"] - joined["reported"]).abs()
        if not (absolute <= ROUNDING_LIMIT_BN).all():
            raise PromotionError(f"{production_id} fails the reported-candidate rounding gate")
        checks["series"][production_id] = {
            "historical_rows": int(len(hist)),
            "tail_rows_preserved": int(len(tail)),
            "reported_overlap_rows": int(len(joined)),
            "max_absolute_diff_bn_cny": float(absolute.max()),
            "status": "PASS",
        }
        promoted = hist.copy()
        promoted["series_id"] = production_id
        replacement.append(promoted)

    rows = pd.concat(replacement, ignore_index=True)
    report = {
        "status": "READY" if checks["series"] else "BLOCKED",
        "mode": "dry-run",
        "candidate_series": sorted(TARGETS),
        "production_series": sorted(TARGETS.values()),
        "historical_window": [START.strftime("%Y-%m-%d"), HISTORY_END.strftime("%Y-%m-%d")],
        "tail_rule": "preserve production rows from 2026-04 onward when source is PBC",
        "release_gate_policy": {
            "status": "CONDITIONALLY_ACCEPTED",
            "selected_gate": RESOLUTION_AWARE_GATE_ID,
            "scope": "public cumulative report differencing for the released historical splice",
            "strict_live_pbc_gate": "independent_raw_report_acceptance_gate",
        },
        "checks": checks,
        "downstream_regression": {
            "summary": "D2/D4 production IDs unchanged; only placeholder history is planned for replacement",
            "routes_unchanged": True,
            "candidate_series_retained": True,
            "pbc_tail_overwritten": False,
        },
    }
    return PromotionPlan(rows=rows, checks=checks, report=report)


def apply_promotion(
    plan: PromotionPlan,
    canonical_path: Path,
    db_path: Path,
    registry: dict,
    backup_dir: Path,
) -> dict[str, object]:
    """Apply a validated plan with a recoverable local backup and DB rebuild."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / "macro.duckdb"
    parquet_backup = backup_dir / "macro.parquet"
    shutil.copy2(canonical_path, parquet_backup)
    if db_path.exists():
        shutil.copy2(db_path, db_backup)
    try:
        existing = pd.read_parquet(canonical_path)
        # Parquet readers may materialize date-only columns as ``datetime.date``
        # while the validated plan uses pandas ``Timestamp`` values.  Normalize
        # both sides before concatenation/sorting so the atomic replacement does
        # not depend on the physical date representation.
        existing["date"] = pd.to_datetime(existing["date"], errors="raise")
        dates = pd.to_datetime(existing["date"])
        ids = set(plan.rows["series_id"])
        keep = ~(
            existing["series_id"].isin(ids)
            & dates.between(START, HISTORY_END)
        )
        merged = pd.concat([existing.loc[keep], plan.rows], ignore_index=True)
        merged = merged.sort_values(["series_id", "date"]).drop_duplicates(["series_id", "date"], keep="last")
        tmp = canonical_path.with_suffix(".promotion.tmp.parquet")
        merged.to_parquet(tmp, index=False)
        tmp.replace(canonical_path)
        counts = rebuild_duckdb_from_canonical(registry, db_path=db_path)
    except Exception:
        shutil.copy2(parquet_backup, canonical_path)
        if db_backup.exists():
            shutil.copy2(db_backup, db_path)
        raise
    return {"status": "APPLIED", "backup_dir": str(backup_dir), "duckdb": counts}


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
