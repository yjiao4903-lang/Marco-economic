"""Validation package (V2.5). Read-only consumer of V2 outputs; never imported
by production Asset/Macro/Market code and never writes to canonical.
"""
from macro_compass.validation.history import (
    ValidationSample,
    aligned,
    assemble,
    build_asset_panel,
    build_factor_panel,
    build_forward_returns,
    build_return_proxies,
    factor_scores_on_grid,
    forward_return_at,
    mechanism_scored_share,
)
from macro_compass.validation.methods import run_all_for_asset
from macro_compass.validation.lomo import run_lomo
from macro_compass.validation.regime_checks import run_all as run_regime_checks
from macro_compass.validation.coverage import (
    assess_backfill_gaps,
    build_coverage_matrix,
    first_score_dates,
)

__all__ = [
    "ValidationSample", "aligned", "assemble", "build_asset_panel",
    "build_factor_panel", "build_forward_returns", "build_return_proxies",
    "factor_scores_on_grid", "forward_return_at", "mechanism_scored_share",
    "run_all_for_asset",
    "run_lomo", "run_regime_checks", "assess_backfill_gaps",
    "build_coverage_matrix", "first_score_dates",
]