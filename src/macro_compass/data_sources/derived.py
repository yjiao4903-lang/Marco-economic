"""Fail-closed, non-imputing derived macro diagnostics.

The functions in this module consume already-routed canonical legs.  They do
not fetch data, write storage, alter signal weights, or change allocation
behavior.  The Treasury curve diagnostic requires an exact-date intersection;
the DR007 diagnostic uses a causally bounded policy step as documented below.
"""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from macro_compass.data_sources.base import build_canonical_frame
from macro_compass.data_sources.registry import DataSourcesConfig


class DerivedSeriesError(ValueError):
    """Raised when a derived diagnostic cannot be built safely."""


_LEG_REQUIRED_COLUMNS = {
    "series_id",
    "date",
    "value",
    "unit",
    "observation_date",
    "release_at",
    "available_at",
}


def _decision_time_utc(decision_time) -> pd.Timestamp | None:
    if decision_time is None:
        return None
    timestamp = pd.Timestamp(decision_time)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise DerivedSeriesError(
            "decision_time must be a timezone-aware timestamp; refusing an "
            "ambiguous PIT cutoff"
        )
    return timestamp.tz_convert("UTC")


def _require_timezone_aware(frame: pd.DataFrame, column: str, series_id: str) -> None:
    naive = 0
    for value in frame[column].dropna():
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError):
            continue
        if timestamp.tzinfo is None:
            naive += 1
    if naive:
        raise DerivedSeriesError(
            f"{series_id}: {column} contains {naive} timezone-naive row(s)"
        )


