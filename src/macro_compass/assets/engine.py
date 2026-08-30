"""Asset Compass engine (V2): 7-asset tailwind/headwind scores.

Pure functions throughout: the Macro Factor outputs (``macro.factors``) and the
Market Confirmation outputs (``market.engine``) go in, results come out - no
network, no storage side effects, no modification of any fundamental or market
input.

Hard constraints (MASTER SPEC 13, ARCHITECTURE 11, task spec 55):

* Asset score = sum over the four core factors of (normalised factor beta x
  factor score). The betas are DECLARED PRIORS transcribed from the R2 matrix
  (config/assets.yaml) - never fitted, never searched, and the asset's own
  price never enters its score (ARCHITECTURE 11).
* View text is tailwind / headwind / neutral ONLY - never buy/sell/position.
* Market confirmation is carried as a PARALLEL observation (asset ->
  market_signal binding) and is never merged into the Asset Score weighting.
* Confidence is a data-quality description (coverage / freshness /
  source_quality), not a forecast probability.

Isolation: this module READS factor outputs and (for the 1M/3M change) the
read-only factor engine. It never imports the market package to save or change
anything - it only reads the confirmation results it is handed. Nothing here
writes back into Growth/Inflation or any market state.

Support for an optional ``factor_signal_ids`` (registry factor -> [core signal
ids]) reconstructs each factor's score at 1M/3M ago through the frozen
``macro.factors.compute_factor`` (read-only) so the asset's "1M / 3M change"
is the change in its own tailwind score over those horizons.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional

import pandas as pd

from macro_compass.macro.config import CORE_FACTORS

# View words - tailwind/headwind only, no buy/sell/position vocabulary.
VIEW_TAILWIND = "顺风"
VIEW_NEUTRAL = "中性"
VIEW_HEADWIND = "逆风"

READY = "READY"
WARMUP = "WARMUP"


@dataclass
class AssetSignalContribution:
    """One signal's additive contribution to an asset, fully traceable.

    ``contribution`` is in additive asset-score points: its sum across a
    factor equals that factor's contribution, and the grand total equals the
    asset score. ``inputs`` maps series_id -> canonical source (provider) so
    Asset -> Factor -> Signal -> series -> source stays open.
    """

    factor: str
    score: Optional[float]
    contribution: Optional[float]
    inputs: dict  # series_id -> source (provider)


@dataclass
class AssetConfirmation:
    """The asset's market-confirmation observation (parallel, NOT scored)."""

    signal_id: str
    state: Optional[str]
    status: str
    macro_direction: int
    market_direction: int
    agreement: Optional[str]


@dataclass
class AssetResult:
    """The eight-field output contract of one asset (task spec 55 scope)."""

    asset: str
    name: str
    status: str
    score: Optional[float]
    view: Optional[str]
    change_1m: Optional[float]
    change_3m: Optional[float]
    factor_contributions: dict  # factor -> additive asset-score points
    signal_contributions: dict[str, AssetSignalContribution]
    beta: dict  # factor -> raw declared prior beta
    beta_normalized: dict  # factor -> L1-normalised beta
    market_confirmation: Optional[AssetConfirmation]
    confidence: dict[str, float]  # coverage/freshness/source_quality/composite
    asof: Optional[pd.Timestamp]
    scored_factors: list


def _normalize_betas(asset_cfg: Mapping) -> tuple[dict, dict]:
    beta = {f: float(asset_cfg["factors"][f]["beta"]) for f in CORE_FACTORS}
    norm = {f: 0.0 for f in CORE_FACTORS}
    total = sum(abs(b) for b in beta.values())
    if total > 0:
        for f in CORE_FACTORS:
            norm[f] = beta[f] / total
    return beta, norm


def _factor_scores_at(
    computations: Mapping[str, object],
    factor_signal_ids: Mapping[str, list[str]],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    horizon: pd.Timestamp,
) -> dict[str, Optional[float]]:
    """All four factors' scores as of ``horizon`` by re-running the frozen
    read-only factor engine on signal frames truncated to that date. Computed
    ONCE (shared across assets) so the 1M/3M change is cheap."""
    from macro_compass.macro.factors import compute_factor

    truncated = {
        sid: replace(comp, frame=comp.frame[comp.frame["date"] <= horizon])
        if not comp.frame.empty
        else comp
        for sid, comp in computations.items()
    }
    out: dict[str, Optional[float]] = {}
    for f in CORE_FACTORS:
        if not factor_signal_ids.get(f):
            out[f] = None
            continue
        out[f] = compute_factor(
            f, factor_signal_ids[f], truncated, macro_config, staleness, horizon
        ).score
    return out


