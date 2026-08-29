"""Canonical Parquet store (V1-03).

Canonical parquet files are the long-term, migration-safe source of truth:
``data/canonical/macro/macro.parquet`` and ``data/canonical/market/market.parquet``.
DuckDB is only a local computation cache and must always be rebuildable from
these files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from macro_compass import paths

CATEGORY_FILES = {
    "macro": paths.MACRO_PARQUET,
    "market": paths.MARKET_PARQUET,
}


def canonical_path_for(category: str) -> Path:
    try:
        return CATEGORY_FILES[category]
    except KeyError:
        raise ValueError(
            f"Unknown category '{category}' - expected one of {sorted(CATEGORY_FILES)}"
        ) from None


def read_canonical(category: str) -> pd.DataFrame:
    path = canonical_path_for(category)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def append_canonical(new_data: pd.DataFrame) -> dict[str, int]:
    """Merge canonical long-format rows into the per-category parquet files.

    Merge rule: for a duplicate (series_id, date) the row with the newer
    ``import_time`` wins, so re-exported data updates instead of duplicating.

    Returns ``{category: total_rows_written}``.
    """
    written: dict[str, int] = {}
    for category, group in new_data.groupby("category"):
        path = canonical_path_for(str(category))
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = read_canonical(str(category))
        merged = (
            pd.concat([existing, group], ignore_index=True)
            if not existing.empty
            else group.copy()
        )
        merged["_import_ts"] = pd.to_datetime(merged["import_time"])
        merged = (
            merged.sort_values("_import_ts")
            .drop_duplicates(subset=["series_id", "date"], keep="last")
            .drop(columns="_import_ts")
            .sort_values(["series_id", "date"])
            .reset_index(drop=True)
        )

        tmp = path.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp, index=False)
        tmp.replace(path)
        written[str(category)] = len(merged)
    return written


def replace_window(new_data: pd.DataFrame) -> dict[str, int]:
    """Replace canonical rows inside each fetched window, then append.

    For every (category, series_id) in ``new_data``: drop existing rows whose
    date falls inside the fetched window [min date .. max date], then add the
    fresh rows. Preserves history outside the window (older rows and any
    future rows survive; revisions are applied without duplication).
    """
    written: dict[str, int] = {}
    for category, category_group in new_data.groupby("category"):
        path = canonical_path_for(str(category))
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = read_canonical(str(category))
        if existing.empty:
            merged = category_group.copy()
        else:
            keep_mask = pd.Series(True, index=existing.index)
            for series_id, group in category_group.groupby("series_id"):
                window = (existing["series_id"] == series_id) & (
                    (existing["date"] >= group["date"].min())
                    & (existing["date"] <= group["date"].max())
                )
                keep_mask &= ~window
            merged = pd.concat([existing[keep_mask], category_group], ignore_index=True)
        merged = _normalise(merged)
        tmp = path.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp, index=False)
        tmp.replace(path)
        written[str(category)] = len(merged)
    return written


def replace_series(new_data: pd.DataFrame) -> dict[str, int]:
    """Replace the ENTIRE canonical history of the series in ``new_data``.

    Used by ``update_policy: full_refresh`` sources whose whole history is
    revised on each release (e.g. GSCPI). Rows of other series are kept.
    """
    written: dict[str, int] = {}
    for category, category_group in new_data.groupby("category"):
        path = canonical_path_for(str(category))
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = read_canonical(str(category))
        if not existing.empty:
            touched = set(category_group["series_id"].unique())
            existing = existing[~existing["series_id"].isin(touched)]
        merged = _normalise(pd.concat([existing, category_group], ignore_index=True))
        tmp = path.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp, index=False)
        tmp.replace(path)
        written[str(category)] = len(merged)
    return written


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.sort_values(["series_id", "date"])
        .drop_duplicates(subset=["series_id", "date"], keep="last")
        .reset_index(drop=True)
    )
