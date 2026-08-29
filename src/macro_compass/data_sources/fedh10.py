"""Federal Reserve H.10 foreign exchange rates adapter (v0.4c Task 3).

Serves the trade-weighted BROAD dollar index (Jan-2006 = 100) from the weekly
H.10 release page:

    https://www.federalreserve.gov/releases/h10/current/default.htm

The page carries one week of daily values (Mon-Fri columns) - the adapter
parses the ``Memo: UNITED STATES DOLLAR / 1) BROAD JAN06=100`` row and the
date header. Used as X2's (USD_BROAD) FALLBACK behind FRED DTWEXBGS:
FRED remains primary; the Board has announced the Data Download Program is
being adjusted/retired, so this adapter deliberately parses the release PAGE
(not the DDP) and only the current week - no long-term DDP architecture
(task spec 47 §8).
"""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    http_get,
)

H10_CURRENT_URL = "https://www.federalreserve.gov/releases/h10/current/default.htm"

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_DATE_CELL_RE = re.compile(r"([A-Z][a-z]{2})\.?\s+(\d{1,2})")
_BROAD_ROW_RE = re.compile(r"BROAD\s+JAN06\s*=\s*100\s+((?:\d+\.\d+\s*)+)")
_RELEASE_YEAR_RE = re.compile(r"Release Date:\s*[A-Za-z]+ \d{1,2}, (\d{4})")


def parse_h10_broad(html: str) -> tuple[list, list]:
    """Parse the current H.10 release into (dates, broad index values)."""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    year_match = _RELEASE_YEAR_RE.search(text)
    if not year_match:
        raise FetchError("H.10 release date not found")
    year = int(year_match.group(1))

    header_match = re.search(r"COUNTRY\s+CURRENCY\s+((?:[A-Z][a-z]{2}\.?\s+\d{1,2}\s*)+)", text)
    if not header_match:
        raise FetchError("H.10 date header row not found")
    day_dates: list = []
    for month_abbr, day in _DATE_CELL_RE.findall(header_match.group(1)):
        month = _MONTHS.get(month_abbr)
        if month is None:
            continue
        day_dates.append(date(year, month, int(day)))

    broad = _BROAD_ROW_RE.search(text)
    if not broad:
        raise FetchError("H.10 BROAD index row not found")
    values = [float(v) for v in broad.group(1).split()]
    if not day_dates or len(values) > len(day_dates):
        raise FetchError(
            f"H.10 broad row has {len(values)} values vs {len(day_dates)} date columns"
        )
    return day_dates[: len(values)], values


class FedH10Adapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        if code.upper() != "BROAD":
            raise FetchError(f"Fed H.10 adapter has no route for '{code}'")
        html = http_get(H10_CURRENT_URL, timeout=self.provider_spec.timeout_seconds)
        dates, values = parse_h10_broad(html)
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError("H.10 returned no observations in the requested window")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=H10_CURRENT_URL,
            series_name=series_id,
            unit="index_2006_01=100",
            frequency=spec.frequency,
            category=spec.category,
        )
