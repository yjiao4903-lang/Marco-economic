"""Shadow Operation metrics - read-only directional-consistency monitor.

Declared purpose (V4.6 handoff -> Shadow Operation, MASTER SPEC section 15 /
task 86): during the 3-6 month observation phase NO model / weight /
threshold / signal may be changed. This module records, per month-end, the
declared Asset View (tailwind / headwind / neutral derived from the FROZEN
0.15 threshold) and - once the canonical market proxy has advanced far enough -
attributes the realized 1m/3m forward-return proxy and counts directional hits.

Hit rule (consistent with validation's sign-aligned proxies): for non-neutral
views, hit = sign(score) == sign(fwd), i.e. tailwind expects fwd>0 and headwind
expects fwd<0. Neutral views make no directional claim and are not counted.

Isolation contract (identical to validation):
- reads frozen V2/V1.5 outputs + canonical; never writes to canonical;
- synthetic is excluded upstream (allow_synthetic=False, enforced by caller);
- the threshold is READ from assets.yaml, never fitted or changed here.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import platform
import subprocess

import numpy as np
import pandas as pd

VIEW_TAILWIND = "tailwind"
VIEW_HEADWIND = "headwind"
VIEW_NEUTRAL = "neutral"

SNAPSHOT_COLUMNS = [
    "asof", "date", "asset", "score", "view", "coverage",
    "fwd_1m", "fwd_3m", "hit_1m", "hit_3m",
]

# V2 governance storage.  These are deliberately separate from the legacy
# metrics frame above: a decision snapshot is immutable and never contains an
# outcome or forward-return field.
DECISION_SNAPSHOT_COLUMNS = [
    "snapshot_id", "as_of", "decision_date", "asset", "score", "view", "coverage",
    "lifecycle_status", "config_hash", "data_hash", "git_hash",
    "runtime_metadata",
]
OUTCOME_OBSERVATION_COLUMNS = [
    "outcome_id", "snapshot_id", "observed_as_of", "horizon",
    "forward_return", "observation_status",
]
FORBIDDEN_SNAPSHOT_FIELDS = {"outcome", "fwd_1m", "fwd_3m", "forward_return",
                             "hit_1m", "hit_3m", "hit", "outcome_observation"}


def content_hash(value) -> str:
    """Stable SHA-256 for a small config/data manifest (not raw data export)."""
    if isinstance(value, pd.DataFrame):
        value = value.sort_index(axis=1).sort_index().to_json(date_format="iso")
    elif isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        value = str(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_hash(project_root: Path | None = None) -> str:
    """Return the current commit hash, or ``unknown`` outside a git checkout."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(project_root or Path.cwd()), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def runtime_metadata() -> str:
    return json.dumps({"python": platform.python_version(), "platform": platform.platform()},
                      sort_keys=True)


def decision_snapshot_frame(asset_scores: pd.DataFrame, coverage: pd.DataFrame,
                            threshold: float = 0.15, *, as_of=None,
                            config_hash: str = "", data_hash: str = "",
                            git_hash_value: str = "", lifecycle_status: str = "READY",
                            runtime_metadata_value: str | None = None) -> pd.DataFrame:
    """Create immutable decisions only; no outcome columns are permitted."""
    # ``decision_date`` is the month-end/quarter-end *period label* for the
    # score; ``as_of`` is the actual decision/run date.  An open period can
    # therefore never be recorded as a decision before its label is reached.
    as_of_date = pd.Timestamp(as_of or pd.Timestamp.now()).date()
    as_of = as_of_date.isoformat()
    rows = []
    for asset in asset_scores.columns:
        cov = coverage[asset] if asset in coverage.columns else pd.Series(dtype=float)
        for date, score in asset_scores[asset].items():
            if pd.isna(score):
                continue
            value = cov.get(date, np.nan)
            decision_date_value = pd.Timestamp(date).date()
            if decision_date_value > as_of_date:
                continue
            decision_date = decision_date_value.isoformat()
            rows.append({"snapshot_id": content_hash({"as_of": as_of, "date": decision_date, "asset": asset, "score": float(score)}),
                         "as_of": as_of, "decision_date": decision_date, "asset": asset, "score": float(score),
                         "view": view_of(score, threshold),
                         "coverage": float(value) if not pd.isna(value) else np.nan,
                         "lifecycle_status": lifecycle_status,
                         "config_hash": config_hash, "data_hash": data_hash,
                         "git_hash": git_hash_value,
                         "runtime_metadata": runtime_metadata_value or runtime_metadata()})
    return pd.DataFrame(rows, columns=DECISION_SNAPSHOT_COLUMNS)


