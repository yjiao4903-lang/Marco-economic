"""NBS (国家统计局) news-release adapter (V1.2C).

NBS's data portal is WAF-blocked (easyquery API returns 403), but the news
release pages (``www.stats.gov.cn/sj/zxfb/``) are plain HTML and contain the
monthly figures in prose. This adapter walks the release listing (with
pagination), fetches the articles matching each routed series, and parses the
figures out of the article text with tolerant regexes.

Parsed series semantics (documented in data_sources.yaml ``original_source``):

- ``PMI_NEW_ORDERS``      - manufacturing PMI new-orders diffusion index (%),
                            from the article's monthly sentence
- ``PMI_INPUT_PRICE``     - PMI raw-material input-price diffusion index (%),
                            from the article's 13-month breakdown table
- ``PROPERTY_SALES_AREA`` - new commercial housing floor space sold:
                            YEAR-TO-DATE cumulative YoY growth (%) exactly as
                            published (comparable growth - the frozen G4
                            declaration consumes a growth input, not a level)
- ``PROPERTY_SALES_VALUE``- same for sales value (%)
- ``CORE_CPI_YOY``        - core CPI YoY growth (%) from the CPI release /
                            interpretation article

The observation month comes from the article title (publication always lags
one month). All parser functions are pure and tested against offline HTML
fixtures.
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

LISTING_URL = "https://www.stats.gov.cn/sj/zxfb/"

# listing anchors: relative article links with a title
_ARTICLE_RE = re.compile(r'href="(\./\d{6}/t\d+[^"]*?\.html)"[^>]*>\s*([^<]{6,80}?)\s*<')

_TITLE_PATTERNS = {
    "PMI": re.compile(r"(?P<year>\d{4})年(?P<month>\d{1,2})月中国采购经理指数运行情况"),
    "PROPERTY": re.compile(r"(?P<year>\d{4})年\d{1,2}[—\-–](?P<month>\d{1,2})月份全国房地产市场基本情况"),
    "CPI": re.compile(r"(?P<year>\d{4})年(?P<month>\d{1,2})月份居民消费价格"),
}

_NEWORDERS_RE = re.compile(r"新订单指数为\s*(\d+(?:\.\d+)?)\s*%")
_INPUT_PRICE_TABLE_RE = re.compile(
    r"购进价格[\s\S]{0,200}?(?:\d{4}年\d{1,2}月\s+(?:\d+\.\d+\s*)+)+"
)
_YOY_SENTENCE_RE = re.compile(
    r"(?:同比)?(下降|上涨|增长)\s*(\d+(?:\.\d+)?)\s*%"
)
_AREA_RE = re.compile(r"新建商品房销售面积\s*[\d,，.\s]+万平方米\s*[，,]\s*")
_VALUE_RE = re.compile(r"新建商品房销售额\s*[\d,，.\s]+亿元\s*[，,]\s*")
_CORE_CPI_RE = re.compile(
    r"核心CPI[^。]{0,80}?同比(上涨|增长|下降)\s*(\d+(?:\.\d+)?)\s*%"
)

_PROVIDER_CODES = {
    "PMI_NEW_ORDERS": "PMI",
    "PMI_INPUT_PRICE": "PMI",
    "PROPERTY_SALES_AREA": "PROPERTY",
    "PROPERTY_SALES_VALUE": "PROPERTY",
    "CORE_CPI_YOY": "CPI",
}


def parse_listing(html: str) -> list[tuple[str, str]]:
    """Extract (title, relative URL) article pairs from one listing page."""
    out: dict[str, str] = {}
    for href, title in _ARTICLE_RE.findall(html):
        title = title.strip()
        if title and title not in out:
            out[title] = href
    return sorted(out.items())


def _month_end(year: int, month: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def _signed(direction: str, value: float) -> float:
    return -value if direction == "下降" else value


def strip_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _signed_yoy_after(text: str, start: int) -> float | None:
    match = _YOY_SENTENCE_RE.search(text, start)
    return _signed(match.group(1), float(match.group(2))) if match else None


def parse_pmi_new_orders(title: str, text: str) -> list[tuple[pd.Timestamp, float]]:
    """New-orders diffusion index for the article's reference month."""
    title_match = _TITLE_PATTERNS["PMI"].search(title)
    if not title_match:
        raise FetchError(f"NBS PMI article title not parseable: {title!r}")
    match = _NEWORDERS_RE.search(text)
    if not match:
        return []
    date = _month_end(int(title_match.group("year")), int(title_match.group("month")))
    return [(date, float(match.group(1)))]


