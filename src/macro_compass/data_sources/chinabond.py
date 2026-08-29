"""ChinaBond (中国债券信息网) adapter (V1.2A).

ChinaBond yield-curve data lives behind a token-guarded POST endpoint
(``searchYc``); the token is scraped from the curve page HTML at fetch time.
The endpoint has proven unstable (page 404s / empty results when the token
scheme changes), so this adapter is a best-effort source for CGB yields -
the ChinaMoney curve or a Wind manual export remain the fallbacks.

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

YC_MAIN_URL = "https://yield.chinabond.com.cn/cbweb-mn/yc/main?locale=zh_CN"
SEARCH_YC_URL = "https://yield.chinabond.com.cn/cbweb-mn/yc/searchYc"
YC_DEF_ID = "2c9081e50a2f9606010a3068cae70001"  # 中债国债收益率曲线

_TOKEN_RE = re.compile(r'"([0-9a-f]{32})"')
_DATE_KEYS = ("infoDate", "workTime", "date", "日期", "tradingDay")


def extract_token(html: str) -> str:
    """Scrape the 32-hex token embedded in the yield-curve page."""
    match = _TOKEN_RE.search(html)
    if not match:
        raise FetchError("ChinaBond page did not expose a request token")
    return match.group(1)


def parse_search_yc(text: str, term: str) -> tuple[list, list]:
    """Parse the searchYc JSON list into (dates, values) for one curve term.

    Items are dicts keyed by date-ish fields and term labels like ``10年``;
    the parser tolerates both ``10年`` and plain ``10`` keys.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"ChinaBond response is not valid JSON: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise FetchError(f"ChinaBond returned no rows for term '{term}'")

    value_keys = (f"{term}年", str(term))
    dates, values = [], []
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_date = next((item[k] for k in _DATE_KEYS if item.get(k)), None)
        raw_value = next((item[k] for k in value_keys if item.get(k)), None)
        parsed_date = pd.to_datetime(raw_date, errors="coerce")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if pd.isna(parsed_date):
            continue
        dates.append(parsed_date.date())
        values.append(value)
    return dates, values


class ChinaBondAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        term = self._require_code(series_id)
        options = self.provider_spec.options

        page_url = options.get("page_url", YC_MAIN_URL)
        api_url = options.get("api_url", SEARCH_YC_URL)
        yc_def_id = options.get("yc_def_id", YC_DEF_ID)

        page_html = http_get(page_url, timeout=self.provider_spec.timeout_seconds)
        token = extract_token(page_html)
        work_times = pd.Timestamp(end_date).date().isoformat() if end_date is not None \
            else pd.Timestamp.now().date().isoformat()
        form = (
            "xyzSelect=txy"
            f"&workTimes={work_times}"
            "&dxbj=0&qxll=0,&yqqxN=N&yqqxK=Y"
            f"&ycDefIds={yc_def_id}"
            "&wrjxCBFlag=0&language=SS&locale=zh_CN"
            f"&token={token}"
        )
        text = http_get(
            api_url,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page_url,
            },
            timeout=self.provider_spec.timeout_seconds,
        )
        dates, values = parse_search_yc(text, term)
        if not dates:
            raise FetchError(f"ChinaBond returned no usable rows for term '{term}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=api_url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )


def absolute_listing_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)
