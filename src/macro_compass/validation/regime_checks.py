"""Dedicated checks for the two R2 regime/structural pending items (task 60 sec 5,
from the R2 header note 5 + config/assets.yaml ``v25_pending``).

1. GOLD vs US-10Y real yield 2022-2024 decoupling (central-bank buying): a
   split-sample beta/stability test around the 2022 break.
2. CN_CREDIT funding-sensitivity (2022 wealth-product redemption negative
   feedback): is the credit outcome more driven by funding (D1) than by growth?

Both are EMPIRICAL checks that only use current canonical data. Where the
needed pre-period data does not exist they must say so plainly (no fabricated
history), and that failure is itself a backfill finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from macro_compass.validation.methods import _spearman

# The documented regime break for the gold real-yield anchor (R2 batch note 5).
GOLD_BREAK = pd.Timestamp("2022-01-01")


@dataclass
class RegimeCheckResult:
    check_id: str
    title: str
    conclusion: str       # e.g. DATA_BLOCKED / INSUFFICIENT_SAMPLE / CONFIRMED / NOT_CONFIRMED
    adequate: bool
    statistic: Optional[float]
    n: int
    detail: str


def gold_real_yield_decoupling(sample, assets_config) -> RegimeCheckResult:
    """Split-sample check of GOLD *price* sensitivity to the US 10Y real-yield
    component (X1), before vs after the 2022 central-bank-buying break (R2 note 5).

    Uses the market GOLD spot series as the outcome and the X1 real-yield
    series as the driver - never the fundamental gold score (which mixes other
    factors and would look artificially stable). With no pre-2022 gold-price or
    real-yield history in canonical the 2022 break is UNOBSERVABLE and the check
    must say so (DATA_BLOCKED), feeding the Wind backfill list."""
    gold_series = (sample.series or {}).get("GOLD")
    x1_series = (sample.series or {}).get("US_REAL_YIELD_10Y")
    if gold_series is None or x1_series is None or not len(gold_series.dropna()):
        return RegimeCheckResult(
            "GOLD_X1", "gold real-yield decoupling (2022)",
            "DATA_BLOCKED", False, None, 0,
            "GOLD and/or US_REAL_YIELD_10Y price/driver history absent in canonical",
        )
    gold = gold_series.dropna().sort_index()
    x1 = x1_series.dropna().sort_index()
    span = f"{gold.index.min().date()}..{gold.index.max().date()}"
    if gold.index.min() >= GOLD_BREAK:
        # everything we hold is post-2022: the decoupling itself cannot be tested
        post_corr = None
        if len(x1) >= 4 and len(gold) >= 4:
            both = pd.concat([gold, x1], axis=1, join="inner").dropna()
            both.columns = ["gold", "x1"]
            post_corr = _spearman(both["gold"], both["x1"]) if len(both) >= 4 else None
        return RegimeCheckResult(
            "GOLD_X1", "gold real-yield decoupling (2022)",
            "DATA_BLOCKED", False, post_corr, int(len(gold)),
            f"all gold data is POST-2022 (span {span}); cannot split at the 2022 "
            f"break - needs Wind backfill of pre-2022 gold price + US_REAL_YIELD_10Y "
            f"(post-2022 spearman(gold, x1)={post_corr if post_corr is None else round(post_corr,3)}, n={len(gold)})",
        )
    # pre-2022 data present -> attempt the split
    pre = pd.concat([gold[gold.index < GOLD_BREAK], x1[x1.index < GOLD_BREAK]], axis=1, join="inner").dropna()
    post = pd.concat([gold[gold.index >= GOLD_BREAK], x1[x1.index >= GOLD_BREAK]], axis=1, join="inner").dropna()
    n_pre, n_post = len(pre), len(post)
    pre_corr = _spearman(pre.iloc[:, 0], pre.iloc[:, 1]) if n_pre >= 4 else None
    post_corr = _spearman(post.iloc[:, 0], post.iloc[:, 1]) if n_post >= 4 else None
    adequate = n_pre >= 4 and n_post >= 4
    if not adequate:
        return RegimeCheckResult(
            "GOLD_X1", "gold real-yield decoupling (2022)",
            "INSUFFICIENT_SAMPLE", False, (pre_corr, post_corr), n_pre + n_post,
            f"span {span}; n_pre={n_pre}, n_post={n_post} - too few on one side",
        )
    conclusion = "CONFIRMED" if (abs(pre_corr or 0) < 0.3 and abs(post_corr or 0) > 0.5) else (
        "NOT_CONFIRMED")
    return RegimeCheckResult(
        "GOLD_X1", "gold real-yield decoupling (2022)",
        conclusion, adequate, (pre_corr, post_corr), n_pre + n_post,
        f"span {span}; spearman(gold_price, real_yield) pre2022={pre_corr:.3f}, "
        f"post2022={post_corr:.3f} (n_pre={n_pre}, n_post={n_post})",
    )


def credit_funding_sensitivity(sample, assets_config) -> RegimeCheckResult:
    """Compare the CN_CREDIT outcome response to the funding factor (D1) against
    the growth factor - tests whether funding sensitivity dominates growth."""
    cred_score = sample.asset_scores.get("CN_CREDIT")
    fwd = sample.forward_returns.get("CN_CREDIT")
    for h in ("1m", "3m"):
        fdf = fwd.get(f"fwd_{h}")
        if fdf is not None:
            break
    if cred_score is None or fdf is None:
        return RegimeCheckResult(
            "CREDIT_D1", "credit funding-sensitivity vs growth",
            "DATA_BLOCKED", False, None, 0, "no credit score/forward panel",
        )
    rows = pd.DataFrame({
        "score": cred_score,
        "dom": sample.factor_panel["domestic_financial"],
        "grow": sample.factor_panel["growth"],
        "fwd": fdf,
    }).dropna(subset=["fwd"])
    rows = rows.dropna(subset=["dom", "grow"])
    if len(rows) < 6:
        return RegimeCheckResult(
            "CREDIT_D1", "credit funding-sensitivity vs growth",
            "INSUFFICIENT_SAMPLE", False, None, len(rows),
            "too few aligned credit outcomes vs both factors (D1 needs DR007+policy history)",
        )
    # outcome ~ funding vs outcome ~ growth
    dom_r = _spearman(rows["fwd"], rows["dom"])
    grow_r = _spearman(rows["fwd"], rows["grow"])
    # score-level: credit score ~ funding vs credit score ~ growth
    sdom = _spearman(rows["score"], rows["dom"])
    strong = (dom_r is not None and grow_r is not None and abs(dom_r) > abs(grow_r))
    adequate = len(rows) >= 60
    conclusion = "CONFIRMED" if (adequate and strong) else (
        "NOT_CONFIRMED" if adequate else "INSUFFICIENT_SAMPLE")
    return RegimeCheckResult(
        "CREDIT_D1", "credit funding-sensitivity vs growth",
        conclusion, adequate, dom_r - grow_r if dom_r is not None and grow_r is not None else None,
        len(rows),
        f"spearman(creditFwd,Funding)={dom_r}, (creditFwd,Growth)={grow_r}; "
        f"spearman(creditScore,Funding)={sdom}; n={len(rows)}",
    )


def run_all(sample, assets_config) -> list[RegimeCheckResult]:
    return [
        gold_real_yield_decoupling(sample, assets_config),
        credit_funding_sensitivity(sample, assets_config),
    ]