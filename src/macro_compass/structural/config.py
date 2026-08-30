"""``config/structural.yaml`` loading with explicit validation (V2.6).

Holds the Structural Risk layer's declared priors: per-signal direction
convention, percentile/trend windows and the diagnostic thresholds. Every
value is validated at load time so a malformed declaration fails loudly
instead of silently changing a fragility read.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DIRECTIONS = ("positive", "negative")

# thresholds accepted by the engine's diagnostic read. S1 uses level
# thresholds (elevated / above_trend on the gap in percent); S2 uses
# percentile thresholds (elevated_percentile / moderate_percentile).
LEVEL_THRESHOLDS = ("elevated", "above_trend")
PERCENTILE_THRESHOLDS = ("elevated_percentile", "moderate_percentile")


class StructuralConfigError(Exception):
    """Raised when structural.yaml is missing, malformed or inconsistent."""


def load_structural_config(path: Path) -> dict:
    """Load and validate ``config/structural.yaml``; returns the raw mapping."""
    path = Path(path)
    if not path.exists():
        raise StructuralConfigError(f"Structural config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise StructuralConfigError(f"structural.yaml is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise StructuralConfigError(f"structural.yaml must contain a YAML mapping: {path}")

    signals = data.get("signals")
    if not isinstance(signals, dict) or not signals:
        raise StructuralConfigError("structural.yaml: missing or empty 'signals' section")
    for signal_id, spec in signals.items():
        if not isinstance(spec, dict):
            raise StructuralConfigError(f"structural.yaml: signal '{signal_id}' must be a mapping")
        if spec.get("direction") not in DIRECTIONS:
            raise StructuralConfigError(
                f"structural.yaml: signal '{signal_id}' must declare direction in "
                f"{DIRECTIONS} (the rising-series fragility convention), got {spec.get('direction')!r}"
            )
        if spec.get("placeholder"):
            # A placeholder (S3 until the B-package proxy pool lands) carries
            # no priors yet - only the direction convention stays mandatory.
            continue
        for key in ("percentile_window", "trend_quarters"):
            value = spec.get(key)
            if not isinstance(value, int) or value < 1:
                raise StructuralConfigError(
                    f"structural.yaml: signal '{signal_id}' {key} must be a positive "
                    f"integer, got {value!r}"
                )
        thresholds = spec.get("thresholds") or {}
        known = LEVEL_THRESHOLDS + PERCENTILE_THRESHOLDS
        if not thresholds or any(key not in known for key in thresholds):
            raise StructuralConfigError(
                f"structural.yaml: signal '{signal_id}' thresholds must be a non-empty "
                f"subset of {list(known)}, got {thresholds!r}"
            )
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)):
                raise StructuralConfigError(
                    f"structural.yaml: signal '{signal_id}' thresholds.{key} must be numeric, "
                    f"got {value!r}"
                )
    return data
