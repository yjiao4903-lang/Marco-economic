"""Signal layer (V1.3 registry + V1.5B engine).

The registry (V1.3, frozen) declares and validates the 15+6+3 signal
catalogue from ``config/signals.yaml``. The engine (V1.5B) computes level +
momentum scores for the core signals from canonical inputs; market and
structural signals stay untouched until V1.6.
"""

from macro_compass.signals.engine import (
    CONTRACT_COLUMNS,
    SignalComputation,
    compute_core_signals,
    compute_signal,
    map_score,
    resolve_combination,
)
from macro_compass.signals.registry import (
    DECLARED,
    MISSING_INPUT,
    PARTIAL,
    READY,
    SignalAvailability,
    SignalConfigError,
    SignalRegistry,
    SignalSpec,
    assess_availability,
    load_signal_registry,
)

__all__ = [
    "CONTRACT_COLUMNS",
    "DECLARED",
    "MISSING_INPUT",
    "PARTIAL",
    "READY",
    "SignalAvailability",
    "SignalComputation",
    "SignalConfigError",
    "SignalRegistry",
    "SignalSpec",
    "assess_availability",
    "compute_core_signals",
    "compute_signal",
    "load_signal_registry",
    "map_score",
    "resolve_combination",
]