def compute_horizon_scores(
    computations: Mapping[str, object],
    factor_signal_ids: Mapping[str, list[str]],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    today: pd.Timestamp,
    window_1m: int,
    window_3m: int,
) -> dict[str, dict[str, Optional[float]]]:
    """Factor scores at ``today - window_1m`` and ``today - window_3m``,
    shared by every asset for its 1M / 3M change."""
    today = pd.Timestamp(today)
    return {
        "1m": _factor_scores_at(
            computations, factor_signal_ids, macro_config, staleness,
            today - pd.Timedelta(days=window_1m),
        ),
        "3m": _factor_scores_at(
            computations, factor_signal_ids, macro_config, staleness,
            today - pd.Timedelta(days=window_3m),
        ),
    }


def _score_from_factor_map(
    norm: Mapping[str, float],
    factor_scores: Mapping[str, Optional[float]],
) -> Optional[float]:
    """Asset score reconstructed from a per-factor score map at a horizon."""
    points = []
    for f in CORE_FACTORS:
        v = factor_scores.get(f)
        if v is not None and abs(norm.get(f, 0.0)) > 0:
            points.append(norm[f] * float(v))
    return float(sum(points)) if points else None


def compute_asset(
    asset_id: str,
    asset_cfg: Mapping,
    factor_results: Mapping[str, object],
    computations: Mapping[str, object],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    today: pd.Timestamp,
    defaults: Optional[Mapping] = None,
    factor_signal_ids: Optional[Mapping[str, list[str]]] = None,
    market_confirmations: Optional[Mapping[str, object]] = None,
    horizon_scores: Optional[Mapping[str, Mapping[str, Optional[float]]]] = None,
) -> AssetResult:
    """Score one asset from factor outputs (read-only). Pure function."""
    today = pd.Timestamp(today)
    factor_signal_ids = factor_signal_ids or {}
    asset_defaults = {**(defaults or {}), **asset_cfg.get("defaults", {})}
    view_threshold = float(asset_defaults.get("view_threshold", 0.15))
    min_scored = int(asset_defaults.get("min_scored_factors", 1))

    beta, norm = _normalize_betas(asset_cfg)

    scored_factors = [
        f
        for f in CORE_FACTORS
        if factor_results.get(f) is not None
        and factor_results[f].score is not None
        and abs(norm[f]) > 0
    ]
    factor_contributions = {f: None for f in CORE_FACTORS}
    for f in scored_factors:
        factor_contributions[f] = norm[f] * float(factor_results[f].score)

    status = READY
    score: Optional[float] = None
    if len(scored_factors) < min_scored:
        status = WARMUP
    else:
        score = float(sum(factor_contributions[f] for f in scored_factors))

    view: Optional[str] = None
    if status == READY and score is not None:
        if abs(score) >= view_threshold:
            view = VIEW_TAILWIND if score > 0 else VIEW_HEADWIND
        else:
            view = VIEW_NEUTRAL

    # signal-level additive contributions, fully traceable to provider.
    # Only the asset's ACTIVE (non-zero prior) signals are attributed: an
    # `ambiguous`/`0` cell (weight 0) contributes nothing to this asset, by
    # rule 4. The macro factor score is apportioned among the active scored
    # signals (re-scaled so the attributions still sum to the factor's
    # contribution to this asset - additive and consistent).
    signal_contributions: dict[str, AssetSignalContribution] = {}
    for f in scored_factors:
        fr = factor_results[f]
        factor_score = float(fr.score)
        active_ids = {
            sid
            for sid, cell in asset_cfg["factors"][f]["signals"].items()
            if cell["sign"] in ("+", "-")
        }
        pool = {
            sid: fc
            for sid, fc in fr.signals.items()
            if sid in active_ids and fc.contribution is not None
        }
        pool_total = sum(fc.contribution for fc in pool.values())
        if not pool or not pool_total:
            continue
        factor_part = (norm[f] * factor_score) / pool_total
        for sid, fc in pool.items():
            signal_contributions[sid] = AssetSignalContribution(
                factor=f,
                score=fc.score,
                contribution=factor_part * fc.contribution,
                inputs=dict(fc.inputs),
            )

    # 1M / 3M change of the asset score from the shared horizon factor scores
    # (reconstructed read-only via the frozen factor engine, once for all
    # assets). horizon_scores keys: "1m" / "3m" -> {factor: score}.
    change_1m = change_3m = None
    if status == READY and score is not None and horizon_scores:
        h1m, h3m = (horizon_scores or {}).get("1m"), (horizon_scores or {}).get("3m")
        s1 = _score_from_factor_map(norm, h1m) if h1m else None
        s3 = _score_from_factor_map(norm, h3m) if h3m else None
        change_1m = score - s1 if s1 is not None else None
        change_3m = score - s3 if s3 is not None else None

    # confidence = data-quality (three components), weighted by |norm beta|
    # over the contributing factors - never a forecast probability.
    confidence = {
        "coverage": 0.0,
        "freshness": 0.0,
        "source_quality": _default_source_quality(macro_config),
        "composite": 0.0,
    }
    if scored_factors:
        w = sum(abs(norm[f]) for f in scored_factors)
        if w > 0:
            agg = {
                key: sum(
                    abs(norm[f]) * float(factor_results[f].confidence.get(key, 0.0))
                    for f in scored_factors
                )
                / w
                for key in ("coverage", "freshness", "source_quality")
            }
            agg["composite"] = (agg["coverage"] + agg["freshness"] + agg["source_quality"]) / 3.0
            confidence = agg

    confirmation: Optional[AssetConfirmation] = None
    market_signal = asset_cfg.get("market_signal")
    if market_signal and market_confirmations and market_signal in market_confirmations:
        mr = market_confirmations[market_signal]
        confirmation = AssetConfirmation(
            signal_id=getattr(mr, "signal_id", market_signal),
            state=getattr(mr, "state", None),
            status=getattr(mr, "status", ""),
            macro_direction=getattr(mr, "macro_direction", 0),
            market_direction=getattr(mr, "market_direction", 0),
            agreement=getattr(mr, "agreement", None),
        )

    asof = None
    last_dates = [
        factor_results[f].asof
        for f in scored_factors
        if factor_results[f].asof is not None
    ]
    if last_dates:
        asof = max(last_dates)

    return AssetResult(
        asset=asset_id,
        name=asset_cfg.get("name", asset_id),
        status=status,
        score=score,
        view=view,
        change_1m=change_1m,
        change_3m=change_3m,
        factor_contributions=factor_contributions,
        signal_contributions=signal_contributions,
        beta=beta,
        beta_normalized=norm,
        market_confirmation=confirmation,
        confidence=confidence,
        asof=asof,
        scored_factors=scored_factors,
    )


