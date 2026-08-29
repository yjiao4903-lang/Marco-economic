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
import time
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

# ---------------------------------------------------------------------------
# V1.6A M4: full-curve table endpoint (verified 2026-08-30, see
# docs/research/2026-08-30_market_layer_sources.md). One GET returns the
# treasury / bank-AAA / MTN-AAA curves for every key tenor; the AAA credit
# spread is derived inside the adapter from two SAME-SOURCE legs (the
# derive_private_tsf_yoy precedent: a derived series computed where both
# official quantities are published together).
PBC_HISTORY_URL = (
    "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
)
# a single request must span at most 365 days - history backfills chunk by
# year segments and merge
PBC_QUERY_MAX_SPAN_DAYS = 360
# the MTN AAA curve starts 2006-12-25 (research archive); earlier chunks
# would return treasury-only rows and cannot produce a spread
PBC_SPREAD_HISTORY_START = "2006-12-25"

# provider_code -> (match substring of the wide leg, match substring of the
# base leg, tenor column label as printed in the table header)
SPREAD_ROUTES = {
    "AAA_MTN_SPREAD_3Y": ("中短期票据", "国债", "3年"),
}


def parse_history_query_spread(text: str, code: str) -> tuple[list, list]:
    """Parse a pbc/historyQuery HTML payload into (dates, spread values).

    The payload carries one row per curve per date with columns
    ``曲线名称 / 日期 / 3月 / 6月 / 1年 / 3年 / ...``. The spread value is
    ``wide_leg_curve - base_curve`` on dates where both legs are published;
    dates missing either leg are skipped (never interpolated).
    """
    if code not in SPREAD_ROUTES:
        raise FetchError(f"ChinaBond adapter has no spread route for '{code}'")
    wide_match, base_match, tenor_column = SPREAD_ROUTES[code]
    try:
        tables = pd.read_html(pd.io.common.StringIO(text))
    except ValueError as exc:
        raise FetchError(f"ChinaBond historyQuery payload has no tables: {exc}") from exc

    table = None
    for candidate in tables:
        # the endpoint renders the header as a plain row (no <thead>), so
        # read_html may return integer columns with the labels in row 0 -
        # promote that row before matching
        if "曲线名称" not in [str(c) for c in candidate.columns]:
            first_row = [str(v) for v in candidate.iloc[0].tolist()]
            if "曲线名称" in first_row:
                candidate = candidate.copy()
                candidate.columns = first_row
                candidate = candidate.iloc[1:].reset_index(drop=True)
        columns = [str(c) for c in candidate.columns]
        if "曲线名称" in columns and "日期" in columns and tenor_column in columns:
            table = candidate
            break
    if table is None:
        raise FetchError(
            f"ChinaBond historyQuery payload has no curve table with a '{tenor_column}' column"
        )

    wide: dict = {}
    base: dict = {}
    for _, row in table.iterrows():
        curve_name = str(row["曲线名称"])
        date = pd.to_datetime(row["日期"], errors="coerce")
        if pd.isna(date):
            continue
        try:
            value = float(row[tenor_column])
        except (TypeError, ValueError):
            continue
        if wide_match in curve_name:
            wide[date.date()] = value
        elif base_match in curve_name:
            base[date.date()] = value

    dates, values = [], []
    for date in sorted(set(wide) & set(base)):
        # round to 0.01bp to keep the subtraction free of float noise
        values.append(round(wide[date] - base[date], 6))
        dates.append(date)
    if not dates:
        raise FetchError(
            f"ChinaBond historyQuery payload has no overlapping {wide_match}/{base_match} rows"
        )
    return dates, values


def build_pbc_history_url(start_date, end_date) -> str:
    """One historyQuery GET for the given inclusive date window."""
    return (
        f"{PBC_HISTORY_URL}?startDate={pd.Timestamp(start_date).date().isoformat()}"
        f"&endDate={pd.Timestamp(end_date).date().isoformat()}"
        "&gjqx=0&qxId=ycqx&locale=cn_ZH"
    )


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
        if term in SPREAD_ROUTES:
            return self._fetch_spread(series_id, spec, term, start_date)

        options = self.provider_spec.options
        api_url = options.get("api_url", YZ_QUERY_URL)

        end = pd.Timestamp(end_date) if end_date is not None else pd.Timestamp.now()
        initial_days = int(options.get("initial_days", DEFAULT_START_DAYS))
        start = pd.Timestamp(start_date) if start_date is not None             else end - pd.Timedelta(days=initial_days)
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

    def _fetch_spread(
        self, series_id: str, spec, code: str, start_date=None
    ) -> pd.DataFrame:
        """AAA credit spread from the full-curve table endpoint.

        Incremental windows (start_date given) are one request; the initial /
        backfill fetch walks the curve history in <=360-day segments because
        the endpoint rejects spans beyond one year.
        """
        history_url = self.provider_spec.options.get("history_url", PBC_HISTORY_URL)
        end = pd.Timestamp.now()
        if start_date is not None:
            segments = [(pd.Timestamp(start_date), end)]
        else:
            segments = []
            cursor = pd.Timestamp(PBC_SPREAD_HISTORY_START)
            while cursor <= end:
                segment_end = min(cursor + pd.Timedelta(days=PBC_QUERY_MAX_SPAN_DAYS), end)
                segments.append((cursor, segment_end))
                cursor = segment_end + pd.Timedelta(days=1)

        dates: list = []
        values: list = []
        for segment_start, segment_end in segments:
            url = build_pbc_history_url(segment_start, segment_end).replace(
                PBC_HISTORY_URL, history_url, 1
            )
            text = http_get(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.provider_spec.timeout_seconds,
            )
            seg_dates, seg_values = parse_history_query_spread(text, code)
            dates.extend(seg_dates)
            values.extend(seg_values)
            if len(segments) > 1:
                time.sleep(0.5)  # be polite between year segments
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"ChinaBond returned no spread rows for '{series_id}'")
        order = sorted(range(len(dates)), key=lambda i: dates[i])
        dates = [dates[i] for i in order]
        values = [values[i] for i in order]
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=history_url,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )


def absolute_listing_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)
