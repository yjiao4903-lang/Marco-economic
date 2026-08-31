import pandas as pd

from macro_compass.data_sources.gold_monthly import (
    DAILY_SERIES_ID,
    MONTHLY_SERIES_ID,
    audit_gold_monthly,
    derive_gold_monthly,
)


def _daily(dates, values):
    return pd.DataFrame({
        "series_id": [DAILY_SERIES_ID] * len(dates), "date": pd.to_datetime(dates),
        "value": values, "source": "WIND", "source_file": "gold.xlsx",
        "import_time": pd.Timestamp("2026-08-31"), "series_name": "gold",
        "unit": "usd_per_troy_oz", "frequency": "daily", "category": "market",
    })


def test_uses_last_available_trade_day_and_month_end_date():
    out = derive_gold_monthly(_daily(["2024-01-02", "2024-01-31", "2024-03-01"], [1, 2, 3]))
    assert out["series_id"].eq(MONTHLY_SERIES_ID).all()
    assert out["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-31", "2024-03-31"]
    assert out["source_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-31", "2024-03-01"]
    assert out["value"].tolist() == [2, 3]
    assert out["enabled"].eq(False).all()


def test_audit_reports_missing_months_and_production_overlap():
    daily = _daily(["2024-01-31", "2024-03-29"], [2, 3])
    production = pd.DataFrame({"series_id": ["GOLD"], "date": pd.to_datetime(["2024-01-31"]), "value": [2.5]})
    audit = audit_gold_monthly(daily, production)
    assert audit.missing_months == ["2024-02"]
    assert audit.overlap_rows == 1
    assert audit.overlap_mean_abs_diff == audit.overlap_max_abs_diff == 0.5
