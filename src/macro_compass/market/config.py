"""``config/market.yaml`` loading with explicit validation (V1.6A).

Holds the Market Confirmation layer's declared priors: per-signal direction
conventions, computation windows, divergence thresholds and the macro
reference factors. Every value is validated at load time so a malformed
declaration fails loudly instead of silently changing a market read.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from macro_compass.macro.config import CORE_FACTORS

DIRECTIONS = ("positive", "negative")
MOVE_BASES = ("pct_change", "delta")
WINDOW_KEYS = ("move_1m", "move_3m", "trend_6m", "percentile")

CONFIRMED_POSITIVE = "CONFIRMED_POSITIVE"
CONFIRMED_NEGATIVE = "CONFIRMED_NEGATIVE"
POSITIVE_MACRO_DIVERGENCE = "POSITIVE_MACRO_DIVERGENCE"
NEGATIVE_MACRO_DIVERGENCE = "NEGATIVE_MACRO_DIVERGENCE"
MIXED = "MIXED"

DIVERGENCE_STATES = (
    CONFIRMED_POSITIVE,
    CONFIRMED_NEGATIVE,
    POSITIVE_MACRO_DIVERGENCE,
    NEGATIVE_MACRO_DIVERGENCE,
    MIXED,
)


class MarketConfigError(Exception):
    """Raised when market.yaml is missing, malformed or inconsistent."""


def load_market_config(path: Path) -> dict:
    """Load and validate ``config/market.yaml``; returns the raw mapping."""
    path = Path(path)
    if not path.exists():
        raise MarketConfigError(f"Market config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise MarketConfigError(f"market.yaml is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise MarketConfigError(f"market.yaml must contain a YAML mapping: {path}")

    signals = data.get("signals")
    if not isinstance(signals, dict) or not signals:
        raise MarketConfigError("market.yaml: missing or empty 'signals' section")
    for signal_id, spec in signals.items():
        if not isinstance(spec, dict):
            raise MarketConfigError(f"market.yaml: signal '{signal_id}' must be a mapping")
        if spec.get("direction") not in DIRECTIONS:
            raise MarketConfigError(
                f"market.yaml: signal '{signal_id}' must declare direction in {DIRECTIONS} "
                f"(the rising-series convention - no implicit assumptions), "
                f"got {spec.get('direction')!r}"
            )
        if spec.get("move") not in MOVE_BASES:
            raise MarketConfigError(
                f"market.yaml: signal '{signal_id}' move must be one of {MOVE_BASES} "
                "(transform whitelist), got {spec.get('move')!r}"
            )
        windows = spec.get("windows") or {}
        for key in WINDOW_KEYS:
            value = windows.get(key)
            if not isinstance(value, int) or value < 1:
                raise MarketConfigError(
                    f"market.yaml: signal '{signal_id}' windows.{key} must be a "
                    f"positive integer, got {value!r}"
                )
        thresholds = spec.get("thresholds") or {}
        trend = thresholds.get("trend_6m")
        if not isinstance(trend, (int, float)) or trend <= 0:
            raise MarketConfigError(
                f"market.yaml: signal '{signal_id}' thresholds.trend_6m must be > 0, "
                f"got {trend!r}"
            )
        references = spec.get("macro_reference")
        if (
            not isinstance(references, list)
            or not references
            or any(ref not in CORE_FACTORS for ref in references)
        ):
            raise MarketConfigError(
                f"market.yaml: signal '{signal_id}' macro_reference must be a non-empty "
                f"list of core factors {CORE_FACTORS}, got {references!r}"
            )

    thresholds = data.get("thresholds") or {}
    macro_score = thresholds.get("macro_score")
    if not isinstance(macro_score, (int, float)) or macro_score <= 0:
        raise MarketConfigError(
            f"market.yaml: thresholds.macro_score must be > 0, got {macro_score!r}"
        )
    return data
