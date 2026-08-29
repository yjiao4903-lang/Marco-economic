"""Market Confirmation layer (V1.6A).

Computes the six MASTER SPEC market-confirmation signals (trend, percentile)
and their divergence from the fundamental macro direction. Hard constraint
(ARCHITECTURE section 10): this package READS fundamental factor outputs;
no fundamental module imports it and nothing here writes back into
Growth/Inflation. Divergence output is a confirmation observation, never a
buy/sell signal.
"""

from macro_compass.market.config import (
    DIVERGENCE_STATES,
    MarketConfigError,
    load_market_config,
)
from macro_compass.market.engine import (
    MarketConfirmation,
    classify_divergence,
    compute_market_confirmations,
    compute_market_metrics,
)

__all__ = [
    "DIVERGENCE_STATES",
    "MarketConfigError",
    "MarketConfirmation",
    "classify_divergence",
    "compute_market_confirmations",
    "compute_market_metrics",
    "load_market_config",
]
