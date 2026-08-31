"""Audit-only checks for PBC cumulative-report flow candidates.

These tests intentionally read the local candidate artifact rather than the
production canonical store.  They protect the rounding-aware comparison gate
and the no-promotion metadata contract.
"""

from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).parents[1]
FLOW = ROOT / "data" / "local" / "pbc_reported_flow_candidates_20260831.csv"
CUM = ROOT / "data" / "local" / "pbc_reported_cumulative_sources_20260831.csv"


def test_pbc_reported_candidates_are_complete_and_continuous() -> None:
    flow = pd.read_csv(FLOW)
    expected = {
        "CN_TSF_TOTAL_PBC_REPORTED_CANDIDATE": [620.0, 2030.0, 3360.0, 1410.0],
        "CN_GOV_BOND_FINANCING_PBC_REPORTED_CANDIDATE": [910.0, 1220.0, 770.0, 1320.0],
    }
    for series_id, values in expected.items():
        rows = flow[flow["series_id"] == series_id].sort_values("date")
        assert rows["date"].tolist() == [
            "2026-04-30",
            "2026-05-31",
            "2026-06-30",
            "2026-07-31",
        ]
        assert rows["value"].tolist() == values
        assert rows["unit"].eq("bn_cny").all()
        assert rows["statistical_month"].tolist() == [
            "2026-04",
            "2026-05",
            "2026-06",
            "2026-07",
        ]
        assert rows["source_url"].str.startswith("https://www.pbc.gov.cn/").all()


def test_pbc_reported_candidates_pass_rounding_aware_wind_gate() -> None:
    pbc = pd.read_csv(FLOW)
    pbc["date"] = pd.to_datetime(pbc["date"]).dt.strftime("%Y-%m-%d")
    wind = pd.read_parquet(ROOT / "data" / "canonical" / "macro" / "macro.parquet")
    wind["date"] = pd.to_datetime(wind["date"]).dt.strftime("%Y-%m-%d")
    wind = wind[wind["series_id"].isin(
        ["CN_TSF_TOTAL_WIND_CANDIDATE", "CN_GOV_BOND_FINANCING_WIND_CANDIDATE"]
    )]
    mapping = {
        "CN_TSF_TOTAL_PBC_REPORTED_CANDIDATE": "CN_TSF_TOTAL_WIND_CANDIDATE",
        "CN_GOV_BOND_FINANCING_PBC_REPORTED_CANDIDATE": "CN_GOV_BOND_FINANCING_WIND_CANDIDATE",
    }
    for pbc_id, wind_id in mapping.items():
        left = pbc[pbc["series_id"] == pbc_id].set_index("date")
        right = wind[wind["series_id"] == wind_id].set_index("date")
        joined = left.join(right[["value"]], lsuffix="_pbc", rsuffix="_wind", how="inner")
        assert joined.index.tolist() == ["2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31"]
        absolute = (joined["value_pbc"] - joined["value_wind"]).abs()
        relative = absolute / joined["value_wind"].abs()
        assert (absolute <= 10.0).all()
        joined["absolute_diff"] = absolute
        joined["relative_diff"] = relative
        assert joined["absolute_diff"].notna().all()
        assert joined["relative_diff"].notna().all()


def test_candidate_config_is_disabled_and_not_in_signals() -> None:
    indicators = yaml.safe_load((ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    signals_text = (ROOT / "config" / "signals.yaml").read_text(encoding="utf-8")
    for series_id in (
        "CN_TSF_TOTAL_PBC_REPORTED_CANDIDATE",
        "CN_GOV_BOND_FINANCING_PBC_REPORTED_CANDIDATE",
    ):
        assert indicators[series_id]["enabled"] is False
        assert series_id not in signals_text


def test_cumulative_source_contract_preserves_resolution_and_raw_unit() -> None:
    cumulative = pd.read_csv(CUM)
    assert cumulative["statistical_month"].tolist() == [
        "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"
    ]
    assert cumulative["raw_unit"].eq("万亿元").all()
    assert cumulative["resolution_note"].str.contains("0.01万亿元分辨率").all()
    assert cumulative["source_url"].str.startswith("https://www.pbc.gov.cn/").all()
