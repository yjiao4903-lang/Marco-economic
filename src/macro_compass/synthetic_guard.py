"""Synthetic data isolation (V1.2C).

Production calculation (signal scoring, factor aggregation, reports) must
never consume synthetic fixture rows. Canonical may contain synthetic rows
(they enter via the Wind importer when the sample fixture is imported), so
the filter is ROW-level: a canonical row is synthetic when its
``source_file`` matches one of the synthetic markers declared in
``config/macro.yaml`` (``synthetic_markers``).

The production entry points default to ``allow_synthetic=False``; tests can
opt in explicitly with ``--allow-synthetic``. There is no silent fallback:
when a production calculation would silently fall back to synthetic rows,
the filter drops them instead and the missing data becomes visible.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

SYNTHETIC_LABEL = "synthetic"
REAL_LABEL = "real"


def is_synthetic(source_file: str, markers: Iterable[str]) -> bool:
    """True when the row's source_file carries a synthetic marker."""
    name = str(source_file or "").lower()
    return any(str(marker).lower() in name for marker in markers)


def filter_synthetic(
    frame: pd.DataFrame, markers: Iterable[str], allow_synthetic: bool = False
) -> pd.DataFrame:
    """Drop synthetic rows from a canonical frame unless explicitly allowed.

    Production entry points call this with ``allow_synthetic=False`` (the
    default) before feeding the signal engine. Missing inputs stay missing -
    they are never back-filled from synthetic data.
    """
    if allow_synthetic or frame.empty or not list(markers):
        return frame
    if "source_file" not in frame.columns:
        return frame
    mask = frame["source_file"].map(lambda f: not is_synthetic(f, markers))
    return frame[mask].reset_index(drop=True)
