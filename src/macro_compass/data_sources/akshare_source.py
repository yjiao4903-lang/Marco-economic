"""AKShare adapter (V1.2A).

AKShare is an access layer, not an authoritative source; it is an optional
dependency. When it is not installed the adapter raises
``ProviderUnavailable`` and the updater reports MANUAL_REQUIRED instead of
crashing the run.

``provider_code`` is the AKShare instrument code, e.g. ``000300`` for
CSI300 (via ``index_zh_a_hist``).
"""

from __future__ import annotations

import re

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    ProviderUnavailable,
    build_canonical_frame,
)

_DATE_CANDIDATES = ("日期", "date", "DATE")
_CLOSE_CANDIDATES = ("收盘", "close", "CLOSE")

# V1.6A market-layer routes (sina-backed AKShare functions; the sina hosts are
# reachable where the eastmoney push2his primary is proxy-blocked):
_SINA_HK_INDEX_CODES = {"HSI"}                     # stock_hk_index_daily_sina
_SINA_CN_INDEX_CODES = {"sh000300", "sz399300"}    # stock_zh_index_daily
_SINA_FOREIGN_FUTURES_CODES = {"CAD"}              # LME 3M copper, futures_foreign_hist


def ensure_akshare():
    try:
        import akshare  # noqa: PLC0415 - optional dependency, imported lazily
        return akshare
    except ImportError as exc:
        raise ProviderUnavailable(
            "akshare is not installed - run 'pip install akshare' or fetch this "
            "series manually"
        ) from exc


def parse_akshare_hist(df: pd.DataFrame) -> tuple[list, list]:
    """Parse an ``index_zh_a_hist``-style DataFrame into (dates, values).

    Expects a date column (日期/date) and a close column (收盘/close).
    """
    date_col = next((c for c in df.columns if c in _DATE_CANDIDATES), None)
    close_col = next((c for c in df.columns if c in _CLOSE_CANDIDATES), None)
    if date_col is None or close_col is None:
        raise FetchError(
            f"AKShare frame has no date/close columns: {list(df.columns)}"
        )
    dates = pd.to_datetime(df[date_col], errors="coerce")
    values = pd.to_numeric(df[close_col], errors="coerce")
    mask = dates.notna() & values.notna()
    return list(dates[mask].dt.date), list(values[mask])




# ---------------------------------------------------------------------------
# China macro series (V1.2C). AKShare is the ACCESS layer (P3); the
# original_source of every routed series is the official publisher (PBOC/NBS),
# documented per series in data_sources.yaml.


def _month_cn(text: str):
    """Parse '2026年07月份' into a month-end timestamp."""
    match = re.match(r"(\d{4})年(\d{1,2})月份?", str(text).strip())
    if not match:
        return None
    return pd.Timestamp(year=int(match.group(1)), month=int(match.group(2)), day=1) + pd.offsets.MonthEnd(0)


