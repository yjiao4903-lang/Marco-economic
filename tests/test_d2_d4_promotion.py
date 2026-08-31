"""Safety gates for the explicit D2/D4 promotion command."""

from pathlib import Path

import pandas as pd
import pytest

from macro_compass.d2_d4_promotion import (
    PromotionError,
    apply_promotion,
    build_promotion_plan,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2018-01-31", "2026-07-31", freq="ME")
    rows = []
    for candidate, production in (
        ("CN_TSF_TOTAL_WIND_CANDIDATE", "CN_TSF_TOTAL"),
        ("CN_GOV_BOND_FINANCING_WIND_CANDIDATE", "CN_GOV_BOND_FINANCING"),
    ):
        for date in dates:
            source = "PBC" if date >= pd.Timestamp("2026-04-01") else "WIND_PLACEHOLDER"
            rows.append({"series_id": production, "date": date, "value": 100.0,
                         "source": source, "unit": "bn_cny", "frequency": "monthly",
                         "category": "macro", "source_file": "fixture", "import_time": pd.Timestamp.now()})
            rows.append({"series_id": candidate, "date": date, "value": 100.0,
                         "source": "WIND", "unit": "bn_cny", "frequency": "monthly",
                         "category": "macro", "source_file": "fixture", "import_time": pd.Timestamp.now()})
    canonical = pd.DataFrame(rows)
    pbc = pd.DataFrame([
        {"series_id": f"{production}_PBC_REPORTED_CANDIDATE", "date": date,
         "value": 100.0, "unit": "bn_cny", "frequency": "monthly", "source": "PBC"}
        for production in ("CN_TSF_TOTAL", "CN_GOV_BOND_FINANCING")
        for date in pd.date_range("2026-04-30", "2026-07-31", freq="ME")
    ])
    return canonical, pbc


def test_dry_run_plan_does_not_mutate_input():
    canonical, pbc = _frames()
    before = canonical.copy(deep=True)
    plan = build_promotion_plan(canonical, pbc)
    assert len(plan.rows) == 2 * 99
    assert plan.report["release_gate_policy"]["status"] == "CONDITIONALLY_ACCEPTED"
    assert plan.report["release_gate_policy"]["selected_gate"] == "public_cumulative_report_resolution_aware"
    assert plan.checks["independent_strict_live_pbc_gate"]["status"] == "SEPARATE_NOT_EVALUATED"
    assert plan.checks["independent_strict_live_pbc_gate"]["absolute_limit_bn_cny"] == 0.1
    pd.testing.assert_frame_equal(canonical, before)


def test_rejects_non_placeholder_history():
    canonical, pbc = _frames()
    canonical.loc[(canonical.series_id == "CN_TSF_TOTAL") & (canonical.date == "2018-01-31"), "source"] = "PBC"
    with pytest.raises(PromotionError, match="WIND_PLACEHOLDER"):
        build_promotion_plan(canonical, pbc)


def test_rejects_rounding_gate_failure():
    canonical, pbc = _frames()
    pbc.loc[pbc.series_id == "CN_TSF_TOTAL_PBC_REPORTED_CANDIDATE", "value"] = 111.0
    with pytest.raises(PromotionError, match="rounding"):
        build_promotion_plan(canonical, pbc)


def test_apply_replaces_history_and_preserves_pbc_tail(tmp_path: Path):
    canonical, pbc = _frames()
    canonical_path = tmp_path / "macro.parquet"
    db_path = tmp_path / "macro.duckdb"
    canonical.to_parquet(canonical_path, index=False)
    plan = build_promotion_plan(canonical, pbc)
    result = apply_promotion(plan, canonical_path, db_path, {}, tmp_path / "backup")
    assert result["status"] == "APPLIED"
    output = pd.read_parquet(canonical_path)
    old = output[(output.series_id == "CN_TSF_TOTAL") & (output.date < "2026-04-01")]
    tail = output[(output.series_id == "CN_TSF_TOTAL") & (output.date >= "2026-04-01")]
    assert old.source.eq("WIND").all()
    assert tail.source.eq("PBC").all()
    assert len(tail) == 4
    assert (tmp_path / "backup" / "macro.parquet").exists()
    assert db_path.exists()
