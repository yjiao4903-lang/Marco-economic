"""Structural Risk engine (V2.6).

Computes the three MASTER SPEC structural fragility signals (S1 credit-to-GDP
gap, S2 debt service ratio, S3 property vulnerability) as medium/long-term
DIAGNOSTICS. Pure functions throughout: canonical series, the registry
declarations (``config/signals.yaml``) and the declared priors
(``config/structural.yaml``) go in, readings come out - no network, no storage
side effects.

ISOLATION (MASTER SPEC section 7, ARCHITECTURE): structural risk NEVER enters
the short-term Asset Score. This package is a standalone diagnostic layer; the
asset engine only reads the four core factor outputs and never imports this
package (locked by source-level tests).

Status semantics follow V1.5D (READY / WARMUP / PARTIAL / MISSING_INPUT):
* MISSING_INPUT - no canonical data for the declared input series;
* WARMUP        - real data present but shorter than the declared percentile
                  window (diagnostics not fully positioned yet);
* READY         - every declared metric computable.

No-data / stale behaviour (task spec): when there is no data OR the latest
quarterly observation is older than its staleness budget, the REPORT entry
point emits ``NO_SIGNAL`` explicitly - never a silent fallback and never a
synthetic placeholder. The engine itself keeps the V1.5D statuses and exposes
``stale`` so the report can make that call without duplicating logic.

Computation reuses the frozen V1.5A transform whitelist only (``apply_chain``,
``rolling_percentile``): the level chain declared in signals.yaml (``level``
for S1/S2) gives the raw basis, the percentile positions it against its own
history, and a ``delta`` over the declared quarters gives the trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

import pandas as pd

from macro_compass.signals.registry import SignalRegistry
from macro_compass.transforms.pipeline import apply_chain
from macro_compass.transforms.stats import rolling_percentile

MISSING_INPUT = "MISSING_INPUT"  # no canonical data for the declared series
READY = "READY"                  # every declared metric computable
WARMUP = "WARMUP"                # real data present, declared window not met
PARTIAL = "PARTIAL"              # proxy pool: some (not all) inputs have data

# default staleness budget (days) when the series has no data_sources route
DEFAULT_STALENESS_DAYS = 260


@dataclass
class StructuralReading:
    """One structural signal's diagnostic reading."""

    signal_id: str
    series_id: str
    status: str  # READY / WARMUP / PARTIAL / MISSING_INPUT (V1.5D semantics)
    direction: str  # rising-series fragility convention from structural.yaml
    as_of: Optional[pd.Timestamp] = None
    history_start: Optional[pd.Timestamp] = None
    history_length: int = 0
    # for multi-input proxy pools (S3): the declared pool and how many landed
    series_ids: list[str] = field(default_factory=list)
    inputs_total: int = 0
    available_count: int = 0
    # latest raw basis value (the gap / DSR in percent)
    level: Optional[float] = None
    # rolling percentile of the level against its own history (0..1)
    percentile: Optional[float] = None
    # change of the level over the declared trend_quarters (in percent points)
    trend: Optional[float] = None
    trend_quarters: int = 0
    percentile_window: int = 0
    freshness_days: Optional[int] = None
    stale: bool = False
    # diagnostic label from the declared thresholds (READY only)
    diagnostic: Optional[str] = None
    message: str = ""
    provenance: str = "unknown"
    source: str = ""


def _latest(basis: pd.Series) -> Optional[float]:
    value = basis.iloc[-1] if len(basis) else float("nan")
    return None if pd.isna(value) else float(value)


def _diagnostic(signal_id: str, thresholds: Mapping, level, percentile) -> Optional[str]:
    """Diagnostic label from the declared thresholds.

    S1-style (level thresholds on the gap in percent): ELEVATED when above the
    BIS 'red zone' prior, ABOVE_TREND when the gap is positive (credit above
    its HP trend), else BELOW_TREND.
    S2-style (percentile thresholds of the DSR's own history): ELEVATED /
    MODERATE / BENIGN.
    """
    if level is None:
        return None
    if "elevated" in thresholds:  # S1: level-based
        if level > float(thresholds["elevated"]):
            return "ELEVATED"
        if level > float(thresholds.get("above_trend", 0.0)):
            return "ABOVE_TREND"
        return "BELOW_TREND"
    if "elevated_percentile" in thresholds and percentile is not None:  # S2
        if percentile >= float(thresholds["elevated_percentile"]):
            return "ELEVATED"
        if percentile >= float(thresholds.get("moderate_percentile", 0.5)):
            return "MODERATE"
        return "BENIGN"
    return None


