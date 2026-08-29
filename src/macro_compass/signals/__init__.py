"""Signal layer foundation (V1.3).

Registry only: declares and validates the 15+6+3 signal catalogue from
``config/signals.yaml``. No scoring, no aggregation - the Signal Engine
(level/momentum scoring) arrives with V1.5B.
"""

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
    "DECLARED",
    "MISSING_INPUT",
    "PARTIAL",
    "READY",
    "SignalAvailability",
    "SignalConfigError",
    "SignalRegistry",
    "SignalSpec",
    "assess_availability",
    "load_signal_registry",
]
