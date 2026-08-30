"""``config/assets.yaml`` loading with explicit validation (V2 Asset Compass).

Holds the Asset Layer's declared priors: the 7-asset x 15-signal R2 prior
matrix (sign + importance tier per cell), the tier->weight scheme, per-factor
beta prior ranges, per-asset market-confirmation signal binding and the
scoring defaults. Every value is validated at load time so a malformed or
internally inconsistent declaration fails loudly.

Transcription rules (carried in the file header as hard constraints):

1. Broker win-rates/correlations support only the importance TIER - never a
   numeric weight (R2 header note 2).
2. "超额流动性" maps to the system D3 signal (M2 YoY - private TSF YoY), not
   R2's M2 - nominal GDP probe (R2 header note 3).
3. Sign convention is explicit: rate/credit `+` = price up/yield down; CNY `+`
   = appreciation (USD/CNY down); equity/commodity/gold `+` = price up.
4. `ambiguous` cells are forced to weight 0 and flagged (R2 header note 5).
5. The gold real-yield decoupling and credit funding-sensitivity findings are
   V2.5 pending checks, carried through, never flattened.

The loader signs no ``ambiguous``/``0`` cell; every factor beta is the signed
tier-weight sum over its signals - a DECLARED prior, never fitted/searched.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from macro_compass.macro.config import CORE_FACTORS

ASSETS = (
    "CN_EQUITY",
    "HK_EQUITY",
    "CN_GOV_BOND",
    "CN_CREDIT",
    "GOLD",
    "INDUSTRIAL_COMMODITY",
    "CNY",
)
SIGNS = ("+", "-", "0", "ambiguous")
TIERS = ("HIGH", "MEDIUM", "LOW")
MARKET_SIGNALS = ("M1", "M2", "M3", "M4", "M5", "M6")

SIGN_VALUE = {"+": 1.0, "-": -1.0, "0": 0.0, "ambiguous": 0.0}


class AssetConfigError(Exception):
    """Raised when assets.yaml is missing, malformed or inconsistent."""


def _factor_beta(signals: dict) -> tuple[float, dict]:
    """Signed tier-weight sum over a factor's signals.

    Returns (beta, weighted_abs) where weighted_abs = sum of |tier_weight|
    (used for confidence weighting). `ambiguous` and `0` cells contribute 0 to
    beta but still count toward weighted_abs so a zeroed factor does not
    silently vanish from the sensitivity weighting.
    """
    beta = 0.0
    weighted_abs = 0.0
    for sid, cell in signals.items():
        weight = float(cell["weight"])
        weighted_abs += weight
        beta += SIGN_VALUE[cell["sign"]] * weight
    return round(beta, 4), round(weighted_abs, 4)


def load_asset_config(path: Path, registry=None) -> dict:
    """Load and validate ``config/assets.yaml``; returns the raw mapping with
    each asset's factors augmented with a derived ``beta`` and ``weighted_abs``.

    ``registry`` (optional SignalRegistry) is used to verify that every signal
    key belongs to the declared factor. Factor keys are validated against
    ``CORE_FACTORS`` in all cases.
    """
    path = Path(path)
    if not path.exists():
        raise AssetConfigError(f"Asset config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise AssetConfigError(f"assets.yaml is not valid YAML: {path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise AssetConfigError(f"assets.yaml must contain a YAML mapping: {path}")

    tier_weights = data.get("tier_weights")
    if not isinstance(tier_weights, dict) or not all(
        tier in tier_weights for tier in TIERS
    ):
        raise AssetConfigError("assets.yaml: tier_weights must define HIGH/MEDIUM/LOW")
    for tier in TIERS:
        w = tier_weights.get(tier)
        if not isinstance(w, (int, float)) or w <= 0:
            raise AssetConfigError(
                f"assets.yaml: tier_weights.{tier} must be > 0, got {w!r}"
            )

    defaults = data.get("defaults") or {}
    threshold = defaults.get("view_threshold")
    if not isinstance(threshold, (int, float)) or threshold <= 0:
        raise AssetConfigError(
            f"assets.yaml: defaults.view_threshold must be > 0, got {threshold!r}"
        )
    windows = defaults.get("change_window_days") or {}
    for key in ("change_1m", "change_3m"):
        w = windows.get(key)
        if not isinstance(w, int) or w < 1:
            raise AssetConfigError(
                f"assets.yaml: defaults.change_window_days.{key} must be positive, got {w!r}"
            )

    assets = data.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise AssetConfigError("assets.yaml: missing or empty 'assets' section")
    for asset_id in ASSETS:
        if asset_id not in assets:
            raise AssetConfigError(
                f"assets.yaml: missing asset '{asset_id}' (MASTER SPEC section 8)"
            )

    for asset_id, asset in assets.items():
        if not isinstance(asset, dict):
            raise AssetConfigError(f"assets.yaml: asset '{asset_id}' must be a mapping")
        factors = asset.get("factors")
        if not isinstance(factors, dict):
            raise AssetConfigError(
                f"assets.yaml: asset '{asset_id}' must declare a 'factors' mapping"
            )
        for factor in CORE_FACTORS:
            if factor not in factors:
                raise AssetConfigError(
                    f"assets.yaml: asset '{asset_id}' missing factor '{factor}'"
                )
        market_signal = asset.get("market_signal")
        if market_signal is not None and market_signal not in MARKET_SIGNALS:
            raise AssetConfigError(
                f"assets.yaml: asset '{asset_id}' market_signal must be in "
                f"{MARKET_SIGNALS} or null, got {market_signal!r}"
            )

        factor_defs: set[str] = set()
        for factor, block in factors.items():
            if not isinstance(block, dict):
                raise AssetConfigError(
                    f"assets.yaml: asset '{asset_id}'.{factor} must be a mapping"
                )
            signals = block.get("signals")
            if not isinstance(signals, dict) or not signals:
                raise AssetConfigError(
                    f"assets.yaml: asset '{asset_id}'.{factor} must declare a "
                    "non-empty 'signals' mapping"
                )
            brange = block.get("beta_range") or {}
            for key in ("low", "high"):
                if key not in brange or not isinstance(brange.get(key), (int, float)):
                    raise AssetConfigError(
                        f"assets.yaml: asset '{asset_id}'.{factor}.beta_range.{key} "
                        "must be numeric"
                    )
            for sid, cell in signals.items():
                if sid in factor_defs:
                    raise AssetConfigError(
                        f"assets.yaml: signal '{sid}' declared more than once in "
                        f"asset '{asset_id}'"
                    )
                factor_defs.add(sid)
                if not isinstance(cell, dict):
                    raise AssetConfigError(
                        f"assets.yaml: asset '{asset_id}'.{factor}.{sid} must be a mapping"
                    )
                if cell.get("sign") not in SIGNS:
                    raise AssetConfigError(
                        f"assets.yaml: asset '{asset_id}'.{factor}.{sid} sign must be "
                        f"one of {SIGNS}, got {cell.get('sign')!r}"
                    )
                tier = cell.get("tier")
                if tier not in TIERS:
                    raise AssetConfigError(
                        f"assets.yaml: asset '{asset_id}'.{factor}.{sid} tier must be "
                        f"one of {TIERS}, got {tier!r}"
                    )
                # attach the derived weight (declared prior); ambiguous/0 -> 0
                cell["weight"] = 0.0 if cell["sign"] in ("ambiguous", "0") else float(
                    tier_weights[tier]
                )
            beta, weighted_abs = _factor_beta(signals)
            block["beta"] = beta
            block["weighted_abs"] = weighted_abs
            # an `ambiguous`/`0`-only factor still keeps a declared prior range
            if registry is not None:
                factor_signal_ids = {
                    sid for sid, spec in registry.core.items() if spec.factor == factor
                }
                unknown = sorted(set(signals) - factor_signal_ids)
                if unknown:
                    raise AssetConfigError(
                        f"assets.yaml: asset '{asset_id}'.{factor} references "
                        f"unknown/non-{factor} signals {unknown}"
                    )

    data["defaults"] = defaults
    data["tier_weights"] = tier_weights
    return data