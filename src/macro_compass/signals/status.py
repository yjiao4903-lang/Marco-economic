"""Shared signal status resolution + production data loading (V1.5E).

Single source of truth for:

1. the status every report entry point displays
   (``resolve_signal_status`` - registry availability semantics + the
   engine's WARMUP refinement);
2. the production data loading pipeline (canonical -> synthetic filter ->
   per-series frames -> engine computations) used by signal_status /
   macro_report / signal_quality, so no report script duplicates the
   pipeline or its status logic (task spec 47 §5.1).
"""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd

from macro_compass.signals.engine import (
    SignalComputation,
    compute_core_signals,
)
from macro_compass.signals.registry import (
    SignalAvailability,
    SignalRegistry,
    assess_availability,
)


def resolve_signal_status(
    registry: SignalRegistry,
    availability: Mapping[str, SignalAvailability],
    computations: Mapping[str, SignalComputation],
    market_computations: Optional[Mapping] = None,
    structural_computations: Optional[Mapping] = None,
) -> dict[str, str]:
    """One resolved status per signal, consistent across all report entry points.

    Core signals take the engine's computed status (which already encodes
    WARMUP); market signals take the V1.6A market engine's status when the
    caller supplies it (READY / WARMUP / MISSING_INPUT); structural signals
    take the V2.6 structural engine's status when supplied (same semantics).
    Signals without an engine result keep the registry's placeholder semantics
    (DECLARED / MISSING_INPUT).
    """
    resolved: dict[str, str] = {}
    for signal_id, spec in registry.signals.items():
        if spec.layer == "core":
            computation = computations.get(signal_id)
            resolved[signal_id] = (
                computation.status if computation is not None else availability[signal_id].status
            )
        elif spec.layer == "market" and market_computations and signal_id in market_computations:
            resolved[signal_id] = market_computations[signal_id].status
        elif (
            spec.layer == "structural"
            and structural_computations
            and signal_id in structural_computations
        ):
            resolved[signal_id] = structural_computations[signal_id].status
        else:
            resolved[signal_id] = availability[signal_id].status
    return resolved


def load_core_computations(
    registry: SignalRegistry,
    macro_config: Mapping,
    indicators: Optional[Mapping] = None,
    *,
    allow_synthetic: bool = False,
    today: Optional[pd.Timestamp] = None,
) -> dict:
    """Load canonical, apply production synthetic isolation and compute all
    core signals. Returns a namespace with everything the report scripts need:
    ``computations``, ``availability``, ``resolved``, ``series``,
    ``available_series``, ``canonical``.
    """
    from macro_compass import paths
    from macro_compass.storage import canonical_store
    from macro_compass.synthetic_guard import filter_synthetic

    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today()
    markers = macro_config.get("synthetic_markers") or []

    frames = [canonical_store.read_canonical(c) for c in ("macro", "market")]
    frames = [f for f in frames if not f.empty]
    canonical = filter_synthetic(
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(),
        markers,
        allow_synthetic=allow_synthetic,
    )
    series: dict[str, pd.Series] = {}
    for series_id, rows in canonical.groupby("series_id"):
        series[series_id] = (
            rows.assign(date=pd.to_datetime(rows["date"]))
            .drop_duplicates(subset="date", keep="last")
            .sort_values("date")
            .set_index("date")["value"]
            .astype(float)
            .rename(series_id)
        )

    availability = assess_availability(registry, set(series))

    from macro_compass.macro.factors import classify_provenance

    provenance_by_series = classify_provenance(
        canonical.groupby("series_id")["source_file"]
        .agg(lambda s: list(s.dropna().unique()))
        .to_dict(),
        markers,
    )
    computations = compute_core_signals(
        registry,
        series,
        macro_config,
        today,
        input_provenance=provenance_by_series,
        input_sources=canonical.sort_values("import_time")
        .groupby("series_id")["source"]
        .last()
        .to_dict(),
    )
    resolved = resolve_signal_status(registry, availability, computations)

    class _Result:
        pass

    result = _Result()
    result.computations = computations
    result.availability = availability
    result.resolved = resolved
    result.series = series
    result.available_series = set(series)
    result.canonical = canonical
    result.provenance_by_series = provenance_by_series
    result.today = today
    return result
