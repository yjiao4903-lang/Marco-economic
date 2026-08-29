"""Statistical transforms: rolling_percentile / robust_zscore / neutral_gap.

All statistics are computed on trailing windows only. NaN inputs yield NaN
outputs; nothing is filled implicitly.
"""

from __future__ import annotations

import pandas as pd

# 1.4826 = Phi(0.75) quantile of the standard normal: converts MAD to a
# consistent sigma estimate so the score is comparable to a classic z-score.
_MAD_TO_SIGMA = 1.4826


def neutral_gap(values: pd.Series, reference: float = 0.0) -> pd.Series:
    """Distance from a neutral anchor (e.g. PMI 50, CLI 100, spread 0)."""
    return values - float(reference)


def rolling_percentile(
    values: pd.Series, window: int, min_periods: int | None = None
) -> pd.Series:
    """Percentile rank (0.0-1.0) of each value within its trailing window.

    Ties count in favour of the current value (``<=``), matching the intuition
    "this reading is at or above X% of the last N observations".
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    min_periods = window if min_periods is None else min_periods

    def _rank(window_values: pd.Series) -> float:
        current = window_values.iloc[-1]
        if pd.isna(current):
            return float("nan")
        window_values = window_values.dropna()
        if window_values.empty:
            return float("nan")
        return float((window_values <= current).mean())

    return values.rolling(window=window, min_periods=min_periods).apply(
        _rank, raw=False
    )


def robust_zscore(
    values: pd.Series, window: int, min_periods: int | None = None
) -> pd.Series:
    """Rolling (x - median) / (1.4826 * MAD) over a trailing window.

    Robust to outliers, unlike a mean/std z-score. When the MAD is zero
    (degenerate window, e.g. constant series) the result is NaN instead of
    infinity.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    min_periods = max(2, window if min_periods is None else min_periods)

    rolling = values.rolling(window=window, min_periods=min_periods)
    median = rolling.median()

    def _mad(window_values: pd.Series) -> float:
        window_values = window_values.dropna()
        if window_values.empty:
            return float("nan")
        center = window_values.median()
        return float((window_values - center).abs().median())

    mad = values.rolling(window=window, min_periods=min_periods).apply(_mad, raw=False)
    sigma = mad * _MAD_TO_SIGMA
    z = (values - median) / sigma
    return z.replace([float("inf"), float("-inf")], float("nan"))
