"""Market Confirmation engine (V1.6A).

Computes the six MASTER SPEC market-confirmation signals (M1-M6) from
canonical series and classifies their divergence from the fundamental macro
direction. Pure functions throughout: canonical series, factor outputs and
configs go in, results come out - no network, no storage side effects.

ISOLATION (ARCHITECTURE section 10, MASTER SPEC section 4): the market layer
only READS fundamental outputs (factor scores via ``macro.factors`` results).
No fundamental module imports this package and nothing here writes back into
Growth/Inflation - a market reading can never modify a fundamental score.

Computation (Phase 2), reusing the frozen transform whitelist only:

* 1M move / 3M move / 6M trend - ``pct_change`` (indices, FX, commodity) or
  ``delta`` in percent points (yields, spreads), per the market.yaml `move`
  declaration, over 21/63/126 observations;
* rolling percentile of the series level over the declared window.

Direction conventions (Phase 2) are DECLARED in ``config/market.yaml`` -
never assumed: `positive` = a rising raw series supports the market read,
`negative` = a rising raw series argues against it. Adjusted metrics apply
the convention (and the percentile is oriented, so adj_percentile > 0.5
always means "supportive").

Divergence (Phase 3) - five states from macro direction x market direction,
named after the macro direction the market fails to confirm:

    CONFIRMED_POSITIVE / CONFIRMED_NEGATIVE /
    POSITIVE_MACRO_DIVERGENCE / NEGATIVE_MACRO_DIVERGENCE / MIXED

retaining macro_direction, market_direction, agreement and confidence.
Confidence is a data-quality description in [0, 1] (history coverage,
freshness, source tier) - NOT a forecast probability. Divergence is never
translated into buy/sell signals or position advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import pandas as pd

from macro_compass.market.config import (
    CONFIRMED_NEGATIVE,
    CONFIRMED_POSITIVE,
    DIVERGENCE_STATES,
    MIXED,
    NEGATIVE_MACRO_DIVERGENCE,
    POSITIVE_MACRO_DIVERGENCE,
)
from macro_compass.signals.registry import SignalRegistry
from macro_compass.transforms.pipeline import apply_chain
from macro_compass.transforms.stats import rolling_percentile

MISSING_INPUT = "MISSING_INPUT"  # no canonical data for the declared series
READY = "READY"                  # every declared metric computable
WARMUP = "WARMUP"                # real data present, declared window not met

# divergence fields are filled by classify_divergence (Phase 3)


@dataclass
class MarketConfirmation:
    """One market signal's metrics plus its divergence classification."""

    signal_id: str
    series_id: str
    status: str  # READY / WARMUP / MISSING_INPUT
    direction: str  # rising-series convention from market.yaml
    as_of: Optional[pd.Timestamp] = None
    history_start: Optional[pd.Timestamp] = None
    # raw basis values (pct_change fraction or delta in percent points)
    move_1m: Optional[float] = None
    move_3m: Optional[float] = None
    trend_6m: Optional[float] = None
    percentile: Optional[float] = None
    # direction-ADJUSTED values: positive = supportive of the mechanism
    adj_move_1m: Optional[float] = None
    adj_move_3m: Optional[float] = None
    adj_trend_6m: Optional[float] = None
    adj_percentile: Optional[float] = None
    threshold_trend_6m: Optional[float] = None
    market_direction: int = 0  # +1 / 0 / -1
    history_length: int = 0
    percentile_window: int = 0
    freshness_days: Optional[int] = None
    stale: bool = False
    provenance: str = "unknown"
    source: str = ""
    # --- divergence fields (Phase 3) ---
    macro_score: Optional[float] = None
    macro_direction: int = 0
    macro_reference: tuple = ()
    state: Optional[str] = None
    agreement: Optional[str] = None  # agree / diverge / None (undirected)
    confidence: Optional[dict] = None  # coverage/freshness/source_quality/composite

    def __post_init__(self) -> None:
        if self.state is not None and self.state not in DIVERGENCE_STATES:
            raise ValueError(f"unknown divergence state: {self.state!r}")


