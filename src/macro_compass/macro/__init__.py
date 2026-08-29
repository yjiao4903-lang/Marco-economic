"""Macro Factor Engine (V1.5C).

Aggregates V1.5B signal outputs into the four MASTER SPEC factors
(growth / inflation / domestic_financial / global_financial) with breadth,
confidence and the growth x inflation regime. Hard constraint (ARCHITECTURE
section 9): this layer reads ONLY signal outputs - raw series never enter
this package.
"""

from macro_compass.macro.config import MacroConfigError, load_macro_config
from macro_compass.macro.factors import (
    FactorResult,
    SignalContribution,
    classify_provenance,
    compute_factor,
)
from macro_compass.macro.regime import RegimeResult, classify_regime

__all__ = [
    "FactorResult",
    "MacroConfigError",
    "RegimeResult",
    "SignalContribution",
    "classify_provenance",
    "classify_regime",
    "compute_factor",
    "load_macro_config",
]