def compute_structural_readings(
    registry: SignalRegistry,
    structural_config: Mapping,
    series: Mapping[str, pd.Series],
    today: pd.Timestamp,
    staleness: Optional[Mapping[str, int]] = None,
    provenance_by_series: Optional[Mapping[str, str]] = None,
    sources_by_series: Optional[Mapping[str, str]] = None,
) -> dict[str, StructuralReading]:
    """Compute the diagnostic reading of every declared structural signal."""
    today = pd.Timestamp(today)
    staleness = staleness or {}
    provenance_by_series = provenance_by_series or {}
    sources_by_series = sources_by_series or {}
    results: dict[str, StructuralReading] = {}

    for signal_id, spec in registry.by_layer("structural").items():
        cfg = (structural_config.get("signals") or {}).get(signal_id)
        if cfg is None:
            raise ValueError(
                f"config/structural.yaml declares no conventions for structural signal '{signal_id}'"
            )
        inputs = list(spec.inputs)
        if not inputs:
            # No declared inputs (defensive: all structural signals now declare
            # at least one) -> MISSING_INPUT, reported as NO_SIGNAL.
            results[signal_id] = StructuralReading(
                signal_id=signal_id,
                series_id="",
                status=MISSING_INPUT,
                direction=cfg["direction"],
                message="未声明输入；不能产生读数",
            )
            continue

        def _clean(series_id: str) -> Optional[pd.Series]:
            values = series.get(series_id)
            if values is None or len(values) == 0:
                return None
            clean = values.dropna()
            clean.index = pd.to_datetime(clean.index)
            clean = clean.sort_index()
            return None if clean.empty else clean

        if len(inputs) == 1:
            # -------------------------------------------------------------- single-input
            series_id = inputs[0].series_id
            reading = StructuralReading(
                signal_id=signal_id,
                series_id=series_id,
                series_ids=[series_id],
                inputs_total=1,
                available_count=1,
                status=MISSING_INPUT,
                direction=cfg["direction"],
                percentile_window=int(cfg["percentile_window"]),
                trend_quarters=int(cfg["trend_quarters"]),
                provenance=provenance_by_series.get(series_id, "unknown"),
                source=str(sources_by_series.get(series_id, "")),
            )
            results[signal_id] = reading

            cleaned = _clean(series_id)
            if cleaned is None:
                reading.message = f"无 canonical 数据：{series_id}"
                continue  # MISSING_INPUT

            reading.as_of = cleaned.index[-1]
            reading.history_start = cleaned.index[0]
            reading.history_length = int(len(cleaned))
            reading.freshness_days = int((today.normalize() - reading.as_of).days)
            reading.stale = reading.freshness_days > int(
                staleness.get(series_id, DEFAULT_STALENESS_DAYS)
            )

            level_basis = apply_chain(cleaned, [dict(step) for step in spec.transforms])
            percentile = rolling_percentile(
                level_basis, window=int(cfg["percentile_window"])
            )
            trend = apply_chain(
                level_basis, [{"type": "delta", "periods": int(cfg["trend_quarters"])}]
            )

            reading.level = _latest(level_basis)
            reading.percentile = _latest(percentile)
            reading.trend = _latest(trend)

            if reading.history_length >= reading.percentile_window:
                reading.status = READY
                reading.diagnostic = _diagnostic(
                    signal_id,
                    cfg.get("thresholds") or {},
                    reading.level,
                    reading.percentile,
                )
            else:
                reading.status = WARMUP
                reading.message = (
                    f"历史 {reading.history_length} 期 < 声明窗口 {reading.percentile_window}"
                )
            if reading.stale:
                reading.message = (
                    f"最新值 {reading.as_of.date().isoformat()} 距今 {reading.freshness_days} 天"
                    f" 超过预算 {staleness.get(series_id, DEFAULT_STALENESS_DAYS)} 天"
                )
            continue

        # ---------------------------------------------------- multi-input proxy pool (S3)
        # Each proxy is positioned against its own history as a rolling
        # percentile (common 0..1 scale for heterogeneous units), resampled to a
        # quarterly index, then the AVAILABLE proxies are averaged (equal-weight
        # declared prior, never an Asset Score input). Missing categories leave
        # the composite PARTIAL - never a synthetic fill.
        available_id = [sid for sid in (i.series_id for i in inputs) if _clean(sid) is not None]
        reading = StructuralReading(
            signal_id=signal_id,
            series_id=", ".join(i.series_id for i in inputs),
            series_ids=[i.series_id for i in inputs],
            inputs_total=len(inputs),
            available_count=len(available_id),
            status=PARTIAL if available_id else MISSING_INPUT,
            direction=cfg["direction"],
            percentile_window=int(cfg["percentile_window"]),
            trend_quarters=int(cfg["trend_quarters"]),
            provenance=(
                "mixed"
                if available_id
                else "unknown"
            ),
            source=", ".join(
                str(sources_by_series.get(sid, "")) for sid in available_id if sources_by_series.get(sid)
            ),
        )
        results[signal_id] = reading
        if not available_id:
            reading.message = f"代理池 {len(inputs)} 端均无 canonical 数据"
            continue  # MISSING_INPUT

        pool = {}
        for sid in available_id:
            cleaned = _clean(sid)
            basis = apply_chain(cleaned, [dict(step) for step in spec.transforms])
            pct = rolling_percentile(basis, window=int(cfg["percentile_window"]))
            pool[sid] = pct.rename(sid).to_frame().resample("QE").last()

        composite = (
            pd.concat(list(pool.values()), axis=1).dropna(how="all").mean(axis=1, skipna=True)
        )
        valid = composite.dropna()
        reading.history_length = int(len(valid))
        if not valid.empty:
            reading.as_of = valid.index[-1]
            reading.history_start = valid.index[0]
            reading.freshness_days = int((today.normalize() - reading.as_of).days)
            # composite is as fresh as its freshest available proxy; stale if
            # the composite's latest quarter exceeds the loosest (max) budget.
            max_budget = max(
                int(staleness.get(sid, DEFAULT_STALENESS_DAYS)) for sid in available_id
            )
            reading.stale = reading.freshness_days > max_budget
            trend = apply_chain(
                valid, [{"type": "delta", "periods": int(cfg["trend_quarters"])}]
            )
            reading.level = _latest(valid)
            reading.percentile = _latest(valid)
            reading.trend = _latest(trend)
            if reading.history_length >= reading.percentile_window:
                reading.diagnostic = _diagnostic(
                    signal_id,
                    cfg.get("thresholds") or {},
                    reading.level,
                    reading.percentile,
                )

        missing = [s for s in reading.series_ids if s not in available_id]
        if missing:
            reading.status = PARTIAL  # some categories have no data (honest)
        elif reading.history_length >= reading.percentile_window:
            reading.status = READY
        else:
            reading.status = WARMUP

        if reading.history_length < reading.percentile_window:
            verbose = (
                "（代理百分位窗口内有效值不足）" if valid.empty else ""
            )
            reading.message = (
                f"历史 {reading.history_length} 期 < 声明窗口 "
                f"{reading.percentile_window}{verbose}"
            )
        if missing:
            reading.message = (
                f"代理池可用 {reading.available_count}/{reading.inputs_total}"
                f"（缺失：{', '.join(missing)}）"
                + (f"；{reading.message}" if reading.message else "")
            )
        if reading.stale:
            reading.message = (
                f"综合最新季度 {reading.as_of.date().isoformat()} 距今 "
                f"{reading.freshness_days} 天 超过预算 {max_budget} 天"
            )
    return results
