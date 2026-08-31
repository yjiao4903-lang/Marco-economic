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
    decision_snapshot_frame,
    outcome_observation_frame,
    validate_decision_snapshots,
    maturity_counts,
    DECISION_SNAPSHOT_COLUMNS,
    OUTCOME_OBSERVATION_COLUMNS,
    replay_gate,
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


def test_governed_storage_separates_decisions_and_outcomes():
    idx = _month_ends("2024-01-01", "2024-01-01")
    scores = pd.DataFrame({"A": [0.30]}, index=idx)
    cov = pd.DataFrame({"A": [1.0]}, index=idx)
    fwd = {"A": pd.DataFrame({"fwd_1m": [0.01], "fwd_3m": [0.03]}, index=idx)}
    decisions = decision_snapshot_frame(scores, cov, as_of="2024-02-01",
                                        config_hash="c", data_hash="d", git_hash_value="g")
    assert list(decisions.columns) == DECISION_SNAPSHOT_COLUMNS
    assert not (set(decisions.columns) & {"fwd_1m", "fwd_3m", "forward_return", "hit_1m"})
    assert validate_decision_snapshots(decisions)["valid"]
    outcomes = outcome_observation_frame(decisions, fwd, observed_as_of="2024-05-01")
    assert list(outcomes.columns) == OUTCOME_OBSERVATION_COLUMNS
    assert set(outcomes["snapshot_id"]) == set(decisions["snapshot_id"])
    assert maturity_counts(decisions, outcomes) == {
        "snapshot_count": 1, "matured_1m_count": 1, "matured_3m_count": 1,
    }
    assert replay_gate(decisions, outcomes)["valid"]
    bad = decisions.assign(forward_return=0.1)
    assert not validate_decision_snapshots(bad)["valid"]


def test_decision_snapshot_generation_excludes_future_period_labels():
    idx = pd.to_datetime(["2026-08-31", "2026-09-30"])
    scores = pd.DataFrame({"A": [0.30, 0.40]}, index=idx)
    cov = pd.DataFrame({"A": [1.0, 1.0]}, index=idx)
    decisions = decision_snapshot_frame(scores, cov, as_of="2026-09-01")
    assert set(decisions["decision_date"]) == {"2026-08-31"}


def test_replay_gate_rejects_future_decision_relative_to_recorded_as_of():
    idx = pd.to_datetime(["2026-09-30"])
    decisions = decision_snapshot_frame(
        pd.DataFrame({"A": [0.30]}, index=idx),
        pd.DataFrame({"A": [1.0]}, index=idx),
        as_of="2026-09-30",
    )
    bad = decisions.assign(as_of="2026-09-01")
    result = replay_gate(bad)
    assert not result["valid"]
    assert result["future_decision_count"] == 1


def test_outcomes_are_withheld_until_horizon_matures():
    idx = _month_ends("2024-01-01", "2024-01-01")
    scores = pd.DataFrame({"A": [0.30]}, index=idx)
    cov = pd.DataFrame({"A": [1.0]}, index=idx)
    fwd = {"A": pd.DataFrame({"fwd_1m": [0.01], "fwd_3m": [0.03]}, index=idx)}
    decisions = decision_snapshot_frame(scores, cov, as_of="2024-01-31")
    early = outcome_observation_frame(decisions, fwd, observed_as_of="2024-02-29")
    assert set(early["horizon"]) == {"1m"}
    late = outcome_observation_frame(decisions, fwd, observed_as_of="2024-04-30")
    assert set(late["horizon"]) == {"1m", "3m"}


def test_replay_gate_rejects_malformed_outcome_schema():
    decisions = pd.DataFrame(columns=DECISION_SNAPSHOT_COLUMNS)
    outcomes = pd.DataFrame(columns=["outcome_id", "snapshot_id", "horizon"])
    result = replay_gate(decisions, outcomes)
    assert not result["valid"]
    assert "forward_return" in result["missing_outcome_fields"]
