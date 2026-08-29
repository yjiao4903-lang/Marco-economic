"""Factor aggregation (V1.5C): factor score, breadth, confidence.

Hard constraint (ARCHITECTURE section 9): this module reads ONLY the signal
layer output (``signals.engine.SignalComputation``) - it has no path to raw
canonical series. Aggregation follows the "mechanism -> factor" hierarchy
(MASTER SPEC section 11): each signal is one economic mechanism, and the
factor score is a configured-weight mean over its signals' scores. Raw
series are never pooled directly.

Confidence is a DATA QUALITY description in [0, 1] with three documented
components - coverage, freshness and source quality. It is NOT a forecast
probability (MASTER SPEC section 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

import pandas as pd

from macro_compass.signals.engine import SignalComputation


@dataclass
class SignalContribution:
    """One signal's contribution to its factor, with full traceability."""

    signal_id: str
    score: Optional[float]
    weight: float
    contribution: Optional[float]  # additive points; parts sum to factor score
    coverage: float
    freshness_days: Optional[int]
    stale: bool
    provenance: str  # synthetic / real / mixed / unknown
    inputs: dict[str, str] = field(default_factory=dict)  # series_id -> source


@dataclass
class FactorResult:
    """Aggregated factor: score, breadth and confidence decomposition."""

    factor: str
    score: Optional[float]
    breadth: int
    breadth_detail: list[str]
    confidence: dict[str, float]  # coverage / freshness / source_quality / composite
    signals: dict[str, SignalContribution]
    asof: Optional[pd.Timestamp]


def classify_provenance(
    source_files_by_series: Mapping[str, Iterable[str]],
    synthetic_markers: Iterable[str],
) -> dict[str, str]:
    """Classify each series' data provenance from its canonical source_file values.

    A series is 'synthetic' when any of its rows was imported from a file whose
    name carries a synthetic marker (config/macro.yaml), 'real' when none does,
    'mixed' when both occur and 'unknown' when it has no file attribution.
    """
    markers = [str(m).lower() for m in synthetic_markers]
    result: dict[str, str] = {}
    for series_id, files in source_files_by_series.items():
        names = [str(f).lower() for f in files if f]
        if not names:
            result[series_id] = "unknown"
            continue
        hits = [f for f in names if any(marker in f for marker in markers)]
        if hits and len(hits) == len(names):
            result[series_id] = "synthetic"
        elif hits:
            result[series_id] = "mixed"
        else:
            result[series_id] = "real"
    return result


def _source_quality(sources: Mapping[str, str], macro_config: Mapping) -> float:
    """Mean source tier of one signal's input series, in [0, 1]."""
    conf = macro_config["confidence"]
    tiers = conf.get("source_quality") or {}
    default = float(conf.get("default_source_quality", 0.5))
    values = [
        float(tiers.get(str(source).upper(), default))
        for source in sources.values()
        if source
    ]
    if not values:
        return default
    return sum(values) / len(values)


def _signal_staleness_budget(
    input_series_ids: Iterable[str], staleness: Mapping[str, int], macro_config: Mapping
) -> int:
    """Strictest staleness budget across a signal's input series (days)."""
    default = int(macro_config["confidence"].get("default_max_staleness_days", 90))
    budgets = [int(staleness.get(series_id, default)) for series_id in input_series_ids]
    return min(budgets) if budgets else default


def compute_factor(
    factor: str,
    declared_signal_ids: Iterable[str],
    signal_outputs: Mapping[str, SignalComputation],
    macro_config: Mapping,
    staleness: Mapping[str, int],
    today: pd.Timestamp,
) -> FactorResult:
    """Aggregate one factor from signal outputs only.

    ``declared_signal_ids`` are the factor's core signal ids from the registry
    (one per economic mechanism). ``staleness`` maps series_id ->
    max_staleness_days as declared in ``config/data_sources.yaml``. Signals
    without a computable score are excluded from the aggregation - never
    zero-filled.
    """
    today = pd.Timestamp(today)
    weights_all = macro_config["factor_weights"][factor]
    breadth_min = float(macro_config["regime"]["breadth_min_score"])

    contributions: dict[str, SignalContribution] = {}
    for signal_id in declared_signal_ids:
        output = signal_outputs.get(signal_id)
        if output is None:
            continue
        weight = float(weights_all.get(signal_id, 1.0))
        latest = output.latest()
        score = float(latest["score"]) if latest is not None else None
        coverage = float(latest["coverage"]) if latest is not None else 0.0

        if output.frame.empty:
            freshness_days: Optional[int] = None
        else:
            freshness_days = int((today.normalize() - output.frame["date"].max()).days)
        budget = _signal_staleness_budget(
            output.input_series_ids, staleness, macro_config
        )
        stale = freshness_days is not None and freshness_days > budget

        contributions[signal_id] = SignalContribution(
            signal_id=signal_id,
            score=score,
            weight=weight,
            contribution=None,
            coverage=coverage,
            freshness_days=freshness_days,
            stale=stale,
            provenance=output.provenance,
            inputs=dict(output.input_sources),
        )

    scored = {sid: c for sid, c in contributions.items() if c.score is not None}
    total_weight = sum(c.weight for c in scored.values())

    factor_score: Optional[float] = None
    if scored and total_weight > 0:
        factor_score = sum(c.weight * c.score for c in scored.values()) / total_weight
        for c in scored.values():
            c.contribution = c.weight * c.score / total_weight

    # Breadth: number of DISTINCT MECHANISMS (signals) supporting the factor's
    # current direction - never a count of raw series.
    breadth_detail: list[str] = []
    if factor_score is not None and factor_score != 0.0:
        direction = 1.0 if factor_score > 0 else -1.0
        breadth_detail = sorted(
            sid
            for sid, c in scored.items()
            if abs(c.score) >= breadth_min and (c.score > 0) == (direction > 0)
        )
    breadth = len(breadth_detail)

    declared = list(declared_signal_ids)
    coverage_component = len(scored) / len(declared) if declared else 0.0
    freshness_component = (
        sum(1 for c in scored.values() if not c.stale) / len(scored) if scored else 0.0
    )
    if scored and total_weight > 0:
        source_component = (
            sum(c.weight * _source_quality(c.inputs, macro_config) for c in scored.values())
            / total_weight
        )
    else:
        source_component = float(macro_config["confidence"].get("default_source_quality", 0.5))
    confidence = {
        "coverage": coverage_component,
        "freshness": freshness_component,
        "source_quality": source_component,
        "composite": (coverage_component + freshness_component + source_component) / 3.0,
    }

    asof = None
    last_dates = [
        output.frame["date"].max()
        for output in signal_outputs.values()
        if not output.frame.empty
    ]
    if last_dates:
        asof = max(pd.DatetimeIndex(last_dates))

    return FactorResult(
        factor=factor,
        score=factor_score,
        breadth=breadth,
        breadth_detail=breadth_detail,
        confidence=confidence,
        signals=contributions,
        asof=asof,
    )
