"""Smoothing transforms: moving_average / rolling_mean / rolling_sum.

Trailing-window only (no future peeking). Windows count observations.
"""

from __future__ import annotations

import pandas as pd


def _window(
    values: pd.Series,
    window: int,
    min_periods: int,
    centered: bool = False,
) -> pd.core.window.rolling.Rolling:
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    if min_periods < 1:
        raise ValueError(f"min_periods must be >= 1, got {min_periods}")
    return values.rolling(window=window, min_periods=min_periods, center=centered)


def moving_average(
    values: pd.Series, window: int, min_periods: int | None = None, centered: bool = False
) -> pd.Series:
    """Rolling mean; ``centered=True`` allows a centered smoothing window."""
    min_periods = window if min_periods is None else min_periods
    return _window(values, window, min_periods, centered).mean()


def rolling_mean(values: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    """Plain trailing rolling mean."""
    min_periods = window if min_periods is None else min_periods
    return _window(values, window, min_periods).mean()


def rolling_sum(values: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    """Trailing rolling sum (NaN positions never contribute)."""
    min_periods = window if min_periods is None else min_periods
    return _window(values, window, min_periods).sum()
