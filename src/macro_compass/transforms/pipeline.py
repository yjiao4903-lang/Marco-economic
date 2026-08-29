"""Transform chain pipeline (V1.5A).

Applies a declared list of transform steps, in order, to a single series.
Each step is ``{"type": <whitelisted name>, ...params}``. The pipeline is pure:
it only manipulates the passed Series. An explicit per-step
``fill: {method: ffill, limit: N}`` declaration is the only supported fill and
is applied verbatim (never implicitly).
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from macro_compass.transforms import smoothing, stats, trend

# ARCHITECTURE section 7 whitelist. Keep in sync with config/signals.yaml docs.
TRANSFORM_REGISTRY: dict[str, Callable[..., pd.Series]] = {
    "level": trend.level,
    "delta": trend.delta,
    "pct_change": trend.pct_change,
    "yoy": trend.yoy,
    "mom": trend.mom,
    "acceleration": trend.acceleration,
    "moving_average": smoothing.moving_average,
    "rolling_mean": smoothing.rolling_mean,
    "rolling_sum": smoothing.rolling_sum,
    "rolling_percentile": stats.rolling_percentile,
    "robust_zscore": stats.robust_zscore,
    "neutral_gap": stats.neutral_gap,
}

FILL_METHODS = ("ffill",)


class UnknownTransformError(ValueError):
    """Raised when a declared transform type is not in the whitelist."""


class TransformError(ValueError):
    """Raised when a declared transform step has invalid parameters."""


def _apply_fill(values: pd.Series, step: dict) -> pd.Series:
    fill = step.get("fill")
    if fill is None:
        return values
    if not isinstance(fill, dict):
        raise TransformError(f"transform '{step['type']}': fill must be a mapping, got {fill!r}")
    method = fill.get("method")
    if method not in FILL_METHODS:
        raise TransformError(
            f"transform '{step['type']}': fill method must be one of {FILL_METHODS}, got {method!r}"
        )
    limit = fill.get("limit")
    if not isinstance(limit, int) or limit < 1:
        raise TransformError(
            f"transform '{step['type']}': explicit fill requires an integer limit >= 1, got {limit!r}"
        )
    return values.ffill(limit=limit)


def apply_chain(values: pd.Series, steps: list[dict] | None) -> pd.Series:
    """Apply declared transform steps in order and return the final series.

    The input Series is never modified. ``steps=None`` or ``[]`` returns a
    plain copy. Unknown transform types and invalid parameters raise before
    any output is produced.
    """
    result = values.copy()
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict):
            raise TransformError(f"transform step #{i} must be a mapping, got {type(step).__name__}")
        transform_type = step.get("type")
        if transform_type not in TRANSFORM_REGISTRY:
            raise UnknownTransformError(
                f"transform step #{i}: unknown type '{transform_type}' - "
                f"whitelisted types: {sorted(TRANSFORM_REGISTRY)}"
            )
        params = {k: v for k, v in step.items() if k not in ("type", "fill")}
        func = TRANSFORM_REGISTRY[transform_type]
        try:
            filled = _apply_fill(result, step)
            result = func(filled, **params)
        except TypeError as exc:
            raise TransformError(
                f"transform step #{i} ('{transform_type}') has invalid parameters: {exc}"
            ) from exc
        except ValueError as exc:
            raise TransformError(f"transform step #{i} ('{transform_type}') failed: {exc}") from exc
    return result
