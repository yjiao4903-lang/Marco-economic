"""NY Fed adapter (V1.2B).

Reads the New York Fed's keyless JSON API for reference rates
(SOFR / SOFR Averages / volume-weighted rates):

    https://markets.newyorkfed.org/api/rates/secured/sofr/search.json

``provider_code`` is the rate type, e.g. ``SOFR``.
"""

from __future__ import annotations

import json

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    build_url,
    http_get,
)

SOFR_SEARCH_URL = (
    "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
)
SOFR_LAST_URL = (
    "https://markets.newyorkfed.org/api/rates/secured/sofr/last/500.json"
)


def build_nyfed_url(start_date=None, end_date=None) -> str:
    """Date-ranged query, or the last-500 endpoint for history-less backfills
    (``search.json`` without dates returns an empty payload; ``last`` caps at
    500 observations, i.e. roughly two years of business days)."""
    if start_date is None and end_date is None:
        return SOFR_LAST_URL
    params = {}
    if start_date is not None:
        params["startDate"] = pd.Timestamp(start_date).date().isoformat()
    if end_date is not None:
        params["endDate"] = pd.Timestamp(end_date).date().isoformat()
    return build_url(SOFR_SEARCH_URL, params)


def parse_ref_rates_json(text: str, rate_type: str) -> tuple[list, list]:
    """Parse a refRates JSON payload into (dates, percent rates)."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"NY Fed response is not valid JSON: {exc}") from exc
    rates = payload.get("refRates") or []

    dates, values = [], []
    for row in rates:
        if str(row.get("type", "")).upper() != rate_type.upper():
            continue
        parsed_date = pd.to_datetime(row.get("effectiveDate"), errors="coerce")
        try:
            value = float(row.get("percentRate"))
        except (TypeError, ValueError):
            continue
        if pd.isna(parsed_date):
            continue
        dates.append(parsed_date.date())
        values.append(value)
    return dates, values


class NyFedAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        rate_type = self._require_code(series_id)
        url = build_nyfed_url(start_date, end_date)
        text = http_get(url, timeout=self.provider_spec.timeout_seconds)
        dates, values = parse_ref_rates_json(text, rate_type)
        if not dates:
            raise FetchError(f"NY Fed returned no rates of type '{rate_type}'")
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
