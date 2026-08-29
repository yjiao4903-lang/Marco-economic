"""ChinaMoney (全国银行间同业拆借中心 / 中国货币网) adapter (V1.2A).

Primary use: USD/CNY central parity (中间价) via the keyless JSON API:

    https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew

``provider_code`` is the currency pair exactly as the API names it, e.g.
``USD/CNY``.
"""

from __future__ import annotations

import json
import time

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    build_url,
    http_get,
)

CCPR_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew"

# The chinamoney WAF rejects API hits without a browser-ish Referer and
# throttles rapid repeat requests (403); keep headers close to a real visit.
CCPR_HEADERS = {
    "Referer": "https://www.chinamoney.com.cn/chinese/bkccy/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def build_ccpr_url(
    currency: str,
    start_date=None,
    end_date=None,
    page_size: int = 50,
    page_num: int = 1,
) -> str:
    """Build one CcprHisNew request page.

    The ChinaMoney WAF rejects ``pageSize`` above ~50 with HTTP 403, so long
    backfills page through the API (see ``fetch_ccpr_pages``).
    """
    params = {
        "lang": "CN",
        "reference": "1",
        "currency": currency,
        "pageNum": page_num,
        "pageSize": page_size,
    }
    if start_date is not None:
        params["startDate"] = pd.Timestamp(start_date).date().isoformat()
    if end_date is not None:
        params["endDate"] = pd.Timestamp(end_date).date().isoformat()
    return build_url(CCPR_URL, params)


def fetch_ccpr_pages(
    currency: str,
    start_date,
    end_date,
    timeout: int,
    page_size: int = 50,
    max_pages: int = 40,
) -> str:
    """Page through CcprHisNew and return a JSON payload of all records.

    Returns a synthetic JSON document with the union of all fetched pages so
    ``parse_ccpr_json`` keeps a single-payload interface.
    """
    all_records: list = []
    head: list = []
    for page_num in range(1, max_pages + 1):
        url = build_ccpr_url(currency, start_date, end_date, page_size, page_num)
        try:
            text = http_get(url, headers=CCPR_HEADERS, timeout=timeout)
        except FetchError:
            if page_num == 1:
                # transient WAF throttling responds 403; back off once and retry
                time.sleep(3)
                text = http_get(url, headers=CCPR_HEADERS, timeout=timeout)
            else:
                raise
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FetchError(f"ChinaMoney response is not valid JSON: {exc}") from exc
        data = payload.get("data") or {}
        head = data.get("head") or head
        records = payload.get("records") or data.get("records") or []
        all_records.extend(records)
        total = data.get("total")
        if total is None or len(all_records) >= int(total) or not records:
            break
        time.sleep(2)
    return json.dumps({"data": {"head": head, "total": len(all_records)}, "records": all_records})


def parse_ccpr_json(text: str, currency: str) -> tuple[list, list]:
    """Parse a CcprHisNew JSON payload into (dates, values) for ``currency``.

    Response shape::

        {"data": {"head": ["USD/CNY", ...]}, "records": [{"date": "...", "values": ["6.7811"]}]}
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"ChinaMoney response is not valid JSON: {exc}") from exc
    data = payload.get("data") or {}
    head = data.get("head") or []
    records = payload.get("records") or data.get("records") or []
    if currency not in head:
        raise FetchError(
            f"ChinaMoney response does not contain currency '{currency}'; got {head}"
        )
    index = head.index(currency)

    dates, values = [], []
    for record in records:
        row_values = record.get("values") or []
        if index >= len(row_values):
            continue
        try:
            value = float(row_values[index])
        except (TypeError, ValueError):
            continue
        parsed_date = pd.to_datetime(record.get("date"), errors="coerce")
        if pd.isna(parsed_date):
            continue
        dates.append(parsed_date.date())
        values.append(value)
    return dates, values




# ---------------------------------------------------------------------------
# DR007 (V1.2C): the interbank repo chart static CSV. Only ~66 recent trading
# days are kept in the rolling file, so this is the LIVE source; history
# backfill comes from the AKShare FDR007 fixing (same depository-institution
# 7-day repo market) routed as this series' fallback.
DR007_CSV_URL = (
    "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv"
)
# column layout (0-based): 0 date, 6 DR001, 7 DR007, 8 DR014
DR007_COLUMNS = {"DR001": 6, "DR007": 7, "DR014": 8}

# V1.6A: CcprHisNew rejects spans beyond ~1 year (verified 2026-08-30: a 1y
# window returns ~245 records, longer spans return none). Initial/backfill
# fetches therefore walk the parity history in year segments; the anchor is
# a declared prior (deep daily parity history for the M5 percentile window)
# rather than the API's absolute first record.
PARITY_HISTORY_START = "2016-01-01"
PARITY_MAX_SPAN_DAYS = 360


def parse_dr007_csv(text: str, code: str) -> tuple[list, list]:
    """Parse the repo-rate chart CSV into (dates, values) for ``code``."""
    import csv as _csv
    import io as _io

    column = DR007_COLUMNS.get(code)
    if column is None:
        raise FetchError(f"ChinaMoney DR007 CSV has no column layout for '{code}'")
    dates, values = [], []
    for row in _csv.reader(_io.StringIO(text)):
        if not row or not row[0].strip():
            continue
        parsed = pd.to_datetime(row[0], errors="coerce")
        if len(row) <= column or pd.isna(parsed):
            continue
        try:
            value = float(row[column])
        except ValueError:
            continue
        dates.append(parsed.date())
        values.append(value)
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return [dates[i] for i in order], [values[i] for i in order]


class ChinaMoneyAdapter(DataSourceAdapter):

    def _fetch_dr007(self, series_id, spec) -> pd.DataFrame:
        code = self._require_code(series_id)
        text = http_get(
            DR007_CSV_URL,
            headers=CCPR_HEADERS,
            timeout=self.provider_spec.timeout_seconds,
        )
        dates, values = parse_dr007_csv(text, code)
        if not dates:
            raise FetchError(f"ChinaMoney repo chart returned no rows for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=DR007_CSV_URL,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        if series_id.startswith("CN_DR") or series_id.startswith("CN_FDR"):
            return self._fetch_dr007(series_id, spec)
        currency = self._require_code(series_id)
        end = pd.Timestamp(end_date) if end_date is not None else pd.Timestamp.now()
        if start_date is not None:
            segments = [(pd.Timestamp(start_date), end)]
        else:
            segments = []
            cursor = pd.Timestamp(PARITY_HISTORY_START)
            while cursor <= end:
                segment_end = min(cursor + pd.Timedelta(days=PARITY_MAX_SPAN_DAYS), end)
                segments.append((cursor, segment_end))
                cursor = segment_end + pd.Timedelta(days=1)

        dates: list = []
        values: list = []
        for segment_start, segment_end in segments:
            text = fetch_ccpr_pages(
                currency,
                segment_start,
                segment_end,
                timeout=self.provider_spec.timeout_seconds,
            )
            seg_dates, seg_values = parse_ccpr_json(text, currency)
            dates.extend(seg_dates)
            values.extend(seg_values)
            if len(segments) > 1:
                time.sleep(2)  # the WAF throttles rapid repeat requests
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        # later pages can repeat a date already seen: latest value wins
        by_date = dict(sorted(zip(dates, values), key=lambda pair: pair[0]))
        if not by_date:
            raise FetchError(f"ChinaMoney returned no records for '{currency}'")
        return build_canonical_frame(
            series_id,
            list(by_date.keys()),
            list(by_date.values()),
            provider=self.provider_id,
            source_file=CCPR_URL,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