def fetch_macro_series(akshare, code: str) -> tuple[list, list]:
    """Dispatch on the macro routing code (provider_code) and return
    (month-end dates, values)."""
    if code == "CN_PPI_YOY":
        frame = akshare.macro_china_ppi()
        col = "当月同比增长"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_M2_YOY":
        frame = akshare.macro_china_money_supply()
        col = "货币和准货币(M2)-同比增长"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_CPI_YOY":
        frame = akshare.macro_china_cpi()
        col = "全国-同比增长"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_IND_PROD_YOY":
        # NBS industrial value-added YoY via AKShare access layer
        # (upstream: eastmoney RPT_ECONOMY_INDUS_GROW, original_source NBS).
        # V1.6A G0: live input of G3 Hard Activity.
        frame = akshare.macro_china_gyzjz()
        col = "同比增长"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_RETAIL_SALES_YOY":
        # NBS total retail sales YoY via AKShare access layer
        # (upstream: eastmoney RPT_ECONOMY_TOTAL_RETAIL, original_source NBS).
        # V1.6A G0: second live input of G3 Hard Activity.
        frame = akshare.macro_china_consumer_goods_retail()
        col = "同比增长"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_TSF_TOTAL":
        frame = akshare.macro_china_shrzgm()
        col = "社会融资规模增量"
        dates = [_month_cn(v) for v in frame["月份"]]
        values = pd.to_numeric(frame[col], errors="coerce")
    elif code == "CN_DR007":
        # FDR007 fixing: depository-institution 7-day repo (the fixing of
        # DR007) - used as the history backfill of CN_DR007. The interface
        # accepts at most ~2 months per call, so fetch in quarterly chunks.
        frames = []
        end = pd.Timestamp.now().normalize()
        start = pd.Timestamp("2014-12-01")
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + pd.Timedelta(days=80), end)
            frame = akshare.repo_rate_hist(
                start_date=cursor.strftime("%Y%m%d"),
                end_date=chunk_end.strftime("%Y%m%d"),
            )
            frames.append(frame)
            cursor = chunk_end + pd.Timedelta(days=1)
        frame = pd.concat(frames, ignore_index=True).drop_duplicates(subset="date")
        dates = pd.to_datetime(frame["date"], errors="coerce")
        values = pd.to_numeric(frame["FDR007"], errors="coerce")
    else:
        raise FetchError(f"AKShare adapter has no macro route for '{code}'")
    pairs = [(d, v) for d, v in zip(dates, values) if d is not None and pd.notna(v)]
    if not pairs:
        raise FetchError(f"AKShare macro route '{code}' returned no rows")
    pairs.sort()
    return [p[0].date() if hasattr(p[0], "date") else p[0] for p in pairs], [float(p[1]) for p in pairs]


class AkshareAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        akshare = ensure_akshare()

        if code.startswith("CN_"):
            dates, values = fetch_macro_series(akshare, code)
            if start_date is not None:
                start = pd.Timestamp(start_date).date()
                keep = [i for i, d in enumerate(dates) if d >= start]
                dates = [dates[i] for i in keep]
                values = [values[i] for i in keep]
            return build_canonical_frame(
                series_id,
                dates,
                values,
                provider=self.provider_id,
                source_file=f"akshare:macro:{code}",
                series_name=series_id,
                unit="",
                frequency=spec.frequency,
                category=spec.category,
            )

        start_str = pd.Timestamp(start_date).strftime("%Y%m%d") if start_date is not None \
            else "19900101"
        end_str = pd.Timestamp(end_date).strftime("%Y%m%d") if end_date is not None \
            else pd.Timestamp.now().strftime("%Y%m%d")
        try:
            if code in _SINA_HK_INDEX_CODES:
                # V1.6A M2 fallback: HK index daily closes via sina (the
                # eastmoney push2his primary is proxy-blocked on some hosts)
                hist = akshare.stock_hk_index_daily_sina(symbol=code)
            elif code in _SINA_CN_INDEX_CODES:
                # V1.6A M1 fallback: A-share index daily closes via sina
                hist = akshare.stock_zh_index_daily(symbol=code)
            elif code in _SINA_FOREIGN_FUTURES_CODES:
                # V1.6A M6: LME 3M copper continuous forward (no contract
                # rolls -> no roll jumps); full history, filtered locally
                hist = akshare.futures_foreign_hist(symbol=code)
            else:
                hist = akshare.index_zh_a_hist(
                    symbol=code, period="daily", start_date=start_str, end_date=end_str
                )
        except Exception as exc:
            raise FetchError(f"akshare index/futures route '{code}' failed: {exc}") from exc
        if hist is None or hist.empty:
            raise FetchError(f"akshare returned no rows for '{code}'")

        dates, values = parse_akshare_hist(hist)
        if start_date is not None:
            start = pd.Timestamp(start_date).date()
            keep = [i for i, d in enumerate(dates) if d >= start]
            dates = [dates[i] for i in keep]
            values = [values[i] for i in keep]
        if not dates:
            raise FetchError(f"akshare returned no rows since {start_date} for '{code}'")
        return build_canonical_frame(
            series_id,
            dates,
            values,
            provider=self.provider_id,
            source_file=f"akshare:index_zh_a_hist:{code}",
            series_name=series_id,
            unit="",
            frequency=spec.frequency,
            category=spec.category,
        )
