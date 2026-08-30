"""The five Validation methods (V2.5, task 60 section 3) + a small weight
robustness helper. All are PURE functions over the aligned sample produced by
``history.aligned`` / ``history.ValidationSample`` - they never touch canonical
or asset outputs, so the production layer is fully isolated.

Every method returns a verdict dict:
    method, asset, horizon, metric, statistic, n, adequate, conclusion, detail

``adequate`` is False (and conclusion = INSUFFICIENT_SAMPLE) whenever n falls
short of the declared sanity bar - this is the honest default on the current
short comparable window; it is NOT a statistical guarantee at any n.
"""

from __future__ import annotations

from typing import Mapping, Optional

import numpy as np
import pandas as pd

from macro_compass.validation.history import MIN_N_FOR_DIRECTIONAL


def _spearman(x: pd.Series, y: pd.Series) -> Optional[float]:
    """Spearman rank correlation without scipy (rank + Pearson)."""
    if len(x) < 3:
        return None
    rx = x.rank().to_numpy(dtype=float)
    ry = y.rank().to_numpy(dtype=float)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    den = (np.sqrt((rx ** 2).sum()) * np.sqrt((ry ** 2).sum())) or np.nan
    return float((rx * ry).sum() / den)


def _verdict(method, asset, horizon, metric, stat, n, detail="") -> dict:
    if stat is None or not np.isfinite(stat) or horizon is None:
        adequate = False
        conclusion = "N_A"
    else:
        adequate = n >= MIN_N_FOR_DIRECTIONAL
        if not adequate:
            conclusion = "INSUFFICIENT_SAMPLE"
        elif stat > 0.15:
            conclusion = "SIGNAL_PRESENT"
        elif stat < -0.15:
            conclusion = "SIGNAL_PRESENT_REVERSED"
        else:
            conclusion = "NO_EFFECT_OR_WEAK"
    return {
        "method": method, "asset": asset, "horizon": horizon,
        "metric": metric, "statistic": stat, "n": n,
        "adequate": adequate, "conclusion": conclusion, "detail": detail,
    }


def forward_returns(asset_id: str, horizon: str, df: pd.DataFrame) -> dict:
    """Spearman(signal, forward return) + sign-agreement hit rate."""
    n = len(df)
    if n < 3:
        return _verdict("forward_returns", asset_id, horizon, "spearman_rho", None, n)
    rho = _spearman(df["score"], df["fwd"])
    hit = float(((df["score"] > 0) == (df["fwd"] > 0)).mean())
    v = _verdict("forward_returns", asset_id, horizon, "spearman_rho", rho, n,
                 detail=f"hit_rate_agreement={hit:.2f}")
    return v


def score_bucket(asset_id: str, horizon: str, df: pd.DataFrame) -> dict:
    """Median-split: mean forward return in high-score vs low-score buckets."""
    n = len(df)
    if n < 4:
        return _verdict("score_bucket", asset_id, horizon, "mean_fwd_high_minus_low", None, n)
    med = df["score"].median()
    high = df.loc[df["score"] > med, "fwd"].mean()
    low = df.loc[df["score"] <= med, "fwd"].mean()
    spread = float(high - low) if pd.notna(high) and pd.notna(low) else None
    v = _verdict("score_bucket", asset_id, horizon, "mean_fwd_high_minus_low", spread, n,
                 detail=f"high_mean={high:.4f}, low_mean={low:.4f}")
    return v


def regime_analysis(asset_id: str, horizon: str, df: pd.DataFrame, factor_panel: pd.DataFrame) -> dict:
    """Compare forward returns across Growth x Inflation quadrants (translation
    of the macro regime classification, task 60 section 3 'regime analysis')."""
    if df.empty:
        return _verdict("regime_analysis", asset_id, horizon, "quadrant_mean_spread", None, 0)
    # Growth x Inflation quadrants need BOTH axes computable on a date. On the
    # current window this rarely clears, so in addition to the 2x2 spread we
    # always report the univariate Growth-positive vs Growth-negative means.
    g = factor_panel["growth"].reindex(df.index)
    i = factor_panel["inflation"].reindex(df.index)
    both = df.loc[g.notna() & i.notna()]
    qdetail = ""
    quadrant_spread = None
    if len(both) >= 4:
        gq = both.loc[g > 0, "fwd"].mean()
        nq = both.loc[g <= 0, "fwd"].mean()
        iq_hi = both.loc[i > 0, "fwd"].mean()
        iq_lo = both.loc[i <= 0, "fwd"].mean()
        quadrant_spread = float(iq_hi - iq_lo) if pd.notna(iq_hi) and pd.notna(iq_lo) else None
        qdetail = f"(G>0 mean={gq:.4f}, G<=0 mean={nq:.4f}, I>0 mean={iq_hi:.4f}, I<=0 mean={iq_lo:.4f})"
    gpos = df.loc[g > 0, "fwd"]
    gneg = df.loc[g <= 0, "fwd"]
    spread = None
    detail = ""
    if len(gpos.dropna()) and len(gneg.dropna()):
        spread = float(gpos.mean() - gneg.mean())
        detail = f"G>0_mean={gpos.mean():.4f}, G<=0_mean={gneg.mean():.4f} {qdetail}"
    n = len(gpos.dropna()) + len(gneg.dropna())
    v = _verdict("regime_analysis", asset_id, horizon, "G_positive_minus_negative_mean_fwd", spread, n, detail)
    return v