def outcome_observation_frame(decisions: pd.DataFrame, forward_returns: dict,
                              *, observed_as_of=None) -> pd.DataFrame:
    """Create append-only, maturity-gated observations linked by snapshot_id.

    A forward-return value is not recordable merely because it is present in an
    in-memory panel: the observation date must have reached the corresponding
    month-end horizon.  This keeps a replay from accidentally consuming a
    future value when a caller supplies a panel with a wider date range.
    """
    observed = pd.Timestamp(observed_as_of or pd.Timestamp.now()).date().isoformat()
    rows = []
    for _, row in decisions.iterrows():
        fdf = forward_returns.get(row["asset"])
        if fdf is None:
            continue
        for horizon in ("1m", "3m"):
            maturity_date = (
                pd.Timestamp(row["decision_date"]) +
                pd.DateOffset(months=int(horizon[0])) + pd.offsets.MonthEnd(0)
            ).date()
            if pd.Timestamp(observed).date() < maturity_date:
                continue
            col = f"fwd_{horizon}"
            if col not in fdf.columns:
                continue
            # IDs are generated from the decision's stable identity and horizon.
            try:
                value = fdf.loc[pd.Timestamp(row["decision_date"]), col]
            except (KeyError, TypeError):
                value = np.nan
            if pd.isna(value):
                continue
            oid = content_hash({"snapshot_id": row["snapshot_id"], "horizon": horizon,
                                "observed_as_of": observed})
            rows.append({"outcome_id": oid, "snapshot_id": row["snapshot_id"],
                         "observed_as_of": observed, "horizon": horizon,
                         "forward_return": float(value), "observation_status": "READY"})
    return pd.DataFrame(rows, columns=OUTCOME_OBSERVATION_COLUMNS)


def validate_decision_snapshots(frame: pd.DataFrame) -> dict:
    """Read-only replay/schema gate for the decision side of Shadow storage."""
    columns = set(frame.columns)
    forbidden = sorted(columns & FORBIDDEN_SNAPSHOT_FIELDS)
    missing = sorted(set(DECISION_SNAPSHOT_COLUMNS) - columns)
    ids_ok = "snapshot_id" in columns and frame["snapshot_id"].notna().all()
    # Validate the temporal contract independently of the caller's ``today``:
    # each row carries the actual run date (as_of), so persisted replays can
    # reject a future period label without trusting current wall-clock time.
    future_count = 0
    invalid_date_count = 0
    if {"as_of", "decision_date"}.issubset(columns) and not frame.empty:
        asof_dates = pd.to_datetime(frame["as_of"], errors="coerce")
        decision_dates = pd.to_datetime(frame["decision_date"], errors="coerce")
        invalid_date_count = int((asof_dates.isna() | decision_dates.isna()).sum())
        future_count = int((decision_dates > asof_dates).fillna(False).sum())
    valid = (not forbidden and not missing and bool(ids_ok) and
             invalid_date_count == 0 and future_count == 0)
    return {"valid": valid,
            "forbidden_fields": forbidden, "missing_fields": missing,
            "future_decision_count": future_count,
            "invalid_date_count": invalid_date_count,
            "snapshot_count": int(len(frame))}


