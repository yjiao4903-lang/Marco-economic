"""U.S. Treasury Daily Par Real Yield Curve adapter (v0.4c Task 2).

Official keyless CSV per year:

    https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
    daily-treasury-rates.csv/{year}/all?type=daily_treasury_real_yield_curve
    &field_tdr_date_value={year}&page&_format=csv

Columns: ``Date`` (MM/DD/YYYY) plus quoted tenor labels (``"5 YR"``,
``"10 YR"``...). ``provider_code`` is the tenor label, e.g. ``10`` for the
10-year par real yield (percent). This is X1's PRIMARY source - FRED DFII10
stays as validation/fallback, contingent on the documented overlap check
(``scripts/overlap_check.py``, >= 60 common trading days).
"""

from __future__ import annotations

import csv as _csv
import io as _io
import time

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    http_get,
)

REAL_YIELD_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_real_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
FIRST_YEAR = 2003  # par real yield curve history starts here


def parse_real_yield_csv(text: str, code: str) -> tuple[list, list]:
    """Parse one year's CSV into (dates, values) for the tenor ``code``."""
    rows = list(_csv.reader(_io.StringIO(text)))
    if len(rows) < 2:
        raise FetchError("Treasury real yield CSV is empty")
    header = [c.strip().strip('"') for c in rows[0]]
    label = f"{code} YR"
    if label not in header:
        raise FetchError(f"Treasury CSV has no column '{label}': {header}")
    column = header.index(label)
    dates, values = [], []
    for row in rows[1:]:
        if not row:
            continue
        parsed = pd.to_datetime(row[0], format="%m/%d/%Y", errors="coerce")
        if pd.isna(parsed) or len(row) <= column:
            continue
        raw = row[column].strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        dates.append(parsed.date())
        values.append(value)
    # CSV rows are newest-first: sort ascending
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return [dates[i] for i in order], [values[i] for i in order]


class TreasuryAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        timeout = self.provider_spec.timeout_seconds

        end_year = pd.Timestamp(end_date).year if end_date is not None else pd.Timestamp.now().year
        start_year = (
            pd.Timestamp(start_date).year
            if start_date is not None
            else max(FIRST_YEAR, end_year - 2)  # default: last 3 years
        )
        dates: list = []
        values: list[float] = []
        for year in range(start_year, end_year + 1):
            text = http_get(REAL_YIELD_URL.format(year=year), timeout=timeout)
            year_dates, year_values = parse_real_yield_csv(text, code)
            dates.extend(year_dates)
            values.extend(year_values)
            if year != end_year:
                time.sleep(1)  # be polite to treasury.gov
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"Treasury returned no observations for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file="home.treasury.gov:daily_treasury_real_yield_curve",
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )
