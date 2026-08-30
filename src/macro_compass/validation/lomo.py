"""Leave-One-Mechanism-Out (LOMO) - Information Increment Test (task 60 section 4).

For every factor (growth/inflation/domestic/global) we drop each declared
mechanism (core signal) in turn, re-derive the PIT factor score over the same
grid, re-score the seven assets, and measure:

* factor stability      - Spearman(leave-out factor score, full factor score)
* asset-score stability - Spearman(leave-out asset score, full asset score),
                         reported as the worst (min) across assets
* forward-return separation - delta between the asset-score vs forward-return
                         Spearman under the full and leave-out panels, reported
                         as the largest |delta| across assets and horizons.

A mechanism that barely moves stability (corr ~1.0) AND barely moves forward
separation (~0) contributes little independent information. Combined with a
high maintenance cost (short/backfill-dependent history) that is the Core ->
Diagnostic signal - but ONLY a recommendation; downgrades need owner approval
(task 60 section 4/6).

Pure functions: they read the frozen PIT panels and frozen return proxies only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import pandas as pd

from macro_compass.validation.history import (
    factor_scores_on_grid,
    MIN_N_FOR_DIRECTIONAL,
)
from macro_compass.validation.methods import _spearman

# Stability requires both a high factor/asset correlation and a small change in
# forward separation before we flag a mechanism as a low-increment candidate.
STABILITY_CORR = 0.95
MAX_SEP_DELTA = 0.05


@dataclass
class LomoResult:
    factor: str
    mechanism: str
    sample_ok: bool
    factor_stability: Optional[float]
    min_asset_stability: Optional[float]
    max_separation_delta: Optional[float]
    candidate: bool
    detail: str


def _asset_scores(assets_config: Mapping, factor_panel: pd.DataFrame) -> pd.DataFrame:
    from macro_compass.validation.history import build_asset_panel
    scores, _ = build_asset_panel(assets_config, factor_panel)
    return scores


def lomo_candidate(
    sample_ok: bool,
    scored_share: Optional[float],
    fac_corr: Optional[float],
    max_delta: Optional[float],
    *,
    corr_threshold: float = STABILITY_CORR,
    delta_threshold: float = MAX_SEP_DELTA,
    share_threshold: float = 0.50,
) -> bool:
    """Pure candidate gate: a mechanism only counts as low-increment when the
    comparison sample is adequate, its own history covers enough of the grid,
    the factor stays ~unchanged when it is dropped, and forward separation does
    not move. This keeps newly-arrived or sample-poor mechanisms out."""
    if not sample_ok or scored_share is None:
        return False
    if scored_share < share_threshold:
        return False
    if fac_corr is None or fac_corr < corr_threshold:
        return False
    if max_delta is not None and max_delta > delta_threshold:
        return False
    return True


def run_lomo(
    computations,
    full_factor_signal_ids,
    macro_config,
    staleness,
    assets_config,
    sample,
    grid: Optional[pd.DatetimeIndex] = None,
    first_score_dates: Optional[Mapping[str, pd.Timestamp]] = None,
    mechanism_scored_share: Optional[Mapping[str, float]] = None,
) -> list[LomoResult]:
    """Run LOMO over every (factor, mechanism); returns one row per combination.

    ``first_score_dates`` (signal_id -> first computable PIT score) and
    ``mechanism_scored_share`` (share of grid dates the mechanism actually
    scored) pre-gate the candidate flag: a mechanism whose own history covers
    only a small share of the grid cannot be judged on whether it adds
    independent information (task 60 section 6: never conclude on insufficient
    sample).
    """
    grid = grid if grid is not None else sample.factor_panel.index
    span = (grid.max() - grid.min()).days
    base_fp = sample.factor_panel
    base_assets = _asset_scores(assets_config, base_fp)
    # baseline separation per asset+horizon
    base_sep = {
        asset_id: _best_separation(asset_id, sample, base_assets)
        for asset_id in base_assets.columns
    }

    results: list[LomoResult] = []
    for factor in full_factor_signal_ids:
        mechanisms = list(full_factor_signal_ids[factor])
        for sid in mechanisms:
            reduced_ids = {
                k: [m for m in v if not (k == factor and m == sid)]
                for k, v in full_factor_signal_ids.items()
            }
            lo_fp = factor_scores_on_grid(
                computations, reduced_ids, macro_config, staleness, grid
            )
            # factor stability (this column changed)
            a = base_fp[factor].dropna()
            b = lo_fp[factor].dropna()
            common = a.index.intersection(b.index)
            fac_corr = (
                _spearman(a[common], b[common]) if len(common) >= 4 else None
            )
            # asset scores with the leave-out factor swapped in
            lo_assets = base_assets.copy()
            # rebuild from a panel where only `factor` differs
            panel = base_fp.copy()
            panel[factor] = lo_fp[factor]
            lo_assets_full = _asset_scores(assets_config, panel)
            # per-asset stability + separation
            asset_corrs, sep_deltas = [], []
            for asset_id in lo_assets_full.columns:
                c = _asset_stability(base_assets[asset_id], lo_assets_full[asset_id])
                if c is not None:
                    asset_corrs.append(c)
                d = _separation_delta(asset_id, sample, base_assets, lo_assets_full)
                if d is not None:
                    sep_deltas.append(d)
            min_asset = min(asset_corrs) if asset_corrs else None
            max_delta = max(sep_deltas) if sep_deltas else None
            sample_ok = len(common) >= MIN_N_FOR_DIRECTIONAL
            # mechanism's own history must cover a meaningful share of the grid
            # (>=50% of scored grid dates) before 'adds little' can be taken as
            # a genuine finding - a mechanism that simply arrived late is not a
            # downgrade candidate.
            scored_share = (mechanism_scored_share or {}).get(sid)
            candidate = lomo_candidate(
                sample_ok, scored_share, fac_corr, max_delta
            )
            detail = (
                f"factor_stab={fac_corr if fac_corr is None else round(fac_corr, 3)}, "
                f"min_asset_stab={min_asset if min_asset is None else round(min_asset, 3)}, "
                f"max_sep_delta={max_delta if max_delta is None else round(max_delta, 4)}, "
                f"scored_share={scored_share if scored_share is None else round(scored_share, 3)}"
            )
            results.append(
                LomoResult(
                    factor=factor, mechanism=sid, sample_ok=sample_ok,
                    factor_stability=fac_corr, min_asset_stability=min_asset,
                    max_separation_delta=max_delta,
                    candidate=candidate, detail=detail,
                )
            )
    return results


def _best_separation(asset_id: str, sample, asset_scores: pd.DataFrame) -> Optional[float]:
    """Largest |Spearman(asset_score, forward return)| across horizons."""
    best = None
    for h in ("1m", "3m"):
        fdf = sample.forward_returns.get(asset_id)
        if fdf is None or f"fwd_{h}" not in fdf:
            continue
        rows = pd.DataFrame({
            "score": asset_scores[asset_id],
            "fwd": fdf[f"fwd_{h}"],
        }).dropna()
        if len(rows) >= 4:
            r = _spearman(rows["score"], rows["fwd"])
            if r is not None:
                best = r if best is None else (r if abs(r) > abs(best) else best)
    return best


def _separation_delta(asset_id, sample, base_scores, lo_scores) -> Optional[float]:
    """|leave-out separation - baseline separation|."""
    b = _best_separation(asset_id, sample, base_scores)
    l = _best_separation(asset_id, sample, lo_scores)
    if b is None or l is None:
        return None
    return abs(l - b)


def _asset_stability(a: pd.Series, b: pd.Series) -> Optional[float]:
    common = a.dropna().index.intersection(b.dropna().index)
    if len(common) < 4:
        return None
    return _spearman(a[common], b[common])