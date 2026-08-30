"""Asset Compass layer (V2).

Maps the 7-asset pool x 15 Core Signal prior matrix (config/assets.yaml,
transcribed from docs/research/2026-08-30_R2_asset_prior_matrix.md) into
per-asset tailwind/headwind scores from the Macro Factor outputs. Pure
functions throughout; market confirmation is a parallel observation carried
but never merged into the Asset Score. Asset -> Factor -> Signal -> series ->
source traceability is preserved on every output.
"""

from macro_compass.assets.config import (
    ASSETS,
    AssetConfigError,
    load_asset_config,
)
from macro_compass.assets.engine import (
    AssetResult,
    AssetConfirmation,
    AssetSignalContribution,
    READY,
    WARMUP,
    compute_asset,
    compute_assets,
)

__all__ = [
    "ASSETS",
    "AssetConfigError",
    "AssetConfirmation",
    "AssetResult",
    "AssetSignalContribution",
    "READY",
    "WARMUP",
    "compute_asset",
    "compute_assets",
    "load_asset_config",
]