def _single_input_series_id(signal_id: str, spec) -> str:
    inputs = list(spec.inputs)
    if len(inputs) != 1:
        raise ValueError(
            f"market signal '{signal_id}' must declare exactly one input series, "
            f"got {[i.series_id for i in inputs]}"
        )
    return inputs[0].series_id


def _move_basis(values: pd.Series, move: str, periods: int) -> pd.Series:
    """1M/3M/6M basis from the frozen transform whitelist."""
    return apply_chain(values, [{"type": move, "periods": periods}])


def compute_market_metrics(
    registry: SignalRegistry,
    market_config: Mapping,
    series: Mapping[str, pd.Series],
    today: pd.Timestamp,
    provenance_by_series: Optional[Mapping[str, str]] = None,
    sources_by_series: Optional[Mapping[str, str]] = None,
) -> dict[str, MarketConfirmation]:
    """Compute 1M/3M/6M moves and the rolling percentile for every declared
    market signal, with the configured direction conventions applied."""
    today = pd.Timestamp(today)
    provenance_by_series = provenance_by_series or {}
    sources_by_series = sources_by_series or {}
    results: dict[str, MarketConfirmation] = {}

    for signal_id, spec in registry.by_layer("market").items():
        signal_cfg = (market_config.get("signals") or {}).get(signal_id)
        if signal_cfg is None:
            raise ValueError(
                f"config/market.yaml declares no conventions for market signal '{signal_id}'"
            )
        series_id = _single_input_series_id(signal_id, spec)
        windows = signal_cfg["windows"]
        sign = 1.0 if signal_cfg["direction"] == "positive" else -1.0
        threshold = float(signal_cfg["thresholds"]["trend_6m"])

        result = MarketConfirmation(
            signal_id=signal_id,
            series_id=series_id,
            status=MISSING_INPUT,
            direction=signal_cfg["direction"],
            threshold_trend_6m=threshold,
            percentile_window=int(windows["percentile"]),
            provenance=provenance_by_series.get(series_id, "unknown"),
            source=str(sources_by_series.get(series_id, "")),
        )
        results[signal_id] = result

        values = series.get(series_id)
        if values is None or len(values) == 0:
            continue  # MISSING_INPUT: every metric stays explicitly null

        cleaned = values.dropna()
        cleaned.index = pd.to_datetime(cleaned.index)
        cleaned = cleaned.sort_index()
        if cleaned.empty:
            continue

        result.as_of = cleaned.index[-1]
        result.history_start = cleaned.index[0]
        result.history_length = int(len(cleaned))
        result.freshness_days = int((today.normalize() - result.as_of).days)

        basis_1m = _move_basis(cleaned, signal_cfg["move"], int(windows["move_1m"]))
        basis_3m = _move_basis(cleaned, signal_cfg["move"], int(windows["move_3m"]))
        basis_6m = _move_basis(cleaned, signal_cfg["move"], int(windows["trend_6m"]))
        percentile = rolling_percentile(cleaned, window=int(windows["percentile"]))

        result.move_1m = _latest(basis_1m)
        result.move_3m = _latest(basis_3m)
        result.trend_6m = _latest(basis_6m)
        result.percentile = _latest(percentile)
        result.adj_move_1m = None if result.move_1m is None else sign * result.move_1m
        result.adj_move_3m = None if result.move_3m is None else sign * result.move_3m
        result.adj_trend_6m = None if result.trend_6m is None else sign * result.trend_6m
        if result.percentile is None:
            result.adj_percentile = None
        elif sign > 0:
            result.adj_percentile = result.percentile
        else:
            result.adj_percentile = 1.0 - result.percentile

        missing_metrics = any(
            value is None for value in (result.move_1m, result.move_3m, result.trend_6m, result.percentile)
        )
        insufficient_history = result.history_length < max(
            int(windows["percentile"]), int(windows["trend_6m"]) + 1
        )
        if missing_metrics or insufficient_history:
            result.status = WARMUP
        else:
            result.status = READY

        # market direction: the 6M trend beyond its threshold, confirmed by a
        # 3M move that does not contradict the sign. 1M and percentile are
        # reported context, never a silent override.
        if result.status == READY:
            if result.adj_trend_6m >= threshold and result.adj_move_3m > 0:
                result.market_direction = 1
            elif result.adj_trend_6m <= -threshold and result.adj_move_3m < 0:
                result.market_direction = -1

    return results


