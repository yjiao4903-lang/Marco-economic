"""Eastmoney push2his kline adapter (V1.6A Market Data Readiness).

Serves daily index / FX klines for the Market Confirmation layer from the
endpoint family verified externally on 2026-08-30 (see
docs/research/2026-08-30_market_layer_sources.md):

    GET http://push2his.eastmoney.com/api/qt/stock/kline/get
        ?secid=1.000300&klt=101&fqt=0&beg=19900101&end=20500101
        &fields1=f1,f2,f3,f4,f5,f6&fields2=f51,...,f58

``provider_code`` is the eastmoney ``secid``:
    1.000300   CSI 300 (M1)
    100.HSI    Hang Seng Index, price index not total return (M2)

KNOWN ENVIRONMENT BLOCKER: the local proxy intermittently breaks the
connection to this domain (HTTP 000 with and without --noproxy, reproduced
by the coordinator on 2026-08-30). Requests therefore bypass the ambient
proxy configuration explicitly (urllib opener with an empty ProxyHandler -
the equivalent of ``session.trust_env=False``) and every failure surfaces as
``FetchError`` so the updater tries the configured fallback (AKShare/sina)
and reports FALLBACK_USED. Silent failure is forbidden.

The kline response is a JSON document whose ``data.klines`` entries are
comma-joined rows "date,open,close,high,low,volume,amount,..." - the close
is the third field (f53).
"""

from __future__ import annotations

import json
import urllib.request

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    build_canonical_frame,
)

KLINE_URL = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
# fields2 f51..f58: date, open, close, high, low, volume, amount, amplitude
KLINE_CLOSE_COLUMN = 2

_REQUEST_HEADERS = {
    # plain browser string: CN endpoints WAF-block bot-style UAs (see base.py)
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}

# dedicated opener that ignores ambient proxy environment variables: the
# documented environment blocker is the local proxy breaking this domain
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch_kline_text(secid: str, timeout: int) -> str:
    """Fetch one kline payload with the direct (no-proxy) opener."""
    url = (
        f"{KLINE_URL}?secid={secid}&klt=101&fqt=0"
        "&beg=19900101&end=20500101"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
    )
    request = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - surfaced as the contract FetchError
        raise FetchError(f"eastmoney kline request failed for {secid}: {exc}") from exc


def parse_kline_json(text: str) -> tuple[list, list]:
    """Parse a push2his kline payload into (dates, close values)."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"eastmoney kline response is not valid JSON: {exc}") from exc
    data = (payload or {}).get("data") or {}
    rows = data.get("klines") or []
    if not rows:
        raise FetchError(f"eastmoney kline response has no rows for secid {data.get('code')!r}")
    dates, values = [], []
    for row in rows:
        parts = str(row).split(",")
        if len(parts) <= KLINE_CLOSE_COLUMN:
            continue
        parsed_date = pd.to_datetime(parts[0], errors="coerce")
        try:
            value = float(parts[KLINE_CLOSE_COLUMN])
        except ValueError:
            continue
        if pd.isna(parsed_date):
            continue
        dates.append(parsed_date.date())
        values.append(value)
    if not dates:
        raise FetchError("eastmoney kline payload contained no parseable rows")
    return dates, values


class EastmoneyAdapter(DataSourceAdapter):
    """Daily close klines by eastmoney ``secid`` (market-layer series)."""

    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        secid = self._require_code(series_id)
        text = fetch_kline_text(secid, self.provider_spec.timeout_seconds)
        dates, values = parse_kline_json(text)
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"eastmoney returned no rows since {start_date} for '{series_id}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=f"eastmoney:push2his:{secid}",
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
