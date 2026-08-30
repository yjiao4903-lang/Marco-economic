"""V4.6 per-asset empirical verdict assembly (task 86).

Reads ONLY the already-computed validation results (the five methods, LOMO and
regime checks) plus the asset-score/coverage panels, and classifies each asset
into one of the task-spec verdict labels. It is a pure report transformation:
it never re-fits, never searches betas/thresholds, never modifies the model,
and never forces a positive conclusion.

Verdict labels (task 86 / demand section 3.10):
    SUPPORTED            adequate directional separation AND sign agrees with
                         the declared prior on at least one horizon
    WEAKLY_SUPPORTED     adequate sample but only a small directional effect
                         (|rho| <= SIGNAL_BAR) on all horizons
    MIXED                material effects with conflicting signs across
                         horizons / buckets
    NO_EFFECT_OR_WEAK    adequate sample, no material effect anywhere
    INSUFFICIENT_SAMPLE  no horizon reaches the declared sanity bar
    DATA_BLOCKED         no forward-return panel (e.g. GOLD spot absent)

The honest default on the current ~21-month comparable window is
INSUFFICIENT_SAMPLE / WEAKLY_SUPPORTED / NO_EFFECT_OR_WEAK - never SUPPORTED
without an adequate, sign-agreeing sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

import pandas as pd

# Materiality bar for directional separation (same convention as methods.py).
SIGNAL_BAR = 0.15
# Verdict labels allowed by the task spec (no forced-positive).
LABELS = (
    "SUPPORTED", "WEAKLY_SUPPORTED", "MIXED", "NO_EFFECT_OR_WEAK",
    "INSUFFICIENT_SAMPLE", "DATA_BLOCKED",
)

_ASSET_NAMES = {
    "CN_EQUITY": "A股", "HK_EQUITY": "港股", "CN_GOV_BOND": "利率债",
    "CN_CREDIT": "信用债", "GOLD": "黄金",
    "INDUSTRIAL_COMMODITY": "工业商品", "CNY": "人民币汇率",
}


@dataclass
class AssetVerdict:
    asset: str
    verdict: str
    n: int = 0                        # largest adequate horizon n seen
    mean_rho: Optional[float] = None  # mean adequate |rho|, sign retained
    window_start: Optional[str] = None
    coverage: Optional[float] = None  # mean factor coverage on scored dates
    reasons: list[str] = field(default_factory=list)
    confidence: str = "low"

    def as_row(self) -> dict:
        return {
            "asset": self.asset,
            "name": _ASSET_NAMES.get(self.asset, self.asset),
            "verdict": self.verdict,
            "n": self.n,
            "mean_rho": "" if self.mean_rho is None else round(self.mean_rho, 4),
            "window_start": self.window_start or "",
            "coverage": "" if self.coverage is None else round(self.coverage, 3),
            "confidence": self.confidence,
            "reasons": "; ".join(self.reasons),
        }


def _methods_for(methods: Iterable[dict], asset: str) -> list[dict]:
    return [m for m in methods if m["asset"] == asset]


def _forward_rhos(methods: Iterable[dict], asset: str) -> list[dict]:
    """Forward-return Spearman rows (adequate only) for one asset."""
    out = []
    for m in _methods_for(methods, asset):
        if m["method"] == "forward_returns" and m.get("adequate") \
                and m.get("statistic") is not None \
                and m.get("horizon") in ("1m", "3m"):
            out.append(m)
    return out


def _bucket_rows(methods: Iterable[dict], asset: str) -> list[dict]:
    return [m for m in _methods_for(methods, asset)
            if m["method"] == "score_bucket" and m.get("adequate")
            and m.get("statistic") is not None]


def _regime_rows(methods: Iterable[dict], asset: str) -> list[dict]:
    return [m for m in _methods_for(methods, asset)
            if m["method"] == "regime_analysis" and m.get("adequate")
            and m.get("statistic") is not None]


def _weight_row(methods: Iterable[dict], asset: str) -> Optional[dict]:
    for m in _methods_for(methods, asset):
        if m["method"] == "weight_robustness":
            return m
    return None


def classify(asset: str, methods: Iterable[dict]) -> tuple[str, list[str]]:
    """Pure classifier: (verdict, reasons) from the methods table only."""
    reasons: list[str] = []
    fwd = _forward_rhos(methods, asset)
    buckets = _bucket_rows(methods, asset)
    regimes = _regime_rows(methods, asset)
    weight = _weight_row(methods, asset)

    if not fwd:
        # no adequate forward-return sample at all
        if any(m["method"] == "forward_returns" for m in _methods_for(methods, asset)) \
                and all(not m.get("adequate") for m in
                        [x for x in _methods_for(methods, asset)
                         if x["method"] == "forward_returns"]):
            return "INSUFFICIENT_SAMPLE", [
                "no horizon reaches the 60-month sanity bar (current window ~21m)"]
        return "DATA_BLOCKED", ["no forward-return panel"]

    rhos = [float(m["statistic"]) for m in fwd]
    sign_agree = sum(1 for r in rhos if r > 0)
    material = [r for r in rhos if abs(r) > SIGNAL_BAR]
    signs_material = {1 if r > 0 else -1 for r in material}

    reasons.append(
        f"directional rho 1m={fwd[0]['statistic']:.3f} "
        f"(n={fwd[0]['n']})"
        + (f", 3m={fwd[1]['statistic']:.3f} (n={fwd[1]['n']})" if len(fwd) > 1 else "")
    )
    if buckets:
        spreads = [float(b["statistic"]) for b in buckets]
        reasons.append(f"bucket spread(high-low fwd) 1m={spreads[0]:.4f}"
                       + (f", 3m={spreads[1]:.4f}" if len(spreads) > 1 else ""))
    if regimes:
        gs = [float(r["statistic"]) for r in regimes]
        reasons.append(f"regime G+ minus G- mean fwd 1m={gs[0]:.4f}"
                       + (f", 3m={gs[1]:.4f}" if len(gs) > 1 else ""))
    if weight is not None:
        reasons.append(f"weight robustness mean_scheme_corr={weight['statistic']:.3f}")

    if material:
        if len(signs_material) > 1:
            return "MIXED", reasons + ["material effects conflict in sign across horizons"]
        if 1 in signs_material:
            return "SUPPORTED", reasons + ["sign agrees with declared prior"]
        return "MIXED", reasons + ["material effect is REVERSED vs declared prior"]
    # no material effect anywhere but sample adequate
    if all(r > 0 for r in rhos):
        return "WEAKLY_SUPPORTED", reasons + ["small positive effect only (|rho|<=0.15)"]
    if all(r < 0 for r in rhos):
        return "NO_EFFECT_OR_WEAK", reasons + ["small negative effect only (|rho|<=0.15)"]
    return "NO_EFFECT_OR_WEAK", reasons + ["no material effect on any horizon"]


def _window_start(asset_scores: pd.DataFrame, asset: str) -> Optional[str]:
    if asset_scores is None or asset not in asset_scores:
        return None
    vals = asset_scores[asset].dropna()
    return vals.index.min().date().isoformat() if len(vals) else None


def _coverage(asset_coverage: pd.DataFrame, asset: str) -> Optional[float]:
    if asset_coverage is None or asset not in asset_coverage:
        return None
    vals = asset_coverage[asset][asset_coverage[asset] > 0]
    return float(vals.mean()) if len(vals) else None


def _confidence(n: int, coverage: Optional[float]) -> str:
    if n >= 60 and (coverage or 0) >= 0.9:
        return "medium"
    if n >= 60:
        return "low-medium"
    return "low"


def build_verdicts(
    methods: Iterable[dict],
    asset_scores: pd.DataFrame,
    asset_coverage: pd.DataFrame,
    assets: Optional[list[str]] = None,
) -> list[AssetVerdict]:
    """Classify every asset (or the given subset)."""
    assets = assets or sorted({m["asset"] for m in methods})
    verdicts: list[AssetVerdict] = []
    for asset in assets:
        label, reasons = classify(asset, methods)
        fwd = _forward_rhos(methods, asset)
        n = max((int(m["n"]) for m in fwd), default=0)
        mean_rho = (
            float(sum(float(m["statistic"]) for m in fwd) / len(fwd)) if fwd else None
        )
        cov = _coverage(asset_coverage, asset)
        verdicts.append(
            AssetVerdict(
                asset=asset,
                verdict=label,
                n=n,
                mean_rho=mean_rho,
                window_start=_window_start(asset_scores, asset),
                coverage=cov,
                reasons=reasons,
                confidence=_confidence(n, cov),
            )
        )
    return verdicts


def verdicts_frame(verdicts: list[AssetVerdict]) -> pd.DataFrame:
    return pd.DataFrame([v.as_row() for v in verdicts])
