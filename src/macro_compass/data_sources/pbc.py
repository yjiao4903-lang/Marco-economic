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

from macro_compass.data_sources.cumulative import cumulative_to_monthly
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




# ---------------------------------------------------------------------------
# OMO 7-day reverse repo (V1.2C)
# The transaction-announcement listing is plain HTML (one page, ~20 latest
# announcements; the announcement body is static). The rate appears in a
# table cell that HTML stripping sometimes splits ("1. 40 %"), so the parser
# tolerates whitespace inside the number.

OMO_LISTING_URL = (
    "http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html"
)

_OMO_ANCHOR_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*title="([^"]*公开市场业务交易公告[^"]*)"',
    re.IGNORECASE,
)
_OMO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}")
_OMO_RATE_RE = re.compile(r"7\s*天\s*([\d.\s]+?)\s*%")


def parse_omo_listing(html: str, base_url: str) -> list[tuple[str, str]]:
    """(announcement page URL, raw date string if present) for OMO announcements."""
    out: list[str] = []
    for href, _title in _OMO_ANCHOR_RE.findall(html):
        url = urljoin(base_url, href)
        if url not in out:
            out.append(url)
    return out


def parse_omo_announcement(html: str, url: str) -> tuple[pd.Timestamp, float] | None:
    """(date, 7-day reverse repo rate %) from one transaction announcement."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    rate_match = _OMO_RATE_RE.search(text)
    if not rate_match:
        return None
    rate = float(rate_match.group(1).replace(" ", ""))
    date_match = _OMO_DATE_RE.search(text)
    if date_match:
        date = pd.Timestamp(date_match.group(1))
    else:
        digits = re.search(r"/(\d{14})/", url)
        if not digits:
            return None
        raw = digits.group(1)
        date = pd.Timestamp(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
    return date, rate


# ---------------------------------------------------------------------------
# Monthly financial statistics reports (V1.2C)
# The 调查统计司 publishes a monthly "金融统计数据报告" whose prose contains the
# year-to-date cumulative social financing aggregate and its government bond
# component. Cumulative values are converted to monthly flows with the
# fixture-tested ``cumulative_to_monthly`` utility.

STATS_LISTING_URL = "http://www.pbc.gov.cn/diaochatongjisi/116219/index.html"

_REPORT_TITLE_RE = re.compile(r"(\d{4})年(?:(\d{1,2})月|上半年)金融统计数据报告")
_YEAR_PAGE_RE = re.compile(r'href="([^"]+)"[^>]*>\s*(\d{4}年统计数据)\s*<')
_TSF_CUM_RE = re.compile(
    r"前[\d一二三四五六七八九十]+个月社会融资规模增量累计为\s*([\d.]+)\s*(万亿元|亿元)"
)
_GOV_BOND_CUM_RE = re.compile(
    r"政府债券净融资\s*([\d.]+)\s*(万亿元|亿元)"
)


def parse_stats_listing(html: str, base_url: str) -> list[tuple[str, str]]:
    """(title, absolute URL) for monthly statistics report articles."""
    out: dict[str, str] = {}
    for href, title in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{4,60}?)\s*<', html):
        title = title.strip()
        if _REPORT_TITLE_RE.search(title) and title not in out:
            out[title] = urljoin(base_url, href)
    return sorted(out.items())


def parse_report_cumulative(text: str) -> dict[str, float | None]:
    """Cumulative YTD (亿元) for TSF total and government bond financing."""
    result = {"TSF_TOTAL": None, "GOV_BOND_FINANCING": None}
    for key, pattern in (("TSF_TOTAL", _TSF_CUM_RE), ("GOV_BOND_FINANCING", _GOV_BOND_CUM_RE)):
        match = pattern.search(text)
        if match:
            value = float(match.group(1))
            if match.group(2) == "万亿元":
                value *= 10000.0
            result[key] = value
    return result


class PbcAdapter(DataSourceAdapter):
    """Dispatches on ``provider_code``:

    - ``LPR_1Y`` / ``LPR_5Y``      - monthly LPR announcement (V1.2B)
    - ``OMO_7D``                   - 7-day reverse repo policy rate from the
                                     daily open-market transaction announcements
    - ``TSF_TOTAL`` / ``GOV_BOND_FINANCING`` - monthly flow (亿元) reconstructed
                                     from the year-to-date cumulative values in
                                     the financial statistics reports
    """

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        if code in ("LPR_1Y", "LPR_5Y"):
            return self._fetch_lpr(series_id, spec, code)
        if code == "OMO_7D":
            return self._fetch_omo(series_id, spec)
        if code in ("TSF_TOTAL", "GOV_BOND_FINANCING"):
            return self._fetch_stats(series_id, spec, code)
        raise FetchError(f"PBOC adapter has no route for provider_code '{code}'")

    def _fetch_lpr(self, series_id, spec, code) -> pd.DataFrame:
        listing_url = self.provider_spec.options.get("listing_url", LPR_LISTING_URL)
        listing_html = http_get(listing_url, timeout=self.provider_spec.timeout_seconds)
        announcements = parse_lpr_listing(listing_html, listing_url)
        if not announcements:
            raise FetchError("PBOC listing page contains no LPR announcements")
        announcement_date, announcement_url = announcements[0]
        html = http_get(announcement_url, timeout=self.provider_spec.timeout_seconds)
        rates = parse_lpr_announcement(html)
        if code not in rates:
            raise FetchError(f"PBOC announcement has no '{code}' rate; found {sorted(rates)}")
        return build_canonical_frame(
            series_id,
            [announcement_date.date()],
            [rates[code]],
            provider=self.provider_id,
            source_file=announcement_url,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )

    def _fetch_omo(self, series_id, spec) -> pd.DataFrame:
        listing_url = self.provider_spec.options.get("listing_url", OMO_LISTING_URL)
        max_announcements = int(self.provider_spec.options.get("max_announcements", 20))
        listing_html = http_get(listing_url, timeout=self.provider_spec.timeout_seconds)
        urls = parse_omo_listing(listing_html, listing_url)
        if not urls:
            raise FetchError("PBOC OMO listing page contains no announcements")
        observations: list[tuple[pd.Timestamp, float]] = []
        for url in urls[:max_announcements]:
            html = http_get(url, timeout=self.provider_spec.timeout_seconds)
            parsed = parse_omo_announcement(html, url)
            if parsed is not None:
                observations.append(parsed)
        if not observations:
            raise FetchError("PBOC OMO announcements contained no 7-day reverse repo rate")
        seen = {}
        for date, rate in observations:
            seen[date] = rate  # later announcements win per date
        dates = sorted(seen)
        return build_canonical_frame(
            series_id,
            [d.date() for d in dates],
            [seen[d] for d in dates],
            provider=self.provider_id,
            source_file=listing_url,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )

    def _fetch_stats(self, series_id, spec, code) -> pd.DataFrame:
        timeout = self.provider_spec.timeout_seconds
        listing_url = STATS_LISTING_URL
        report_urls: dict[str, str] = {}
        listing_html = http_get(listing_url, timeout=timeout)
        for title, url in parse_stats_listing(listing_html, listing_url):
            report_urls[title] = url
        max_years = int(self.provider_spec.options.get("max_years", 2))
        this_year = pd.Timestamp.now().year
        for year in range(this_year, this_year - max_years, -1):
            match = re.search(
                rf'href="([^"]+)"[^>]*>\s*{year}年统计数据\s*<', listing_html
            )
            if not match:
                continue
            year_html = http_get(urljoin(listing_url, match.group(1)), timeout=timeout)
            for title, url in parse_stats_listing(year_html, listing_url):
                report_urls.setdefault(title, url)
        if not report_urls:
            raise FetchError("PBOC statistics listing contained no monthly reports")

        cumulative: dict[tuple[int, int], float | None] = {}
        for title, url in report_urls.items():
            title_match = _REPORT_TITLE_RE.search(title)
            if not title_match:
                continue
            year = int(title_match.group(1))
            month = int(title_match.group(2)) if title_match.group(2) else 6
            html = http_get(url, timeout=timeout)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            values = parse_report_cumulative(text)
            cumulative[(year, month)] = values[code]

        months = sorted(cumulative)
        dates, flows = cumulative_to_monthly(
            [m[1] for m in months],
            [m[0] for m in months],
            [cumulative[m] for m in months],
        )
        if not dates:
            raise FetchError(f"PBOC statistics reports contained no '{code}' cumulative values")
        return build_canonical_frame(
            series_id,
            [d.date() for d in dates],
            flows,
            provider=self.provider_id,
            source_file=listing_url,
            series_name=series_id,
            unit="亿元",
            frequency=spec.frequency,
            category=spec.category,
        )