def replay_gate(decisions: pd.DataFrame, outcomes: pd.DataFrame | None = None) -> dict:
    """Read-only integrity gate for persisted Shadow files.

    It checks the separation boundary and that every observation points to an
    existing decision. It intentionally does not score returns or calibrate
    probabilities.
    """
    result = validate_decision_snapshots(decisions)
    if outcomes is None:
        return result
    missing_outcome = sorted(set(OUTCOME_OBSERVATION_COLUMNS) - set(outcomes.columns))
    outcome_forbidden = sorted(set(outcomes.columns) & {"score", "view", "coverage"})
    known = set(decisions.get("snapshot_id", pd.Series(dtype=str)))
    dangling = int((~outcomes.get("snapshot_id", pd.Series(dtype=str)).isin(known)).sum())
    bad_horizon = int((~outcomes.get("horizon", pd.Series(dtype=str)).isin(["1m", "3m"])).sum())
    result.update({"missing_outcome_fields": missing_outcome,
                   "outcome_forbidden_fields": outcome_forbidden,
                   "invalid_horizon_count": bad_horizon,
                   "dangling_outcome_count": dangling})
    result["valid"] = (result["valid"] and not missing_outcome and
                        not outcome_forbidden and bad_horizon == 0 and dangling == 0)
    return result


def append_unique(path: Path, frame: pd.DataFrame, key: str) -> pd.DataFrame:
    """Append rows without updating existing records; safe for replay checks."""
    incoming = frame.copy()
    if path.exists():
        existing = pd.read_csv(path)
        incoming = pd.concat([existing, incoming], ignore_index=True)
    if key in incoming.columns:
        incoming = incoming.drop_duplicates(key, keep="first")
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(path, index=False, encoding="utf-8-sig")
    return incoming


def maturity_counts(decisions: pd.DataFrame, outcomes: pd.DataFrame) -> dict:
    """Return storage/maturity counts without scoring or calibration."""
    ids = set(outcomes.loc[outcomes["horizon"] == "1m", "snapshot_id"]) if not outcomes.empty else set()
    ids3 = set(outcomes.loc[outcomes["horizon"] == "3m", "snapshot_id"]) if not outcomes.empty else set()
    return {"snapshot_count": int(len(decisions)), "matured_1m_count": len(ids),
            "matured_3m_count": len(ids3)}


def view_of(score: float, threshold: float) -> str:
    """Declared asset view from the frozen threshold (assets/engine.py semantics).

    ``""`` for missing scores (no view). tailwind when score >= +threshold,
    headwind when score <= -threshold, else neutral.
    """
    if pd.isna(score):
        return ""
    if abs(score) >= threshold:
        return VIEW_TAILWIND if score > 0 else VIEW_HEADWIND
    return VIEW_NEUTRAL


def asset_views(asset_scores: pd.DataFrame, threshold: float = 0.15) -> pd.DataFrame:
    """Per (date x asset) declared view label from PIT scores."""
    return asset_scores.apply(
        lambda col: col.map(lambda v: view_of(v, threshold))
    )


def _hit(score: float, view: str, fwd: float):
    """True/False directional hit; NaN when neutral or fwd not yet realizable."""
    if pd.isna(fwd) or view not in (VIEW_TAILWIND, VIEW_HEADWIND):
        return np.nan
    return bool((score > 0 and fwd > 0) or (score < 0 and fwd < 0))


