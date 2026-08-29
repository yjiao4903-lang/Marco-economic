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


class ChinaMoneyAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        currency = self._require_code(series_id)
        text = fetch_ccpr_pages(
            currency, start_date, end_date, timeout=self.provider_spec.timeout_seconds
        )
        dates, values = parse_ccpr_json(text, currency)
        if not dates:
            raise FetchError(f"ChinaMoney returned no records for '{currency}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=CCPR_URL,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
