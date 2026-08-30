"""Structural Risk layer (V2.6).

Computes the three MASTER SPEC structural fragility signals (S1 / S2 / S3) as
medium/long-term diagnostics. Hard constraint (MASTER SPEC section 7): the
Structural Risk layer NEVER enters the short-term Asset Score - the asset
engine only reads the four core factor outputs and never imports this package.
Output is a diagnostic status + latest values; no-data / stale observations
surface as NO_SIGNAL, never synthetic.
"""

from macro_compass.structural.config import (
    StructuralConfigError,
    load_structural_config,
)
from macro_compass.structural.engine import (
    MISSING_INPUT,
    PARTIAL,
    READY,
    StructuralReading,
    WARMUP,
    compute_structural_readings,
)

__all__ = [
    "MISSING_INPUT",
    "PARTIAL",
    "READY",
    "StructuralConfigError",
    "StructuralReading",
    "WARMUP",
    "compute_structural_readings",
    "load_structural_config",
]
