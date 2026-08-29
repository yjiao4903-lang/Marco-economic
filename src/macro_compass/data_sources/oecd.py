"""OECD adapter (V1.2A).

Reads the OECD SDMX REST API (keyless) and returns the CSV flavour:

    https://sdmx.oecd.org/public/rest/data/{flowRef}/{key}?format=csvfilewithlabels

``provider_code`` is the full ``flowRef/key`` string, e.g.::

    OECD.SDD.STES,DSD_KEI@DF_KEI,4.0/CHN.M.LI.IX._T.AA.

Monthly periods (``2026-05``) are dated to the first day of the month, which
becomes the canonical observation date.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
    build_url,
    http_get,
)

OECD_DATA_URL = "https://sdmx.oecd.org/public/rest/data"

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")


def build_oecd_url(code: str, start_date=None, end_date=None) -> str:
    params = {"format": "csvfilewithlabels"}
    if start_date is not None:
        params["startPeriod"] = pd.Timestamp(start_date).date().isoformat()
    if end_date is not None:
        params["endPeriod"] = pd.Timestamp(end_date).date().isoformat()
    return build_url(f"{OECD_DATA_URL}/{code}", params)


def period_to_date(value: str):
    """``2026-05`` / ``2026-05-01`` / ``2026-05-01T00:00:00`` -> ``date``."""
    match = _PERIOD_RE.match(str(value).strip())
    if not match:
        return None
    year, month, day = int(match[1]), int(match[2]), int(match[3] or 1)
    try:
        return pd.Timestamp(year=year, month=month, day=day).date()
    except ValueError:
        return None


def parse_sdmx_csv(text: str) -> tuple[list, list]:
    """Parse an SDMX-CSV payload into (dates, values).

    Uses the ``TIME_PERIOD`` and ``OBS_VALUE`` columns. Duplicate dates (the
    API returns multiple rows when trailing key dimensions are wildcards)
    keep the last occurrence.
    """
    df = pd.read_csv(io.StringIO(text))
    for column in ("TIME_PERIOD", "OBS_VALUE"):
        if column not in df.columns:
            raise FetchError(f"SDMX CSV is missing column '{column}': {list(df.columns)}")

    parsed = df["TIME_PERIOD"].map(period_to_date)
    values = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    frame = pd.DataFrame({"date": parsed, "value": values}).dropna()
    frame = frame.drop_duplicates(subset="date", keep="last").sort_values("date")
    return list(frame["date"]), list(frame["value"])


class OecdAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        url = build_oecd_url(code, start_date, end_date)
        text = http_get(url, timeout=self.provider_spec.timeout_seconds)
        dates, values = parse_sdmx_csv(text)
        if not dates:
            raise FetchError(f"OECD returned no usable observations for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=url,
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
