"""V1.5A transform engine tests: whitelist coverage, purity, edge cases.

Every transform gets at least two deterministic tests, including short
series, NaN and all-NaN boundaries.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_compass.transforms import (
    TRANSFORM_REGISTRY,
    UnknownTransformError,
    acceleration,
    apply_chain,
    delta,
    level,
    mom,
    moving_average,
    neutral_gap,
    pct_change,
    robust_zscore,
    rolling_mean,
    rolling_percentile,
    rolling_sum,
    yoy,
)
from macro_compass.transforms.pipeline import TransformError

# ARCHITECTURE section 7 whitelist must be fully implemented.
EXPECTED_WHITELIST = {
    "level", "delta", "pct_change", "yoy", "mom", "moving_average",
    "rolling_percentile", "robust_zscore", "neutral_gap",
    "rolling_sum", "rolling_mean", "acceleration",
}


def test_whitelist_complete() -> None:
    assert set(TRANSFORM_REGISTRY) == EXPECTED_WHITELIST


def _series(values: list[float | None]) -> pd.Series:
    index = pd.date_range("2024-01-31", periods=len(values), freq="ME")
    return pd.Series(values, index=index, dtype=float)


# --- trend.level ------------------------------------------------------------


def test_level_returns_equal_copy_and_does_not_mutate_input() -> None:
    values = _series([1.0, 2.0, 3.0])
    result = level(values)
    assert result.equals(values)
    assert result is not values
    values.iloc[0] = 99.0
    assert result.iloc[0] == 1.0


def test_level_preserves_nan_and_empty() -> None:
    nan_series = _series([np.nan, 1.0, np.nan])
    assert level(nan_series).isna().tolist() == [True, False, True]
    assert level(pd.Series(dtype=float)).empty


# --- trend.delta ------------------------------------------------------------


def test_delta_known_values() -> None:
    result = delta(_series([5.0, 7.0, 6.0, 9.0]), periods=1)
    assert result.dropna().tolist() == [2.0, -1.0, 3.0]


def test_delta_multi_period_and_short_series() -> None:
    result = delta(_series([1.0, 2.0, 3.0, 4.0, 6.0]), periods=3)
    assert result.dropna().tolist() == [3.0, 4.0]
    short = delta(_series([1.0, 2.0]), periods=3)
    assert short.isna().all()


def test_delta_all_nan() -> None:
    result = delta(_series([np.nan] * 5), periods=1)
    assert result.isna().all()


def test_delta_rejects_nonpositive_periods() -> None:
    with pytest.raises(ValueError, match="periods"):
        delta(_series([1.0, 2.0]), periods=0)


# --- trend.pct_change / yoy / mom -------------------------------------------


def test_pct_change_known_values() -> None:
    result = pct_change(_series([100.0, 110.0, 99.0]), periods=1)
    assert np.allclose(result.dropna(), [0.10, -0.10])


def test_pct_change_does_not_implicitly_fill_gaps() -> None:
    # A NaN endpoint must stay NaN (legacy pandas defaults forward filled it
    # and would silently produce a value at idx3).
    result = pct_change(_series([100.0, np.nan, 110.0, 121.0]), periods=2)
    assert result.isna().tolist() == [True, True, False, True]
    assert result.iloc[2] == pytest.approx(0.10)


def test_yoy_twelve_observations() -> None:
    values = _series([100.0] * 12 + [110.0] * 3)
    result = yoy(values)
    assert result.iloc[11] != result.iloc[11]  # NaN before a full year
    assert result.iloc[12] == pytest.approx(0.10)


def test_mom_matches_single_period_pct_change() -> None:
    values = _series([50.0, 55.0, 44.0])
    assert mom(values).dropna().equals(pct_change(values, periods=1).dropna())


# --- trend.acceleration ------------------------------------------------------


def test_acceleration_of_linear_series_is_zero() -> None:
    result = acceleration(_series([1.0, 2.0, 3.0, 4.0, 5.0]), periods=1)
    assert np.allclose(result.dropna(), [0.0, 0.0, 0.0])


def test_acceleration_known_values_and_short_series() -> None:
    result = acceleration(_series([1.0, 2.0, 4.0, 7.0]), periods=1)
    # first delta: [1, 2, 3]; second delta: [1, 1]
    assert np.allclose(result.dropna(), [1.0, 1.0])
    assert acceleration(_series([1.0, 2.0]), periods=1).isna().all()


def test_acceleration_all_nan() -> None:
    assert acceleration(_series([np.nan] * 4), periods=1).isna().all()


# --- smoothing ---------------------------------------------------------------


def test_moving_average_known_values() -> None:
    result = moving_average(_series([1.0, 2.0, 3.0, 4.0]), window=2)
    assert np.allclose(result.dropna(), [1.5, 2.5, 3.5])


def test_moving_average_nan_positions_do_not_pollute_window() -> None:
    # window=2 with min_periods=2: a NaN inside the window -> NaN result.
    result = moving_average(_series([1.0, np.nan, 3.0, 5.0]), window=2)
    assert result.isna().tolist() == [True, True, True, False]
    assert result.iloc[-1] == pytest.approx(4.0)


def test_moving_average_rejects_bad_window() -> None:
    with pytest.raises(ValueError, match="window"):
        moving_average(_series([1.0, 2.0]), window=0)


def test_rolling_mean_matches_moving_average() -> None:
    values = _series([4.0, 6.0, 2.0, 8.0, 1.0])
    assert rolling_mean(values, window=3).equals(moving_average(values, window=3))


def test_rolling_sum_known_values_and_all_nan() -> None:
    result = rolling_sum(_series([1.0, 2.0, 3.0, 4.0]), window=3)
    assert np.allclose(result.dropna(), [6.0, 9.0])
    assert rolling_sum(_series([np.nan] * 4), window=2).isna().all()


# --- stats.rolling_percentile -------------------------------------------------


def test_rolling_percentile_known_values() -> None:
    result = rolling_percentile(_series([3.0, 1.0, 2.0, 5.0, 4.0]), window=3)
    # window at idx2 is [3, 1, 2]; values <= 2 -> 2/3
    assert result.iloc[2] == pytest.approx(2.0 / 3.0)
    # window at idx3 is [1, 2, 5]; 5 is the maximum -> 1.0
    assert result.iloc[3] == pytest.approx(1.0)
    # window at idx4 is [2, 5, 4]; values <= 4 -> 2/3
    assert result.iloc[4] == pytest.approx(2.0 / 3.0)


def test_rolling_percentile_short_series_then_min_periods() -> None:
    values = _series([1.0, 2.0, 3.0])
    assert rolling_percentile(values, window=5).isna().all()
    relaxed = rolling_percentile(values, window=5, min_periods=1)
    assert relaxed.iloc[0] == pytest.approx(1.0)


def test_rolling_percentile_handles_nan() -> None:
    values = _series([1.0, np.nan, 3.0, 2.0])
    # min_periods counts non-NaN observations: with 2, windows containing
    # the NaN still evaluate (NaNs are dropped, never filled).
    result = rolling_percentile(values, window=3, min_periods=2)
    assert result.iloc[2] == pytest.approx(1.0)  # NaN dropped: [1, 3], 3 is max
    assert result.iloc[3] == pytest.approx(0.5)  # [3, 2], 2 is at the median
    # Default min_periods = window: any NaN in the window -> NaN.
    assert rolling_percentile(values, window=3).isna().all()
    assert rolling_percentile(_series([np.nan] * 4), window=2).isna().all()


# --- stats.robust_zscore -------------------------------------------------------


def test_robust_zscore_known_values() -> None:
    values = _series([1.0, 2.0, 3.0, 100.0])
    result = robust_zscore(values, window=3)
    # window [1,2,3]: median 2, MAD 1 -> (3-2)/1.4826
    assert result.iloc[2] == pytest.approx(1.0 / 1.4826)
    # window [2,3,100]: median 3, MAD 1 -> (100-3)/1.4826
    assert result.iloc[3] == pytest.approx(97.0 / 1.4826)


def test_robust_zscore_constant_series_yields_nan_not_inf() -> None:
    result = robust_zscore(_series([5.0] * 6), window=3)
    assert result.iloc[2:].isna().all()
    assert not np.isinf(result.to_numpy()).any()


def test_robust_zscore_handles_nan_and_all_nan() -> None:
    values = _series([1.0, 2.0, 3.0, np.nan, 5.0])
    result = robust_zscore(values, window=3)
    assert result.iloc[2] == pytest.approx(1.0 / 1.4826)
    assert result.iloc[3] != result.iloc[3]  # NaN input -> NaN output
    assert result.iloc[4] != result.iloc[4]  # window holds < min_periods non-NaN
    assert robust_zscore(_series([np.nan] * 5), window=3).isna().all()


def test_robust_zscore_with_relaxed_min_periods() -> None:
    values = _series([1.0, np.nan, 2.0, 4.0])
    result = robust_zscore(values, window=3, min_periods=2)
    # window [2, 4]: median 3, MAD 1 -> (4-3)/1.4826
    assert result.iloc[3] == pytest.approx(1.0 / 1.4826)


# --- stats.neutral_gap ----------------------------------------------------------


def test_neutral_gap_reference_subtracted() -> None:
    result = neutral_gap(_series([49.0, 50.0, 52.5]), reference=50.0)
    assert np.allclose(result, [-1.0, 0.0, 2.5])


def test_neutral_gap_default_zero_and_nan_preserved() -> None:
    result = neutral_gap(_series([1.5, np.nan]))
    assert result.iloc[0] == pytest.approx(1.5)
    assert result.isna().tolist() == [False, True]


# --- pipeline.apply_chain ---------------------------------------------------------


def test_apply_chain_empty_steps_returns_copy() -> None:
    values = _series([1.0, 2.0])
    result = apply_chain(values, [])
    assert result.equals(values)
    assert result is not values


def test_apply_chain_runs_steps_in_declared_order() -> None:
    values = _series([98.0, 102.0, 100.0, 106.0])
    chain = [
        {"type": "neutral_gap", "reference": 100},
        {"type": "rolling_percentile", "window": 3},
    ]
    result = apply_chain(values, chain)
    expected = rolling_percentile(neutral_gap(values, reference=100.0), window=3)
    assert np.allclose(result.dropna(), expected.dropna())


def test_apply_chain_unknown_type_lists_whitelist() -> None:
    with pytest.raises(UnknownTransformError, match="neutral_gap"):
        apply_chain(_series([1.0]), [{"type": "zscore", "window": 10}])


def test_apply_chain_invalid_params_raise_transform_error() -> None:
    with pytest.raises(TransformError, match="invalid parameters"):
        apply_chain(_series([1.0, 2.0]), [{"type": "delta", "bogus_kwarg": 1}])
    with pytest.raises(TransformError, match="failed"):
        apply_chain(_series([1.0, 2.0]), [{"type": "delta", "periods": 0}])
    with pytest.raises(TransformError, match="must be a mapping"):
        apply_chain(_series([1.0]), ["delta"])


def test_apply_chain_explicit_fill_is_respected_and_limited() -> None:
    values = _series([1.0, np.nan, np.nan, np.nan, 5.0])
    no_fill = apply_chain(values, [{"type": "level"}])
    assert no_fill.isna().sum() == 3
    filled = apply_chain(values, [{"type": "level", "fill": {"method": "ffill", "limit": 2}}])
    np.testing.assert_allclose(filled.to_numpy(), [1.0, 1.0, 1.0, np.nan, 5.0])


def test_apply_chain_fill_validation() -> None:
    values = _series([1.0, np.nan])
    with pytest.raises(TransformError, match="method"):
        apply_chain(values, [{"type": "level", "fill": {"method": "bfill", "limit": 1}}])
    with pytest.raises(TransformError, match="limit"):
        apply_chain(values, [{"type": "level", "fill": {"method": "ffill"}}])