def realized_frame(
    asset_scores: pd.DataFrame,
    forward_returns: dict,
    coverage: pd.DataFrame,
    threshold: float = 0.15,
) -> pd.DataFrame:
    """Long frame: one row per (date, asset) with declared view + realized proxies.

    Columns: date, asset, score, view, coverage, fwd_1m, fwd_3m, hit_1m, hit_3m.
    ``date`` is the month-end the score was declared (forward return is
    attributed to its START date, same alignment as validation).
    """
    rows: list[dict] = []
    for asset in asset_scores.columns:
        s = asset_scores[asset]
        fdf = forward_returns.get(asset)
        cov = coverage[asset] if asset in coverage.columns else pd.Series(
            np.nan, index=s.index
        )
        for d, score in s.items():
            if pd.isna(score):
                continue
            view = view_of(score, threshold)
            cov_val = cov.at[d] if (asset in coverage.columns and d in cov.index) else np.nan
            fwd1 = fwd3 = np.nan
            if fdf is not None and d in fdf.index:
                if "fwd_1m" in fdf.columns:
                    fwd1 = fdf.at[d, "fwd_1m"]
                if "fwd_3m" in fdf.columns:
                    fwd3 = fdf.at[d, "fwd_3m"]
            rows.append({
                "date": pd.Timestamp(d).date(),
                "asset": asset,
                "score": float(score),
                "view": view,
                "coverage": float(cov_val) if not pd.isna(cov_val) else np.nan,
                "fwd_1m": float(fwd1) if not pd.isna(fwd1) else np.nan,
                "fwd_3m": float(fwd3) if not pd.isna(fwd3) else np.nan,
                "hit_1m": _hit(score, view, fwd1),
                "hit_3m": _hit(score, view, fwd3),
            })
    return pd.DataFrame(rows, columns=[
        "date", "asset", "score", "view", "coverage",
        "fwd_1m", "fwd_3m", "hit_1m", "hit_3m",
    ])


def hit_summary(frame: pd.DataFrame, horizon: str = "3m") -> pd.DataFrame:
    """Per-asset directional-consistency summary over the frame (read-only).

    Counts only non-neutral views with a realized fwd. Columns: asset, horizon,
    n_views, n_hit, hit_rate, n_tailwind / n_tailwind_hit, n_headwind /
    n_headwind_hit, mean_fwd / mean_fwd_tailwind / mean_fwd_headwind.
    """
    fcol, hcol = f"fwd_{horizon}", f"hit_{horizon}"
    if fcol not in frame.columns or hcol not in frame.columns:
        return pd.DataFrame()
    out: list[dict] = []
    for asset, g in frame.groupby("asset", sort=True):
        g = g[
            g["view"].isin([VIEW_TAILWIND, VIEW_HEADWIND]) & g[fcol].notna()
        ]
        if g.empty:
            continue
        tw = g[g["view"] == VIEW_TAILWIND]
        hw = g[g["view"] == VIEW_HEADWIND]
        out.append({
            "asset": asset,
            "horizon": horizon,
            "n_views": int(len(g)),
            "n_hit": int(g[hcol].sum()),
            "hit_rate": float(g[hcol].mean()),
            "n_tailwind": int(len(tw)),
            "n_tailwind_hit": int(tw[hcol].sum()),
            "n_headwind": int(len(hw)),
            "n_headwind_hit": int(hw[hcol].sum()),
            "mean_fwd": float(g[fcol].mean()),
            "mean_fwd_tailwind": float(tw[fcol].mean()) if len(tw) else np.nan,
            "mean_fwd_headwind": float(hw[fcol].mean()) if len(hw) else np.nan,
        })
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_values("asset").reset_index(drop=True)


def upsert_snapshot(
    csv_path: Path,
    frame: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:
    """Merge a run's frame into the persistent CSV, keyed on (date, asset).

    New rows are appended with asof=<run date>; existing rows have their
    realized fwd/hit columns refreshed once the market proxy has advanced
    (their original asof is kept as first-observed date). Returns the merged
    frame. Read-only with respect to canonical.
    """
    frame = frame.copy()
    frame.insert(0, "asof", str(pd.Timestamp(asof).normalize().date()))
    frame["date"] = frame["date"].astype(str)
    merged = frame[SNAPSHOT_COLUMNS].copy()
    if csv_path.exists():
        old = pd.read_csv(csv_path)
        old["date"] = old["date"].astype(str)
        merged = pd.concat([old, merged], ignore_index=True)
    merged = merged.sort_values(["date", "asset", "asof"])
    first_asof = merged.groupby(["date", "asset"])["asof"].transform("first")
    merged = merged.drop_duplicates(["date", "asset"], keep="last")
    merged["asof"] = first_asof.reindex(merged.index).values
    merged = merged[SNAPSHOT_COLUMNS].sort_values(["date", "asset"]).reset_index(drop=True)
    return merged
