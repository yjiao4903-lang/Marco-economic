"""``config/macro.yaml`` loading with explicit validation.

The Macro Engine (V1.5B/V1.5C) keeps every tunable in this file: score
mapping scales, factor weights, confidence inputs and regime thresholds.
All values are declared priors - nothing here is fitted or searched.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CORE_FACTORS = ("growth", "inflation", "domestic_financial", "global_financial")


class MacroConfigError(Exception):
    """Raised when macro.yaml is missing, malformed or inconsistent."""


def load_macro_config(path: Path) -> dict:
    """Load and validate ``config/macro.yaml``; returns the raw mapping."""
    path = Path(path)
    if not path.exists():
        raise MacroConfigError(f"Macro config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise MacroConfigError(f"macro.yaml is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise MacroConfigError(f"macro.yaml must contain a YAML mapping: {path}")

    for section in ("score_mapping", "factor_weights", "confidence", "regime"):
        if not isinstance(data.get(section), dict):
            raise MacroConfigError(f"macro.yaml: missing or invalid section '{section}'")

    weights = data["factor_weights"]
    for factor in CORE_FACTORS:
        if factor not in weights:
            raise MacroConfigError(
                f"macro.yaml: factor_weights must declare all four core factors, "
                f"missing '{factor}'"
            )
    regime = data["regime"]
    for key in ("score_threshold", "min_breadth", "breadth_min_score"):
        if key not in regime:
            raise MacroConfigError(f"macro.yaml: regime.{key} must be declared")
    return data
