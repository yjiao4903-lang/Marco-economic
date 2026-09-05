"""FRED adapter (V1.2A).

Uses the keyless ``fredgraph.csv`` endpoint, so no API key is required:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd=2026-01-01
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    build_url,
    http_get,
    temporal_metadata_for_spec,
)

FREDGRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
_FRED_API_PAGE_SIZE = 10_000
_FRED_API_MAX_RETRIES = 3


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


def parse_fred_observations_json(payload: str | bytes | dict, code: str) -> tuple[list, list]:
    """Parse official FRED observations JSON into dates and numeric values.

    FRED represents observations as strings and uses ``.`` for missing
    values.  Parsing is deliberately strict about the top-level shape while
    retaining the CSV parser's behavior of dropping unusable observations.
    """
    try:
        data = payload if isinstance(payload, dict) else json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FetchError(f"FRED API returned invalid JSON for '{code}'") from exc
    observations = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(observations, list):
        raise FetchError(f"FRED API response for '{code}' has no observations list")

    dates = []
    values = []
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        parsed_date = pd.to_datetime(observation.get("date"), errors="coerce")
        raw_value = observation.get("value")
        parsed_value = pd.to_numeric(
            None if raw_value in (None, "", ".") else raw_value,
            errors="coerce",
        )
        if pd.notna(parsed_date) and pd.notna(parsed_value):
            dates.append(parsed_date.date())
            values.append(float(parsed_value))
    return dates, values


def _fred_api_get(params: dict, *, timeout: int) -> dict:
    """GET one FRED API page without exposing the API key in failures."""
    url = build_url(FRED_OBSERVATIONS_URL, params)
    last_status = None
    for attempt in range(_FRED_API_MAX_RETRIES):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "macro-compass/0.3", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            try:
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise FetchError("FRED API returned an unexpected JSON shape")
                return payload
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                raise FetchError("FRED API returned invalid JSON") from exc
        except urllib.error.HTTPError as exc:
            status = exc.code
            last_status = status
            if status in (429, 423, 500) and attempt + 1 < _FRED_API_MAX_RETRIES:
                time.sleep(0.25 * (2**attempt))
                continue
            if status in (400, 404):
                raise FetchError(f"FRED API request rejected (HTTP {status})") from exc
            raise FetchError(f"FRED API request failed (HTTP {status})") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError("FRED API network request failed") from exc
    raise FetchError(f"FRED API request failed after retries (HTTP {last_status})")


class FredAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        api_key = os.environ.get("FRED_API_KEY", "").strip()
        if api_key:
            dates = []
            values = []
            offset = 0
            while True:
                params = {
                    "series_id": code,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "asc",
                    "limit": _FRED_API_PAGE_SIZE,
                    "offset": offset,
                }
                if start_date is not None:
                    params["observation_start"] = pd.Timestamp(start_date).date().isoformat()
                if end_date is not None:
                    params["observation_end"] = pd.Timestamp(end_date).date().isoformat()
                page = _fred_api_get(params, timeout=self.provider_spec.timeout_seconds)
                page_dates, page_values = parse_fred_observations_json(page, code)
                dates.extend(page_dates)
                values.extend(page_values)
                observation_count = page.get("observations")
                if (
                    not isinstance(observation_count, list)
                    or len(observation_count) < _FRED_API_PAGE_SIZE
                ):
                    break
                offset += _FRED_API_PAGE_SIZE
        else:
            url = build_fred_url(code, start_date, end_date)
            text = http_get(url, timeout=self.provider_spec.timeout_seconds)
            dates, values = parse_fred_csv(text, code)
        if not dates:
            raise FetchError(f"FRED returned no usable observations for '{code}'")
        temporal = temporal_metadata_for_spec(spec, dates)
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=FRED_OBSERVATIONS_URL if api_key else url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
            **temporal,
        )
