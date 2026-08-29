"""Trend transforms: level / delta / pct_change / yoy / mom / acceleration.

All functions are pure: they never modify the input series and never touch
storage or the network. Period parameters count *observations* (rows), not
calendar units - the caller declares them per series frequency.
"""

from __future__ import annotations

import pandas as pd


def level(values: pd.Series, **_params) -> pd.Series:
    """Identity transform - returns a copy of the input values."""
    return values.copy()


def delta(values: pd.Series, periods: int = 1) -> pd.Series:
    """Absolute change vs ``periods`` observations earlier."""
    if periods < 1:
        raise ValueError(f"delta periods must be >= 1, got {periods}")
    return values.diff(periods=periods)


def _validated_pct_change(values: pd.Series, periods: int) -> pd.Series:
    if periods < 1:
        raise ValueError(f"pct_change periods must be >= 1, got {periods}")
    # fill_method=None keeps NaN gaps as NaN: no implicit forward fill.
    return values.pct_change(periods=periods, fill_method=None)


def pct_change(values: pd.Series, periods: int = 1) -> pd.Series:
    """Relative change vs ``periods`` observations earlier, as a fraction."""
    return _validated_pct_change(values, periods)


def yoy(values: pd.Series, periods: int = 12) -> pd.Series:
    """Year-over-year relative change (default 12 monthly observations)."""
    return _validated_pct_change(values, periods)


def mom(values: pd.Series, periods: int = 1) -> pd.Series:
    """Month-over-month (one observation) relative change."""
    return _validated_pct_change(values, periods)


def acceleration(values: pd.Series, periods: int = 1) -> pd.Series:
    """Second difference: the change of the change over ``periods``."""
    return delta(delta(values, periods=periods), periods=periods)
