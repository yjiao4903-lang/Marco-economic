"""PBOC adapter (V1.2B).

Serves policy-rate series (LPR) from the PBOC website. The monetary policy
department publishes one LPR announcement page per month; the adapter walks
the listing page, picks the newest announcement and parses the rates out of
the announcement text.

``provider_code`` is one of ``LPR_1Y`` / ``LPR_5Y``. One observation per
update (the latest announcement) is expected; staleness thresholds should be
set accordingly in data_sources.yaml.
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

LPR_LISTING_URL = (
    "http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/3876551/index.html"
)

_LPR_1Y_RE = re.compile(r"1年期LPR为(\d+(?:\.\d+)?)%")
_LPR_5Y_RE = re.compile(r"5年期以上LPR为(\d+(?:\.\d+)?)%")
_LISTING_ANCHOR_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*LPR[^"]*)"',
    re.IGNORECASE,
)
_LISTING_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def parse_lpr_listing(html: str, base_url: str) -> list[tuple[pd.Timestamp, str]]:
    """Extract (announcement date, absolute URL) pairs from the listing page."""
    out: dict[str, pd.Timestamp] = {}
    for href, title in _LISTING_ANCHOR_RE.findall(html):
        match = _LISTING_DATE_RE.search(title)
        if not match:
            continue
        parsed = pd.Timestamp(year=int(match[1]), month=int(match[2]), day=int(match[3]))
        absolute = urljoin(base_url, href)
        if absolute not in out or parsed > out[absolute]:
            out[absolute] = parsed
    return sorted(((date, url) for url, date in out.items()), reverse=True)


def parse_lpr_announcement(html: str) -> dict[str, float]:
    """Parse the LPR values out of one announcement page (HTML or text)."""
    text = re.sub(r"<[^>]+>", "", html)
    rates: dict[str, float] = {}
    if match := _LPR_1Y_RE.search(text):
        rates["LPR_1Y"] = float(match.group(1))
    if match := _LPR_5Y_RE.search(text):
        rates["LPR_5Y"] = float(match.group(1))
    if not rates:
        raise FetchError("PBOC announcement contains no LPR rates")
    return rates


class PbcAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        listing_url = self.provider_spec.options.get(
            "listing_url", LPR_LISTING_URL
        )

        listing_html = http_get(listing_url, timeout=self.provider_spec.timeout_seconds)
        announcements = parse_lpr_listing(listing_html, listing_url)
        if not announcements:
            raise FetchError("PBOC listing page contains no LPR announcements")

        announcement_date, announcement_url = announcements[0]
        html = http_get(announcement_url, timeout=self.provider_spec.timeout_seconds)
        rates = parse_lpr_announcement(html)
        if code not in rates:
            raise FetchError(
                f"PBOC announcement has no '{code}' rate; found {sorted(rates)}"
            )

        return build_canonical_frame(
            series_id,
            [announcement_date.date()],
            [rates[code]],
            provider=self.provider_id,
            source_file=announcement_url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