def rolling_beta(asset_id: str, horizon: str, df: pd.DataFrame, window: int = 24) -> dict:
    """Stability of the rolling Spearman(score, fwd); report mean/std/min/max."""
    n = len(df)
    if n < max(window + 1, 5):
        return _verdict("rolling_beta", asset_id, horizon, "mean_rolling_rho", None, n)
    rhos = []
    for i in range(len(df) - window):
        sub = df.iloc[i:i + window]
        r = _spearman(sub["score"], sub["fwd"])
        if r is not None:
            rhos.append(r)
    if not rhos:
        return _verdict("rolling_beta", asset_id, horizon, "mean_rolling_rho", None, n)
    rhos = np.array(rhos)
    mean = float(rhos.mean())
    v = _verdict("rolling_beta", asset_id, horizon, "mean_rolling_rho", mean, n,
                 detail=f"std={rhos.std():.3f}, min={rhos.min():.3f}, max={rhos.max():.3f}")
    return v


# ---- weight robustness (task 60 section 3; reversed here from assets.yaml) --
# Alternative DECLARED-prior sensitivity schemes - perturbing the tier->weight
# map only, never signs or which signals are active. Correlation of the score
# series across schemes measures prior-weight robustness.
ALTERNATIVE_TIER_WEIGHTS = {
    "flat": {"HIGH": 1.0, "MEDIUM": 1.0, "LOW": 1.0},
    "steeper": {"HIGH": 1.2, "MEDIUM": 0.7, "LOW": 0.3},
    "flatter": {"HIGH": 0.8, "MEDIUM": 0.5, "LOW": 0.2},
}


def _recompute_betas(asset_cfg: Mapping, tier_weights: Mapping[str, float]) -> Mapping:
    """Re-derive factor betas under an alternative tier-weight scheme (mirrors
    assets/config.load_asset_config: weight = tier weight, ambiguous/0 -> 0)."""
    sign_val = {"+": 1.0, "-": -1.0, "0": 0.0, "ambiguous": 0.0}
    out = {f: dict(asset_cfg["factors"][f]) for f in asset_cfg["factors"]}
    for f, block in out.items():
        beta = 0.0
        for sid, cell in block["signals"].items():
            w = 0.0 if cell["sign"] in ("ambiguous", "0") else float(tier_weights[cell["tier"]])
            block["signals"][sid] = dict(cell)
            block["signals"][sid]["weight"] = w
            beta += sign_val[cell["sign"]] * w
        block["beta"] = round(beta, 4)
    return out


def weight_robustness(asset_id: str, assets_config: Mapping, factor_panel: pd.DataFrame,
                      baseline: pd.Series) -> dict:
    """Spearman between the baseline score series and each alternative scheme's
    score series; report the mean. High correlation = robust to prior weights."""
    base_factors = assets_config["assets"][asset_id]["factors"]
    base_norm = _l1(base_factors)
    corrs = []
    for name, scheme in ALTERNATIVE_TIER_WEIGHTS.items():
        alt_factors = _recompute_betas(assets_config["assets"][asset_id], scheme)
        alt_norm = _l1(alt_factors)
        s = pd.Series(index=factor_panel.index, dtype=float)
        for d, r in factor_panel.iterrows():
            scored = {f for f in alt_norm if pd.notna(r[f]) and abs(alt_norm[f]) > 0}
            s[d] = None if not scored else float(sum(alt_norm[f] * r[f] for f in scored))
        pairs = pd.DataFrame({"a": baseline, "b": s}).dropna()
        rho = _spearman(pairs["a"], pairs["b"])
        if rho is not None:
            corrs.append((name, rho))
    mean = float(np.mean([c for _, c in corrs])) if corrs else None
    detail = "; ".join(f"{name}={c:.3f}" for name, c in corrs)
    # Weight robustness is a qualitative prior-sensitivity check across a small
    # fixed set of declared schemes - sample size is not the operative concern,
    # so the verdict is reported directly (not a sample-size verdict).
    if mean is None:
        conclusion, adequate = "N_A", False
    elif mean >= 0.9:
        conclusion, adequate = "WEIGHT_ROBUST", True
    else:
        conclusion, adequate = "WEIGHT_SENSITIVE", True
    return {
        "method": "weight_robustness", "asset": asset_id, "horizon": None,
        "metric": "mean_scheme_corr", "statistic": mean, "n": len(corrs),
        "adequate": adequate, "conclusion": conclusion, "detail": detail,
    }


def _l1(factors: Mapping) -> dict[str, float]:
    beta = {f: float(factors[f]["beta"]) for f in factors}
    total = sum(abs(b) for b in beta.values())
    if total <= 0:
        return {f: 0.0 for f in beta}
    return {f: beta[f] / total for f in beta}


def run_all_for_asset(
    asset_id: str,
    sample,
    assets_config: Mapping,
    horizons: tuple[str, ...] = ("1m", "3m"),
    min_coverage: float = 0.5,
) -> list[dict]:
    """Run all five methods for one asset over the given horizons."""
    base = sample.asset_scores[asset_id].dropna()
    results: list[dict] = []
    for h in horizons:
        df = _safe_aligned(asset_id, h, sample, min_coverage)
        results.append(forward_returns(asset_id, h, df))
        results.append(score_bucket(asset_id, h, df))
        results.append(regime_analysis(asset_id, h, df, sample.factor_panel))
        results.append(rolling_beta(asset_id, h, df))
    results.append(weight_robustness(asset_id, assets_config, sample.factor_panel, base))
    return results


def _safe_aligned(asset_id: str, horizon: str, sample, min_coverage: float) -> pd.DataFrame:
    from macro_compass.validation.history import aligned
    return aligned(asset_id, horizon, sample, min_coverage=min_coverage)