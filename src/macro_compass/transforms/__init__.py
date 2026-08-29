"""Transform layer (V1.5A).

Pure, deterministic series transforms only. Every function takes a
``pd.Series`` (or DataFrame values) plus explicit parameters and returns a new
object - no network access, no database side effects, no implicit forward
fill. See ``ARCHITECTURE.md`` section 7 for the whitelist contract.
"""

from macro_compass.transforms.pipeline import (
    TRANSFORM_REGISTRY,
    UnknownTransformError,
    apply_chain,
)
from macro_compass.transforms.smoothing import moving_average, rolling_mean, rolling_sum
from macro_compass.transforms.stats import neutral_gap, robust_zscore, rolling_percentile
from macro_compass.transforms.trend import (
    acceleration,
    delta,
    level,
    mom,
    pct_change,
    yoy,
)

__all__ = [
    "TRANSFORM_REGISTRY",
    "UnknownTransformError",
    "apply_chain",
    "acceleration",
    "delta",
    "level",
    "mom",
    "moving_average",
    "neutral_gap",
    "pct_change",
    "robust_zscore",
    "rolling_mean",
    "rolling_percentile",
    "rolling_sum",
    "yoy",
]
