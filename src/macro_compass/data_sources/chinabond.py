"""ChinaBond (中国债券信息网) adapter (V1.2C, endpoint replaced).

The old token-guarded ``searchYc`` endpoint was retired (404). The active
endpoint is the treasury yield curve query ``pgxh/yzQuery`` (POST, keyless):

    POST https://yield.chinabond.com.cn/cbweb-mn/pgxh/yzQuery?gjqx=10
         &startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

Response: a JSON list with one entry whose ``seriesData`` is
``[[epoch_millis, yield_percent], ...]``. Endpoint verified 2026-08-29
(HTTP 200, values cross-checked) - see docs/research/2026-08-29_data_sources_survey.md.

``provider_code`` is the curve term label, e.g. ``10`` for the 10-year point.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    http_get,
)

YZ_QUERY_URL = "https://yield.chinabond.com.cn/cbweb-mn/pgxh/yzQuery"
DEFAULT_START_DAYS = 120  # initial fetch window; incremental overlap trims it


def parse_yz_query(text: str) -> tuple[list, list]:
    """Parse a yzQuery payload into (dates, values)."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"ChinaBond response is not valid JSON: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise FetchError("ChinaBond yzQuery returned no rows")
    series = payload[0].get("seriesData") or []
    dates, values = [], []
    for point in series:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            millis, value = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        dates.append(pd.Timestamp(millis, unit="ms").date())
        values.append(value)
    return dates, values


class ChinaBondAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        term = self._require_code(series_id)
        options = self.provider_spec.options
        api_url = options.get("api_url", YZ_QUERY_URL)

        end = pd.Timestamp(end_date) if end_date is not None else pd.Timestamp.now()
        start = pd.Timestamp(start_date) if start_date is not None             else end - pd.Timedelta(days=DEFAULT_START_DAYS)
        params = {
            "gjqx": term,
            "startDate": start.date().isoformat(),
            "endDate": end.date().isoformat(),
        }
        text = http_get(
            f"{api_url}?gjqx={term}&&startDate={params['startDate']}"
            f"&&endDate={params['endDate']}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.provider_spec.timeout_seconds,
        )
        dates, values = parse_yz_query(text)
        if start_date is not None:
            start_d = start.date()
            keep = [i for i, d in enumerate(dates) if d >= start_d]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"ChinaBond returned no usable rows for term '{term}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=api_url,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )


def absolute_listing_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)