def parse_pmi_input_price(text: str) -> list[tuple[pd.Timestamp, float]]:
    """Input-price index history from the article's 13-month breakdown table.

    Row values are decimal diffusion indices; requiring a decimal point keeps
    the row anchor year ("2025年") from being consumed as a value.
    """
    rows: list[tuple[pd.Timestamp, float]] = []
    # bound the search to the breakdown-table segment following each
    # "购进价格" column header (the prose around it also contains dates)
    for header_index in (m.start() for m in re.finditer("购进价格", text)):
        segment = text[header_index:header_index + 1500]
        for row in re.finditer(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s+((?:\d+\.\d+\s*)+)", segment
        ):
            year, month = int(row.group(1)), int(row.group(2))
            numbers = re.findall(r"\d+\.\d+", row.group(3))
            if numbers:
                rows.append((_month_end(year, month), float(numbers[0])))
    # later articles revise earlier months: last occurrence per date wins
    by_date = dict(rows)
    return sorted(by_date.items(), key=lambda item: item[0])


def parse_property_article(title: str, text: str) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    """Cumulative YoY for new housing sales area/value in the title month."""
    title_match = _TITLE_PATTERNS["PROPERTY"].search(title)
    if not title_match:
        raise FetchError(f"NBS property article title not parseable: {title!r}")
    date = _month_end(int(title_match.group("year")), int(title_match.group("month")))
    result: dict[str, list[tuple[pd.Timestamp, float]]] = {
        "PROPERTY_SALES_AREA": [],
        "PROPERTY_SALES_VALUE": [],
    }
    for key, prefix in (("PROPERTY_SALES_AREA", _AREA_RE), ("PROPERTY_SALES_VALUE", _VALUE_RE)):
        prefix_match = prefix.search(text)
        if prefix_match:
            yoy = _signed_yoy_after(text, prefix_match.end())
            if yoy is not None:
                result[key].append((date, yoy))
    return result


def parse_cpi_article(title: str, text: str) -> list[tuple[pd.Timestamp, float]]:
    """Core CPI YoY from a CPI release / interpretation article."""
    title_match = _TITLE_PATTERNS["CPI"].search(title)
    if not title_match:
        raise FetchError(f"NBS CPI article title not parseable: {title!r}")
    core = _CORE_CPI_RE.search(text)
    if not core:
        return []
    date = _month_end(int(title_match.group("year")), int(title_match.group("month")))
    return [(date, _signed(core.group(1), float(core.group(2))))]


_FETCH_CACHE: dict[str, str] = {}


def _cached_get(url: str, timeout: int) -> str:
    """One shared article/listing fetch per process: several series walk the
    same pages within an update run, and NBS throttles repeat requests."""
    if url not in _FETCH_CACHE:
        _FETCH_CACHE[url] = http_get(url, timeout=timeout)
    return _FETCH_CACHE[url]


class NbsAdapter(DataSourceAdapter):
    """Fetch one routed series from NBS news releases."""

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        kind = _PROVIDER_CODES.get(code)
        if kind is None:
            raise FetchError(f"NBS adapter has no parser for provider_code '{code}'")

        observations = self._collect(kind, series_id)
        if start_date is not None:
            start = pd.Timestamp(start_date)
            observations = [obs for obs in observations if obs[0] >= start]
        if not observations:
            raise FetchError(f"NBS returned no observations for '{series_id}'")

        dates = [obs[0].date() for obs in observations]
        values = [obs[1] for obs in observations]
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=LISTING_URL,
            series_name=series_id,
            unit="%",
            frequency=spec.frequency,
            category=spec.category,
        )

    def _collect(self, kind: str, series_id: str) -> list[tuple[pd.Timestamp, float]]:
        """Walk listing pages, fetch matching articles and parse them."""
        max_pages = int(self.provider_spec.options.get("max_pages", 12))
        timeout = self.provider_spec.timeout_seconds
        seen: set[str] = set()
        observations: list[tuple[pd.Timestamp, float]] = []
        for page in range(max_pages):
            url = LISTING_URL if page == 0 else f"{LISTING_URL}index_{page}.html"
            try:
                html = _cached_get(url, timeout)
            except FetchError:
                if page == 0:
                    raise
                break  # archive exhausted (older pages 404)
            for title, href in parse_listing(html):
                if title in seen or not _TITLE_PATTERNS[kind].search(title):
                    continue
                seen.add(title)
                article = strip_html(
                    _cached_get(urljoin(url, href.lstrip("./")), timeout=timeout)
                )
                if kind == "PMI" and series_id == "CHN_PMI_INPUT_PRICE":
                    observations.extend(parse_pmi_input_price(article))
                elif kind == "PMI" and series_id == "CHN_PMI_NEW_ORDERS":
                    observations.extend(parse_pmi_new_orders(title, article))
                elif kind == "PROPERTY":
                    parsed = parse_property_article(title, article)
                    key = (
                        "PROPERTY_SALES_AREA"
                        if series_id == "CN_PROPERTY_SALES_AREA"
                        else "PROPERTY_SALES_VALUE"
                    )
                    observations.extend(parsed[key])
                elif kind == "CPI":
                    observations.extend(parse_cpi_article(title, article))
        # later articles revise earlier months: last occurrence per date wins
        by_date = dict(observations)
        return sorted(by_date.items(), key=lambda obs: obs[0])