def _prepare_leg(
    frame: pd.DataFrame,
    series_id: str,
    *,
    decision_time: pd.Timestamp | None,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise DerivedSeriesError(f"{series_id}: source leg is empty")
    missing = sorted(_LEG_REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise DerivedSeriesError(
            f"{series_id}: source leg missing temporal/unit column(s): {missing}"
        )

    leg = frame.loc[frame["series_id"].eq(series_id)].copy()
    if leg.empty:
        raise DerivedSeriesError(f"{series_id}: source leg has no matching series_id rows")

    _require_timezone_aware(leg, "release_at", series_id)
    _require_timezone_aware(leg, "available_at", series_id)
    leg["_date"] = pd.to_datetime(leg["date"], errors="coerce").dt.normalize()
    leg["_observation_date"] = pd.to_datetime(
        leg["observation_date"], errors="coerce"
    ).dt.normalize()
    leg["_release_at"] = pd.to_datetime(leg["release_at"], errors="coerce", utc=True)
    leg["_available_at"] = pd.to_datetime(
        leg["available_at"], errors="coerce", utc=True
    )
    leg["_value"] = pd.to_numeric(leg["value"], errors="coerce")

    invalid = (
        leg["_date"].isna()
        | leg["_observation_date"].isna()
        | leg["_release_at"].isna()
        | leg["_available_at"].isna()
        | leg["_value"].isna()
    )
    if invalid.any():
        raise DerivedSeriesError(
            f"{series_id}: {int(invalid.sum())} row(s) have invalid date, value, "
            "or temporal metadata"
        )
    if not leg["_date"].eq(leg["_observation_date"]).all():
        raise DerivedSeriesError(
            f"{series_id}: date and observation_date are not identical"
        )
    if (leg["_available_at"] < leg["_release_at"]).any():
        raise DerivedSeriesError(f"{series_id}: available_at precedes release_at")
    observation_start = pd.to_datetime(leg["_date"], utc=True)
    if (leg["_available_at"] < observation_start).any():
        raise DerivedSeriesError(f"{series_id}: available_at precedes observation date")
    try:
        finite = leg["_value"].map(lambda value: math.isfinite(float(value))).all()
    except (TypeError, ValueError, OverflowError):
        finite = False
    if not finite:
        raise DerivedSeriesError(f"{series_id}: source leg contains non-finite values")

    if decision_time is not None:
        leg = leg.loc[leg["_available_at"].le(decision_time)].copy()
    if leg.empty:
        raise DerivedSeriesError(
            f"{series_id}: no observations were available by the decision_time"
        )
    if leg["_date"].duplicated().any():
        raise DerivedSeriesError(
            f"{series_id}: duplicate observations remain for an exact join date"
        )
    return leg[["_date", "_value", "unit", "_release_at", "_available_at"]]


def _check_unit(prepared: pd.DataFrame, series_id: str, expected_unit: str) -> None:
    units = set(prepared["unit"].dropna().astype(str))
    if units != {expected_unit}:
        raise DerivedSeriesError(
            f"{series_id}: unit must be {expected_unit!r}, got {sorted(units)}"
        )


def derive_difference(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    output_series_id: str,
    left_series_id: str,
    right_series_id: str,
    output_name: str,
    expected_unit: str,
    frequency: str,
    category: str,
    decision_time=None,
) -> pd.DataFrame:
    """Return ``left - right`` on an exact, PIT-safe date intersection."""
    cutoff = _decision_time_utc(decision_time)
    left_prepared = _prepare_leg(left, left_series_id, decision_time=cutoff)
    right_prepared = _prepare_leg(right, right_series_id, decision_time=cutoff)

    _check_unit(left_prepared, left_series_id, expected_unit)
    _check_unit(right_prepared, right_series_id, expected_unit)

    joined = left_prepared.merge(
        right_prepared,
        on="_date",
        how="inner",
        suffixes=("_left", "_right"),
        validate="one_to_one",
    )
    if joined.empty:
        raise DerivedSeriesError(
            f"{output_series_id}: no exact-date overlap between {left_series_id} "
            f"and {right_series_id}; no fill or nearest-date join is allowed"
        )

    values = joined["_value_left"] - joined["_value_right"]
    if not values.map(lambda value: math.isfinite(float(value))).all():
        raise DerivedSeriesError(f"{output_series_id}: derived values are non-finite")
    release_at = joined["_release_at_left"].where(
        joined["_release_at_left"].ge(joined["_release_at_right"]),
        joined["_release_at_right"],
    )
    available_at = joined["_available_at_left"].where(
        joined["_available_at_left"].ge(joined["_available_at_right"]),
        joined["_available_at_right"],
    )
    dates = joined["_date"].dt.date.tolist()
    return build_canonical_frame(
        output_series_id,
        dates,
        values.tolist(),
        provider="MARCO_DERIVED",
        source_file=f"derived:{left_series_id}-{right_series_id}",
        series_name=output_name,
        unit=expected_unit,
        frequency=frequency,
        category=category,
        observation_dates=dates,
        release_at=release_at.tolist(),
        available_at=available_at.tolist(),
    )


def derive_cn_dr007_spread(
    dr007: pd.DataFrame,
    policy_rate: pd.DataFrame,
    *,
    decision_time=None,
    output_name: str = "DR007-7天政策利率利差",
) -> pd.DataFrame:
    """Derive DR007 minus the latest causally published policy step.

    The policy leg is selected with a backward as-of join on ``available_at``
    for each DR007 row.  This preserves the policy step across dates while
    refusing to use a policy observation that was published after that row.
    """
    cutoff = _decision_time_utc(decision_time)
    dr = _prepare_leg(dr007, "CN_DR007", decision_time=cutoff)
    policy = _prepare_leg(policy_rate, "CN_POLICY_RATE_7D", decision_time=cutoff)
    _check_unit(dr, "CN_DR007", "percent")
    _check_unit(policy, "CN_POLICY_RATE_7D", "percent")

    if policy["_available_at"].duplicated().any():
        raise DerivedSeriesError(
            "CN_POLICY_RATE_7D: duplicate publication timestamps prevent a "
            "deterministic as-of selection"
        )
    selected_policy = []
    for _, dr_row in dr.sort_values("_date").iterrows():
        candidates = policy.loc[policy["_date"].le(dr_row["_date"])]
        if cutoff is None:
            candidates = candidates.loc[
                candidates["_available_at"].le(dr_row["_available_at"])
            ]
        if candidates.empty:
            raise DerivedSeriesError(
                "CN_DR007_SPREAD: a DR007 row has no policy value published by "
                "its decision time"
            )
        selected_policy.append(candidates.sort_values(["_date", "_available_at"]).iloc[-1])

    selected = pd.DataFrame(selected_policy).reset_index(drop=True)
    dr = dr.sort_values("_date").reset_index(drop=True)
    values = dr["_value"] - selected["_value"]
    if not values.map(lambda value: math.isfinite(float(value))).all():
        raise DerivedSeriesError("CN_DR007_SPREAD: derived values are non-finite")
    release_at = dr["_release_at"].where(
        dr["_release_at"].ge(selected["_release_at"]),
        selected["_release_at"],
    )
    available_at = dr["_available_at"].where(
        dr["_available_at"].ge(selected["_available_at"]),
        selected["_available_at"],
    )
    dates = dr["_date"].dt.date.tolist()
    return build_canonical_frame(
        "CN_DR007_SPREAD",
        dates,
        values.tolist(),
        provider="MARCO_DERIVED",
        source_file="derived:CN_DR007-CN_POLICY_RATE_7D",
        series_name=output_name,
        unit="percent",
        frequency="daily",
        category="macro",
        observation_dates=dates,
        release_at=release_at.tolist(),
        available_at=available_at.tolist(),
    )


def derive_us_10y2y_spread(
    nominal_10y: pd.DataFrame,
    nominal_2y: pd.DataFrame,
    *,
    decision_time=None,
    output_name: str = "美国10年-2年期国债收益率利差",
) -> pd.DataFrame:
    return derive_difference(
        nominal_10y,
        nominal_2y,
        output_series_id="US_10Y2Y_SPREAD",
        left_series_id="US_TREASURY_NOMINAL_YIELD_10Y",
        right_series_id="US_TREASURY_NOMINAL_YIELD_2Y",
        output_name=output_name,
        expected_unit="percent",
        frequency="daily",
        category="macro",
        decision_time=decision_time,
    )


def derive_configured_series(
    series_id: str,
    frames_by_id: Mapping[str, pd.DataFrame],
    config: DataSourcesConfig,
    indicators: Mapping[str, object] | None = None,
    *,
    decision_time=None,
) -> pd.DataFrame:
    """Build one configured diagnostic without persisting or engine wiring."""
    spec = config.derived_series.get(series_id)
    if spec is None:
        raise DerivedSeriesError(f"'{series_id}' is not a configured derived series")
    if len(spec.legs) != 2:
        raise DerivedSeriesError(f"{series_id}: exactly two legs are required")
    missing = [leg for leg in spec.legs if leg not in frames_by_id]
    if missing:
        raise DerivedSeriesError(f"{series_id}: missing source frame(s): {missing}")
    output_cfg = indicators.get(series_id) if indicators else None
    output_name = getattr(output_cfg, "name", series_id)
    if series_id == "CN_DR007_SPREAD":
        return derive_cn_dr007_spread(
            frames_by_id[spec.legs[0]],
            frames_by_id[spec.legs[1]],
            decision_time=decision_time,
            output_name=output_name,
        )
    if series_id == "US_10Y2Y_SPREAD":
        return derive_us_10y2y_spread(
            frames_by_id[spec.legs[0]],
            frames_by_id[spec.legs[1]],
            decision_time=decision_time,
            output_name=output_name,
        )
    return derive_difference(
        frames_by_id[spec.legs[0]],
        frames_by_id[spec.legs[1]],
        output_series_id=series_id,
        left_series_id=spec.legs[0],
        right_series_id=spec.legs[1],
        output_name=output_name,
        expected_unit=spec.unit,
        frequency=spec.frequency,
        category=spec.category,
        decision_time=decision_time,
    )
