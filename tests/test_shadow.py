"""Shadow Operation metrics tests.

These exercise the PURE functions of src/macro_compass/shadow/metrics.py with
synthetic inputs (never the production canonical pipeline). They prove the
view labelling, the directional hit rule, the summary counting and the
append-only upsert semantics behave as declared. They do NOT require network
and do NOT write to canonical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_compass.shadow.metrics import (
    VIEW_HEADWIND,
    VIEW_NEUTRAL,
    VIEW_TAILWIND,
    asset_views,
    hit_summary,
    realized_frame,
    upsert_snapshot,
    view_of,
)


def _month_ends(start="2024-01-01", end="2025-12-31"):
    return pd.date_range(start, end, freq="MS") + pd.offsets.MonthEnd(0)


# ---------------------------------------------------------------- view_of


def test_view_of_threshold_semantics():
    assert view_of(0.20, 0.15) == VIEW_TAILWIND
    assert view_of(-0.20, 0.15) == VIEW_HEADWIND
    assert view_of(0.10, 0.15) == VIEW_NEUTRAL
    assert view_of(-0.10, 0.15) == VIEW_NEUTRAL
    assert view_of(0.15, 0.15) == VIEW_TAILWIND   # >= threshold
    assert view_of(-0.15, 0.15) == VIEW_HEADWIND
    assert view_of(np.nan, 0.15) == ""


def test_asset_views_maps_every_cell():
    scores = pd.DataFrame({
        "CN_EQUITY": [0.30, 0.05, -0.30],
        "CNY": [-0.40, 0.00, 0.12],
    }, index=_month_ends("2024-01-01", "2024-03-01"))
    views = asset_views(scores, threshold=0.15)
    assert views.loc[scores.index[0], "CN_EQUITY"] == VIEW_TAILWIND
    assert views.loc[scores.index[1], "CN_EQUITY"] == VIEW_NEUTRAL
    assert views.loc[scores.index[2], "CN_EQUITY"] == VIEW_HEADWIND
    assert views.loc[scores.index[0], "CNY"] == VIEW_HEADWIND
    assert views.loc[scores.index[2], "CNY"] == VIEW_NEUTRAL


# ------------------------------------------------------------ realized_frame


def _sample_frame():
    idx = _month_ends("2024-01-01", "2024-04-01")
    scores = pd.DataFrame({
        "A": [0.30, -0.30, 0.30, 0.05],   # TW, HW, TW, neutral
    }, index=idx)
    fwd = {
        "A": pd.DataFrame({
            "fwd_1m": [0.01, -0.02, 0.00, 0.01],
            "fwd_3m": [0.02, -0.01, 0.03, 0.01],
        }, index=idx),
    }
    cov = pd.DataFrame(1.0, index=idx, columns=["A"])
    return scores, fwd, cov


def test_realized_frame_hit_rule():
    scores, fwd, cov = _sample_frame()
    frame = realized_frame(scores, fwd, cov, threshold=0.15)
    assert list(frame.columns) == [
        "date", "asset", "score", "view", "coverage",
        "fwd_1m", "fwd_3m", "hit_1m", "hit_3m",
    ]
    by_date = {pd.Timestamp(r.date): r for _, r in frame.iterrows()}
    d0, d1, d2, d3 = (pd.Timestamp(d) for d in frame["date"])

    # tailwind + positive fwd -> hit True
    assert by_date[d0]["view"] == VIEW_TAILWIND
    assert by_date[d0]["hit_1m"] is True
    assert by_date[d0]["hit_3m"] is True
    # headwind + negative fwd -> hit True
    assert by_date[d1]["view"] == VIEW_HEADWIND
    assert by_date[d1]["hit_1m"] is True
    assert by_date[d1]["hit_3m"] is True
    # tailwind + zero fwd -> not a hit (strict sign)
    assert by_date[d2]["hit_1m"] is False
    # neutral -> no directional claim (NaN hit)
    assert by_date[d3]["view"] == VIEW_NEUTRAL
    assert pd.isna(by_date[d3]["hit_1m"])


# ------------------------------------------------------------- hit_summary


def test_hit_summary_counts_non_neutral_only():
    scores, fwd, cov = _sample_frame()
    frame = realized_frame(scores, fwd, cov, threshold=0.15)
    s = hit_summary(frame, horizon="1m")
    row = s[s["asset"] == "A"].iloc[0]
    # counted = TW(3 rows: d0,d2) + HW(1 row: d1) with fwd; d3 neutral excluded
    assert row["n_views"] == 3
    assert row["n_tailwind"] == 2
    assert row["n_headwind"] == 1
    # hits: d0 True, d1 True, d2 False
    assert row["n_hit"] == 2
    assert row["hit_rate"] == pytest.approx(2 / 3)


def test_hit_summary_empty_when_no_realized_fwd():
    idx = _month_ends("2024-01-01", "2024-02-01")
    scores = pd.DataFrame({"A": [0.30, 0.30]}, index=idx)
    fwd = {"A": pd.DataFrame(
        {"fwd_3m": [np.nan, np.nan]}, index=idx)}
    cov = pd.DataFrame(1.0, index=idx, columns=["A"])
    frame = realized_frame(scores, fwd, cov, threshold=0.15)
    assert hit_summary(frame, horizon="3m").empty


# --------------------------------------------------------- upsert_snapshot


def test_upsert_appends_and_refreshes(tmp_path):
    idx = _month_ends("2024-01-01", "2024-02-01")
    scores = pd.DataFrame({"A": [0.30, -0.30]}, index=idx)
    fwd = {"A": pd.DataFrame(
        {"fwd_1m": [np.nan, np.nan], "fwd_3m": [np.nan, np.nan]}, index=idx)}
    cov = pd.DataFrame(1.0, index=idx, columns=["A"])

    p = tmp_path / "shadow_metrics.csv"
    run1 = realized_frame(scores, fwd, cov, threshold=0.15)
    merged1 = upsert_snapshot(p, run1, pd.Timestamp("2024-03-01"))
    merged1.to_csv(p, index=False, encoding="utf-8-sig")
    assert len(merged1) == 2
    # asof = first observation run date
    assert (merged1["asof"].astype(str) == "2024-03-01").all()

    # second run: same dates, fwd now realized for date0 only
    fwd2 = {"A": pd.DataFrame({
        "fwd_1m": [0.01, np.nan], "fwd_3m": [0.02, np.nan]}, index=idx)}
    run2 = realized_frame(scores, fwd2, cov, threshold=0.15)
    merged2 = upsert_snapshot(p, run2, pd.Timestamp("2024-04-01"))
    # still 2 rows (dedupe on date x asset), no new date added
    assert len(merged2) == 2
    assert set(merged2["date"]) == {str(d) for d in run1["date"]}
    # existing row refreshed with realized fwd, first-observed asof preserved
    row = merged2[merged2["date"].astype(str) == str(idx[0].date())].iloc[0]
    assert row["fwd_3m"] == pytest.approx(0.02)
    assert row["hit_3m"] is True
    assert str(row["asof"]) == "2024-03-01"
