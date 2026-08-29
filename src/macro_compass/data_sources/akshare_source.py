"""AKShare adapter (V1.2A).

AKShare is an access layer, not an authoritative source; it is an optional
dependency. When it is not installed the adapter raises
``ProviderUnavailable`` and the updater reports MANUAL_REQUIRED instead of
crashing the run.

``provider_code`` is the AKShare instrument code, e.g. ``000300`` for
CSI300 (via ``index_zh_a_hist``).
"""

from __future__ import annotations

import pandas as pd

from macro_compass.data_sources.base import (
    DataSourceAdapter,
    FetchError,
    ProviderUnavailable,
    build_canonical_frame,
)

_DATE_CANDIDATES = ("日期", "date", "DATE")
_CLOSE_CANDIDATES = ("收盘", "close", "CLOSE")


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


class AkshareAdapter(DataSourceAdapter):
    def fetch(self, series_id: str, start_date=None, end_date=None) -> pd.DataFrame:
        spec = self._require_series(series_id)
        code = self._require_code(series_id)
        akshare = ensure_akshare()

        start_str = pd.Timestamp(start_date).strftime("%Y%m%d") if start_date is not None \
            else "19900101"
        end_str = pd.Timestamp(end_date).strftime("%Y%m%d") if end_date is not None \
            else pd.Timestamp.now().strftime("%Y%m%d")
        try:
            hist = akshare.index_zh_a_hist(
                symbol=code, period="daily", start_date=start_str, end_date=end_str
            )
        except Exception as exc:
            raise FetchError(f"akshare index_zh_a_hist('{code}') failed: {exc}") from exc
        if hist is None or hist.empty:
            raise FetchError(f"akshare returned no rows for '{code}'")

        dates, values = parse_akshare_hist(hist)
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