def _default_source_quality(macro_config: Mapping) -> float:
    conf = macro_config.get("confidence") or {}
    return float(conf.get("default_source_quality", 0.5))


def compute_assets(
    assets_config: Mapping,
    factor_results: Mapping[str, object],
    computations: Mapping[str, object],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    today: pd.Timestamp,
    factor_signal_ids: Optional[Mapping[str, list[str]]] = None,
    market_confirmations: Optional[Mapping[str, object]] = None,
) -> dict[str, AssetResult]:
    """Compute all seven assets from the same read-only inputs.

    The 1M/3M change factor scores are reconstructed ONCE (shared by every
    asset) via the frozen read-only factor engine.
    """
    defaults = assets_config.get("defaults") or {}
    windows = defaults.get("change_window_days") or {}
    horizon_scores = compute_horizon_scores(
        computations,
        factor_signal_ids or {},
        macro_config,
        staleness,
        today,
        int(windows.get("change_1m", 30)),
        int(windows.get("change_3m", 90)),
    )
    return {
        asset_id: compute_asset(
            asset_id,
            asset_cfg,
            factor_results,
            computations,
            macro_config,
            staleness,
            today,
            defaults=assets_config.get("defaults"),
            factor_signal_ids=factor_signal_ids,
            market_confirmations=market_confirmations,
            horizon_scores=horizon_scores,
        )
        for asset_id, asset_cfg in assets_config["assets"].items()
    }