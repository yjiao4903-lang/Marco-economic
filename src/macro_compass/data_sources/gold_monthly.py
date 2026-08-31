"""Audit-only monthly derivation for the London gold daily candidate.

This module deliberately does not write to canonical storage or register the
derived series with Asset/Signal consumers.  A month is represented by the
last available observation in that calendar month; months with no daily
observation are omitted (no forward-fill or other imputation).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

DAILY_SERIES_ID = "GOLD_LONDON_SPOT_USD_OZ_DAILY"
MONTHLY_SERIES_ID = "GOLD_LONDON_SPOT_USD_OZ_MONTHLY_CANDIDATE"
DAILY_UNIT = "usd_per_troy_oz"
MONTHLY_UNIT = "usd_per_troy_oz"
AGGREGATION_RULE = "last available daily observation per calendar month"


@dataclass(frozen=True)
class GoldMonthlyAudit:
    source_rows: int
    candidate_rows: int
    source_start: str | None
    source_end: str | None
    candidate_start: str | None
    candidate_end: str | None
    missing_months: list[str]
    overlap_rows: int
    overlap_mean_abs_diff: float | None
    overlap_max_abs_diff: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def derive_gold_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Derive an isolated monthly candidate from canonical daily rows.

    The output retains source date and source provenance on every row so that
    each monthly value can be traced to exactly one daily observation.
    """
    required = {"series_id", "date", "value", "unit", "frequency", "category"}
    missing = required.difference(daily.columns)
    if missing:
        raise ValueError(f"daily gold frame missing columns: {sorted(missing)}")
    frame = daily.loc[daily["series_id"].eq(DAILY_SERIES_ID)].copy()
    if frame.empty:
        return pd.DataFrame(columns=[
            "series_id", "date", "value", "source", "source_file",
            "import_time", "series_name", "unit", "frequency", "category",
            "source_series_id", "source_date", "aggregation_rule", "enabled",
        ])
    if not frame["unit"].eq(DAILY_UNIT).all():
        raise ValueError("daily gold candidate must use usd_per_troy_oz")
    if not frame["frequency"].eq("daily").all():
        raise ValueError("daily gold candidate must use daily frequency")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame = frame.sort_values("date")
    frame["_month"] = frame["date"].dt.to_period("M")
    selected = frame.groupby("_month", sort=True, as_index=False).tail(1).copy()
    selected["source_date"] = selected["date"]
    selected["date"] = selected["_month"].dt.to_timestamp(how="end").dt.normalize()
    selected["series_id"] = MONTHLY_SERIES_ID
    selected["series_name"] = "伦敦黄金现货月末值(隔离候选)"
    selected["unit"] = MONTHLY_UNIT
    selected["frequency"] = "monthly"
    selected["source_series_id"] = DAILY_SERIES_ID
    selected["aggregation_rule"] = AGGREGATION_RULE
    selected["enabled"] = False
    return selected.drop(columns="_month").reset_index(drop=True)


def audit_gold_monthly(daily: pd.DataFrame, production_gold: pd.DataFrame) -> GoldMonthlyAudit:
    """Return coverage, gaps, and overlap differences without mutating inputs."""
    candidate = derive_gold_monthly(daily)
    src = daily.loc[daily["series_id"].eq(DAILY_SERIES_ID)].copy()
    src_dates = pd.to_datetime(src["date"], errors="raise").dt.normalize() if not src.empty else pd.Series(dtype="datetime64[ns]")
    prod = production_gold.loc[production_gold["series_id"].eq("GOLD")].copy()
    prod["date"] = pd.to_datetime(prod["date"], errors="raise").dt.normalize()
    candidate_dates = pd.to_datetime(candidate["date"]) if not candidate.empty else pd.Series(dtype="datetime64[ns]")
    expected = pd.period_range(src_dates.min().to_period("M"), src_dates.max().to_period("M"), freq="M") if not src.empty else pd.PeriodIndex([], freq="M")
    actual = pd.PeriodIndex(candidate_dates, freq="M") if not candidate.empty else pd.PeriodIndex([], freq="M")
    missing = [str(p) for p in expected.difference(actual)]
    joined = candidate[["date", "value"]].merge(prod[["date", "value"]], on="date", how="inner", suffixes=("_candidate", "_production"))
    diff = (joined["value_candidate"] - joined["value_production"]).abs()
    return GoldMonthlyAudit(
        source_rows=len(src), candidate_rows=len(candidate),
        source_start=str(src_dates.min().date()) if not src.empty else None,
        source_end=str(src_dates.max().date()) if not src.empty else None,
        candidate_start=str(candidate_dates.min().date()) if not candidate.empty else None,
        candidate_end=str(candidate_dates.max().date()) if not candidate.empty else None,
        missing_months=missing, overlap_rows=len(joined),
        overlap_mean_abs_diff=float(diff.mean()) if len(diff) else None,
        overlap_max_abs_diff=float(diff.max()) if len(diff) else None,
    )
