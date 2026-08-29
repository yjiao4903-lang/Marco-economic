"""FRED adapter (V1.2A).

Uses the keyless ``fredgraph.csv`` endpoint, so no API key is required:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd=2026-01-01
"""

from __future__ import annotations

import io

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    build_url,
    http_get,
)

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def build_fred_url(code: str, start_date=None, end_date=None) -> str:
    params = {"id": code}
    if start_date is not None:
        params["cosd"] = pd.Timestamp(start_date).date().isoformat()
    if end_date is not None:
        params["coed"] = pd.Timestamp(end_date).date().isoformat()
    return build_url(FREDGRAPH_URL, params)


def parse_fred_csv(text: str, code: str) -> tuple[list, list]:
    """Parse a fredgraph.csv payload into (dates, values).

    The file has a date column and one value column per series; missing
    observations are encoded as ``.`` and dropped.
    """
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise FetchError(f"FRED CSV for '{code}' has no value column: {list(df.columns)}")

    date_col = df.columns[0]
    value_col = code if code in df.columns else df.columns[1]

    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[value_col].replace(".", None), errors="coerce")
    mask = dates.notna() & values.notna()
    return list(dates[mask].dt.date), list(values[mask])


class FredAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        url = build_fred_url(code, start_date, end_date)
        text = http_get(url, timeout=self.provider_spec.timeout_seconds)
        dates, values = parse_fred_csv(text, code)
        if not dates:
            raise FetchError(f"FRED returned no usable observations for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
