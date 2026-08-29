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
