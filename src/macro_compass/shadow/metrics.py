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

import numpy as np
import pandas as pd

VIEW_TAILWIND = "tailwind"
VIEW_HEADWIND = "headwind"
VIEW_NEUTRAL = "neutral"

SNAPSHOT_COLUMNS = [
    "asof", "date", "asset", "score", "view", "coverage",
    "fwd_1m", "fwd_3m", "hit_1m", "hit_3m",
]


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
