"""SAFE (国家外汇管理局) adapter (V1.2B).

SAFE re-publishes the RMB central parity list (人民币汇率中间价) as dated
announcement pages. The adapter walks the listing page, picks the newest
announcement and extracts the USD/CNY central parity from its table.

``provider_code`` is the currency name as printed in the table row, e.g.
``美元``. Note that the ChinaMoney provider is the primary USD/CNY source;
SAFE is a redundancy for when chinamoney.com.cn is unreachable.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    http_get,
)

PARITY_LISTING_URL = "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"

_ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,120})</a>')
_DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_parity_links(html: str, base_url: str) -> list[tuple[pd.Timestamp, str]]:
    """Extract (date, absolute URL) pairs from the SAFE listing page."""
    out: dict[str, pd.Timestamp] = {}
    for href, title in _ANCHOR_RE.findall(html):
        if "人民币汇率中间价公告" not in title:
            continue
        match = _DATE_RE.search(title)
        if not match:
            continue
        parsed = pd.Timestamp(
            year=int(match[1]), month=int(match[2]), day=int(match[3])
        )
        absolute = urljoin(base_url, href)
        if absolute not in out or parsed > out[absolute]:
            out[absolute] = parsed
    return sorted(((date, url) for url, date in out.items()), reverse=True)


def parse_parity_table(html: str, currency: str) -> dict[str, float]:
    """Extract central parity values from one announcement page table.

    Returns ``{currency_name: rate}``, e.g. ``{"美元": 7.1}``.
    """
    rates: dict[str, float] = {}
    for row_html in _ROW_RE.findall(html):
        cells = [_TAG_RE.sub("", c).strip() for c in _CELL_RE.findall(row_html)]
        cells = [c for c in cells if c]
        if len(cells) < 2 or cells[0] != currency:
            continue
        try:
            rates[currency] = float(cells[1])
        except ValueError:
            continue
    if not rates:
        raise FetchError(f"SAFE announcement table has no '{currency}' row")
    return rates


class SafeAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        currency = self._require_code(series_id)
        listing_url = self.provider_spec.options.get(
            "listing_url", PARITY_LISTING_URL
        )

        listing_html = http_get(listing_url, timeout=self.provider_spec.timeout_seconds)
        announcements = parse_parity_links(listing_html, listing_url)
        if not announcements:
            raise FetchError("SAFE listing page contains no central parity announcements")

        announcement_date, announcement_url = announcements[0]
        html = http_get(announcement_url, timeout=self.provider_spec.timeout_seconds)
        rates = parse_parity_table(html, currency)

        return build_canonical_frame(
            series_id,
            [announcement_date.date()],
            [rates[currency]],
            provider=self.provider_id,
            source_file=announcement_url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
