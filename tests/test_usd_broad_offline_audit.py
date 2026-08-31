from pathlib import Path

import pandas as pd

from scripts.audit_usd_broad_offline import audit_usd_broad_file


def _write(path: Path, start: str, periods: int = 260) -> None:
    dates = pd.bdate_range(start, periods=periods)
    pd.DataFrame({"DATE": dates.strftime("%Y-%m-%d"), "DTWEXBGS": [100 + i / 100 for i in range(periods)]}).to_csv(path, index=False)


def test_usd_broad_offline_fred_shape_passes_and_does_not_write_canonical(tmp_path):
    path = tmp_path / "fred.csv"
    _write(path, "2006-01-03", 2600)
    result = audit_usd_broad_file(path)
    assert result["status"] == "PASS"
    assert result["definition_check"] == "PASS"
    assert result["continuity_check"] == "PASS"
    assert result["ready_250_observations"] is True
    assert result["history_120_months"] is True
    assert result["writes_canonical"] is False


def test_usd_broad_offline_duplicate_and_long_gap_fail(tmp_path):
    path = tmp_path / "bad.csv"
    dates = ["2006-01-03", "2006-01-04", "2006-01-04", "2006-02-20"]
    pd.DataFrame({"Date": dates, "美元广义指数": [100, 101, 101, 102]}).to_csv(path, index=False)
    result = audit_usd_broad_file(path)
    assert result["status"] == "FAIL"
    assert result["duplicate_dates"] == 1
    assert result["continuity_check"] == "FAIL"


def test_usd_broad_short_but_structurally_valid_is_warmup(tmp_path):
    path = tmp_path / "short.csv"
    _write(path, "2026-08-17", 5)
    result = audit_usd_broad_file(path)
    assert result["status"] == "PASS"
    assert result["readiness_status"] == "WARMUP"
    assert result["ready_250_observations"] is False
    assert result["history_120_months"] is False