def _latest(basis: pd.Series) -> Optional[float]:
    value = basis.iloc[-1] if len(basis) else float("nan")
    return None if pd.isna(value) else float(value)


def classify_divergence(
    metrics: Mapping[str, MarketConfirmation],
    factor_results: Mapping,
    market_config: Mapping,
) -> dict[str, MarketConfirmation]:
    """Fill the divergence fields of every metric result in place.

    macro_direction is the sign of the mean of the reference factors' latest
    scores (factor-layer OUTPUTS - raw series are unreachable here) beyond
    the declared threshold; the five states follow the market.yaml naming
    convention. Divergence is never translated into buy/sell advice.
    """
    threshold = float((market_config.get("thresholds") or {}).get("macro_score", 0.10))
    for signal_id, result in metrics.items():
        signal_cfg = (market_config.get("signals") or {}).get(signal_id) or {}
        references = tuple(signal_cfg.get("macro_reference") or ())
        result.macro_reference = references

        scores = [
            float(factor_results[factor].score)
            for factor in references
            if factor in factor_results and factor_results[factor].score is not None
        ]
        macro_score = sum(scores) / len(scores) if scores else None
        result.macro_score = macro_score
        if macro_score is None:
            result.macro_direction = 0
        elif macro_score >= threshold:
            result.macro_direction = 1
        elif macro_score <= -threshold:
            result.macro_direction = -1
        else:
            result.macro_direction = 0

        macro, market = result.macro_direction, result.market_direction
        if macro == 1 and market == 1:
            result.state = CONFIRMED_POSITIVE
        elif macro == -1 and market == -1:
            result.state = CONFIRMED_NEGATIVE
        elif macro == 1 and market == -1:
            result.state = POSITIVE_MACRO_DIVERGENCE
        elif macro == -1 and market == 1:
            result.state = NEGATIVE_MACRO_DIVERGENCE
        else:
            result.state = MIXED

        if macro == 0 or market == 0:
            result.agreement = None
        elif macro == market:
            result.agreement = "agree"
        else:
            result.agreement = "diverge"
    return metrics


def compute_market_confirmations(
    registry: SignalRegistry,
    market_config: Mapping,
    series: Mapping[str, pd.Series],
    factor_results: Mapping,
    staleness: Mapping[str, int],
    macro_config: Mapping,
    today: pd.Timestamp,
    provenance_by_series: Optional[Mapping[str, str]] = None,
    sources_by_series: Optional[Mapping[str, str]] = None,
) -> dict[str, MarketConfirmation]:
    """Full market layer: metrics (Phase 2) + divergence states (Phase 3)."""
    metrics = compute_market_metrics(
        registry, market_config, series, today, provenance_by_series, sources_by_series
    )
    classify_divergence(metrics, factor_results, market_config)
    for result in metrics.values():
        result.confidence = _confidence(result, staleness, macro_config)
    return metrics


def _confidence(
    result: MarketConfirmation, staleness: Mapping[str, int], macro_config: Mapping
) -> dict:
    """Data-quality description in [0, 1], three documented components.

    coverage      - history sufficiency of the declared percentile window
    freshness     - 1.0 when the latest observation is within the series'
                    max_staleness_days budget, else 0.0
    source_quality- canonical source tier from macro.yaml (aggregator access
                    layers score lower than official machine-readable sources)
    """
    conf = macro_config.get("confidence") or {}
    default_budget = int(conf.get("default_max_staleness_days", 90))
    budget = int(staleness.get(result.series_id, default_budget))
    fresh = (
        1.0 if result.freshness_days is not None and result.freshness_days <= budget else 0.0
    )
    tiers = conf.get("source_quality") or {}
    source_component = float(
        tiers.get(result.source.upper(), conf.get("default_source_quality", 0.5))
    )
    coverage = (
        min(1.0, result.history_length / result.percentile_window)
        if result.percentile_window
        else 0.0
    )
    return {
        "coverage": coverage,
        "freshness": fresh,
        "source_quality": source_component,
        "composite": (coverage + fresh + source_component) / 3.0,
    }
