"""Signal Engine (V1.5B): level + momentum scoring for the 15 core signals.

Consumes the frozen V1.3 declarations (``config/signals.yaml`` via
``signals/registry.py``) and the frozen V1.5A transform whitelist
(``transforms/pipeline.py``). Everything here is a pure function: canonical
DataFrames and config dicts go in, signal tables come out. No network access,
no storage side effects - persistence is the caller's (script) job.

Output contract (ARCHITECTURE section 8, one row per date per signal)::

    signal_id, date, level, level_score, momentum, momentum_score,
    score, freshness, coverage, status

Score mapping (basis -> score in [-1, 1], no black box - see
``config/macro.yaml`` for the declared scales):

* basis type ``rolling_percentile`` (already bounded [0, 1]):
  ``score = clip(2 * (basis - neutral), -1, 1)`` using the signal's declared
  ``neutral`` anchor;
* basis type ``robust_zscore``: clipped to ``[-zscore_clip, +zscore_clip]``
  then divided by it;
* any other (unbounded) basis: ``score = clip(basis / scale, -1, 1)`` with a
  per-signal scale declared in ``config/macro.yaml``.

Signals with ``direction: negative`` have their scores multiplied by -1, so
``score > 0`` always means "the mechanism is improving".

Composite combination (all explainable, per the V1.3 declarations):

* ``single``  - one input only;
* ``fallback``- inputs declare preferred/fallback roles; the first input with
  data (declared order) is used;
* ``difference`` - declared ``combination: difference``: the raw legs are
  subtracted (declared order) FIRST, then the transform chain runs on the
  composite. Contribution breakdown = signed share of each leg in the raw
  composite value (the chain may be nonlinear, so shares are exact pre-
  transform arithmetic, not score points);
* ``average`` - multi-input signals without a declared combination: the
  transform chain runs PER INPUT, and the composite is the equal-weight mean
  of the per-input scores. Contribution breakdown = additive score points
  (``score_i / N_available``, so contributions sum to the composite score).

Missing inputs never become zeros: dates without a computable value carry
null scores and an explicit ``coverage`` of the available-input share.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

import pandas as pd

from macro_compass.signals.registry import (
    MISSING_INPUT,
    PARTIAL,
    READY,
    SignalSpec,
)
from macro_compass.transforms.pipeline import apply_chain

# ARCHITECTURE section 8 output contract.
CONTRACT_COLUMNS = [
    "signal_id",
    "date",
    "level",
    "level_score",
    "momentum",
    "momentum_score",
    "score",
    "freshness",
    "coverage",
    "status",
]


@dataclass
class SignalComputation:
    """Result of computing one signal over its available inputs."""

    signal_id: str
    frame: pd.DataFrame  # CONTRACT_COLUMNS; empty when no input has data
    status: str  # READY / PARTIAL / MISSING_INPUT (registry semantics)
    combination: str  # single / fallback / difference / average
    # Per-date, per-input breakdown. Semantics depend on ``combination``:
    # average/fallback/single -> additive score points summing to `score`;
    # difference -> signed shares of the raw pre-transform composite value.
    # Column order follows the declared input order.
    contributions: Optional[pd.DataFrame] = None
    # series_id -> "synthetic" | "real" for the inputs that have data
    # (empty when the caller does not supply provenance).
    input_provenance: dict[str, str] = field(default_factory=dict)
    # series_id -> canonical `source` label of the latest observation
    input_sources: dict[str, str] = field(default_factory=dict)
    # declared input series ids (spec.inputs order); declared-missing ones included
    input_series_ids: list[str] = field(default_factory=list)

    @property
    def provenance(self) -> str:
        """synthetic / real / mixed over the inputs that have data."""
        values = sorted(set(self.input_provenance.values()))
        if not values:
            return "unknown"
        if len(values) == 1:
            return values[0]
        return "mixed"

    def latest(self) -> Optional[pd.Series]:
        """The most recent row with a computable score, if any."""
        if self.frame.empty:
            return None
        scored = self.frame[self.frame["score"].notna()]
        if scored.empty:
            return None
        return scored.iloc[-1]


# ---------------------------------------------------------------------------
# score mapping


def _basis_scale(macro_config: Mapping, signal_id: str, role: str) -> float:
    scales = (macro_config.get("score_mapping") or {}).get("scales") or {}
    per_signal = scales.get(signal_id) or {}
    default = scales.get("default") or {}
    value = per_signal.get(role, default.get(role, 2.0 if role == "level" else 1.0))
    if not value or value <= 0:
        raise ValueError(
            f"macro.yaml: score scale for {signal_id} ({role}) must be > 0, got {value!r}"
        )
    return float(value)


def _zscore_clip(macro_config: Mapping) -> float:
    value = (macro_config.get("score_mapping") or {}).get("zscore_clip", 3.0)
    if not value or value <= 0:
        raise ValueError(f"macro.yaml: zscore_clip must be > 0, got {value!r}")
    return float(value)


def _clip(series: pd.Series) -> pd.Series:
    return series.clip(lower=-1.0, upper=1.0)


def map_score(
    basis: pd.Series,
    basis_type: str,
    neutral: float,
    direction: str,
    scale: float,
    zscore_clip: float,
) -> pd.Series:
    """Map a transform-chain basis to a score in [-1, 1] (documented rules)."""
    if basis_type == "rolling_percentile":
        score = 2.0 * (basis - float(neutral))
    elif basis_type == "robust_zscore":
        score = basis.clip(lower=-zscore_clip, upper=zscore_clip) / zscore_clip
    else:
        score = basis / float(scale)
    score = _clip(score)
    if direction == "negative":
        score = -score
    return score


# ---------------------------------------------------------------------------
# combination helpers


def resolve_combination(spec: SignalSpec) -> str:
    """Explainable combination semantics for one declared signal."""
    if len(spec.inputs) == 1:
        return "single"
    if (spec.combination or "").strip().lower() == "difference":
        return "difference"
    roles = {i.role for i in spec.inputs}
    if roles & {"preferred", "fallback"}:
        return "fallback"
    return "average"


def _basis_type(spec: SignalSpec) -> str:
    """Type of the level basis = last declared transform step."""
    return spec.transforms[-1].type if spec.transforms else "level"


def _momentum_type(spec: SignalSpec) -> Optional[str]:
    return spec.momentum_transform.type if spec.momentum_transform is not None else None


def _level_basis(series: pd.Series, spec: SignalSpec) -> pd.Series:
    return apply_chain(series, [dict(step) for step in spec.transforms])


def _momentum_basis(level_basis: pd.Series, spec: SignalSpec) -> Optional[pd.Series]:
    if spec.momentum_transform is None:
        return None
    return apply_chain(level_basis, [dict(spec.momentum_transform)])


def _weighted_component(
    level_score: pd.Series, momentum_score: pd.Series, spec: SignalSpec
) -> pd.Series:
    """score = w_l * level_score + w_m * momentum_score, renormalised over the
    components that are actually present (never silently zero-filled)."""
    if momentum_score is None:
        momentum_score = pd.Series(float("nan"), index=level_score.index)
    wl = float(spec.level_weight)
    wm = float(spec.momentum_weight)
    numerator = wl * level_score.fillna(0.0) + wm * momentum_score.fillna(0.0)
    denominator = wl * level_score.notna() + wm * momentum_score.notna()
    return numerator.where(denominator > 0) / denominator.where(denominator > 0)


def _empty_frame(signal_id: str, status: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_id": pd.Series(dtype=object),
            "date": pd.Series(dtype="datetime64[ns]"),
            "level": pd.Series(dtype=float),
            "level_score": pd.Series(dtype=float),
            "momentum": pd.Series(dtype=float),
            "momentum_score": pd.Series(dtype=float),
            "score": pd.Series(dtype=float),
            "freshness": pd.Series(dtype=int),
            "coverage": pd.Series(dtype=float),
            "status": pd.Series(dtype=object),
        }
    ).assign(signal_id=signal_id, status=status)


def _finalize(
    signal_id: str,
    status: str,
    index: pd.DatetimeIndex,
    level: pd.Series,
    level_score: pd.Series,
    momentum: Optional[pd.Series],
    momentum_score: Optional[pd.Series],
    score: pd.Series,
    coverage: pd.Series,
    today: pd.Timestamp,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "level": level.reindex(index),
            "level_score": level_score.reindex(index),
            "momentum": momentum.reindex(index) if momentum is not None else float("nan"),
            "momentum_score": (
                momentum_score.reindex(index) if momentum_score is not None else float("nan")
            ),
            "score": score.reindex(index),
            "coverage": coverage.reindex(index),
        }
    )
    frame.index.name = "date"
    frame = frame.reset_index()
    frame.insert(0, "signal_id", signal_id)
    frame["freshness"] = (today.normalize() - frame["date"]).dt.days
    frame["status"] = status
    return frame[CONTRACT_COLUMNS]


# ---------------------------------------------------------------------------
# main entry point


def compute_signal(
    spec: SignalSpec,
    input_series: Mapping[str, pd.Series],
    macro_config: Mapping,
    today: pd.Timestamp,
    input_provenance: Optional[Mapping[str, str]] = None,
    input_sources: Optional[Mapping[str, str]] = None,
) -> SignalComputation:
    """Compute one declared signal from canonical input series.

    ``input_series`` maps series_id -> value Series indexed by observation
    date (entries absent or empty = no canonical data for that series). The
    Series are not modified. ``input_provenance`` / ``input_sources`` are
    caller-supplied metadata (series_id -> synthetic|real, series_id ->
    canonical source label) used for reporting only.
    """
    today = pd.Timestamp(today)
    series: dict[str, pd.Series] = {}
    for input_spec in spec.inputs:
        values = input_series.get(input_spec.series_id)
        if values is not None and len(values) > 0:
            cleaned = values.dropna()
            cleaned.index = pd.to_datetime(cleaned.index)
            if not cleaned.empty:
                series[input_spec.series_id] = cleaned.sort_index()

    available_ids = [i.series_id for i in spec.inputs if i.series_id in series]
    missing_ids = [i.series_id for i in spec.inputs if i.series_id not in series]
    if not available_ids:
        status = MISSING_INPUT
    elif missing_ids:
        status = PARTIAL
    else:
        status = READY

    provenance = {
        sid: str(input_provenance.get(sid, "real")) for sid in available_ids
    } if input_provenance is not None else {}
    sources = {sid: str(input_sources.get(sid, "")) for sid in available_ids} if (
        input_sources is not None
    ) else {}

    combination = resolve_combination(spec)
    if status == MISSING_INPUT:
        return SignalComputation(
            signal_id=spec.signal_id,
            frame=_empty_frame(spec.signal_id, status),
            status=status,
            combination=combination,
            contributions=None,
            input_provenance=provenance,
            input_sources=sources,
            input_series_ids=[i.series_id for i in spec.inputs],
        )

    zscore_clip = _zscore_clip(macro_config)
    neutral = float(spec.neutral) if spec.neutral is not None else 0.0
    direction = spec.direction or "positive"

    if combination == "difference":
        if len(available_ids) < len(spec.inputs):
            # A difference needs every leg: with one missing the composite is
            # undefined - emit explicit null-score rows, never a partial diff.
            return _incomplete_difference(
                spec, series, status, combination, provenance, sources, today
            )
        return _compute_difference(
            spec, series, status, combination, provenance, sources,
            macro_config, today, neutral, direction, zscore_clip,
        )
    if combination == "fallback":
        return _compute_fallback(
            spec, series, available_ids, status, combination, provenance, sources,
            macro_config, today, neutral, direction, zscore_clip,
        )
    return _compute_single_or_average(
        spec, series, status, combination, provenance, sources,
        macro_config, today, neutral, direction, zscore_clip,
    )


def _incomplete_difference(
    spec, series, status, combination, provenance, sources, today,
) -> SignalComputation:
    """Difference composite with at least one missing leg: no date is
    computable, but the declared-input share is still reported explicitly."""
    union = _union_index(series)
    n_declared = len(spec.inputs)
    coverage = pd.Series(
        len(series) / n_declared, index=union, dtype=float
    ) if n_declared else pd.Series(0.0, index=union, dtype=float)
    frame = _finalize(
        spec.signal_id, status, union,
        pd.Series(float("nan"), index=union),
        pd.Series(float("nan"), index=union),
        None, None,
        pd.Series(float("nan"), index=union),
        coverage, today,
    )
    return SignalComputation(
        signal_id=spec.signal_id, frame=frame, status=status,
        combination=combination, contributions=None,
        input_provenance=provenance, input_sources=sources,
        input_series_ids=[i.series_id for i in spec.inputs],
    )


def _leg_coefficients(leg_names: list[str]) -> list[tuple[str, float]]:
    """Composite coefficients: first leg +1, every subsequent leg -1
    (combination: difference subtracts in declared order)."""
    return [
        (name, 1.0 if position == 0 else -1.0)
        for position, name in enumerate(leg_names)
    ]


def _compute_difference(
    spec, series, status, combination, provenance, sources,
    macro_config, today, neutral, direction, zscore_clip,
) -> SignalComputation:
    """combination: difference - legs are subtracted raw, then the chain runs
    on the composite. All legs must be present on a date for it to compute."""
    legs = [series[i.series_id] for i in spec.inputs]
    aligned = pd.concat(legs, axis=1, join="inner").dropna()
    leg_names = [i.series_id for i in spec.inputs]
    aligned.columns = leg_names

    composite = aligned[leg_names[0]].copy()
    for name in leg_names[1:]:
        composite = composite - aligned[name]

    level_basis = _level_basis(composite, spec)
    momentum_basis = _momentum_basis(level_basis, spec)

    level_score = map_score(
        level_basis, _basis_type(spec), neutral, direction,
        _basis_scale(macro_config, spec.signal_id, "level"), zscore_clip,
    )
    momentum_score = None
    if momentum_basis is not None:
        momentum_score = map_score(
            momentum_basis, _momentum_type(spec), neutral, direction,
            _basis_scale(macro_config, spec.signal_id, "momentum"), zscore_clip,
        )
    score = _weighted_component(level_score, momentum_score, spec)

    coverage = pd.Series(1.0, index=level_basis.index)
    coverage = coverage.reindex(_union_index(series), fill_value=0.0)

    # Contribution breakdown: signed share of each leg in the raw composite
    # value on each date (exact pre-transform arithmetic). Each leg's raw
    # value is multiplied by its coefficient in the composite (+1 for the
    # first leg, -1 for each subtracted leg) and divided by the sum of
    # absolute leg values; the parts sum to composite/abs_sum in [-1, 1],
    # NaN when the composite cancels to 0.
    abs_sum = aligned.abs().sum(axis=1)
    coefficients = pd.Series(
        {name: sign for name, sign in _leg_coefficients(leg_names)},
        dtype=float,
    )
    contributions = aligned.mul(coefficients, axis=1).div(
        abs_sum.where(abs_sum > 0), axis=0
    ).where(abs_sum > 0)

    frame = _finalize(
        spec.signal_id, status, level_basis.index,
        level_basis, level_score, momentum_basis, momentum_score,
        score, coverage, today,
    )
    return SignalComputation(
        signal_id=spec.signal_id, frame=frame, status=status,
        combination=combination, contributions=contributions,
        input_provenance=provenance, input_sources=sources,
        input_series_ids=[i.series_id for i in spec.inputs],
    )


def _compute_fallback(
    spec, series, available_ids, status, combination, provenance, sources,
    macro_config, today, neutral, direction, zscore_clip,
) -> SignalComputation:
    """combination: fallback - use the first input with data (declared
    priority order). Coverage still reports the declared-input share."""
    chosen = available_ids[0]
    values = series[chosen]

    level_basis = _level_basis(values, spec)
    momentum_basis = _momentum_basis(level_basis, spec)
    level_score = map_score(
        level_basis, _basis_type(spec), neutral, direction,
        _basis_scale(macro_config, spec.signal_id, "level"), zscore_clip,
    )
    momentum_score = None
    if momentum_basis is not None:
        momentum_score = map_score(
            momentum_basis, _momentum_type(spec), neutral, direction,
            _basis_scale(macro_config, spec.signal_id, "momentum"), zscore_clip,
        )
    score = _weighted_component(level_score, momentum_score, spec)

    n_declared = len(spec.inputs)
    coverage = pd.Series(1.0 / n_declared, index=level_basis.index)
    coverage = coverage.reindex(_union_index(series), fill_value=0.0)

    contributions = pd.DataFrame({chosen: score}, index=level_basis.index)

    frame = _finalize(
        spec.signal_id, status, level_basis.index,
        level_basis, level_score, momentum_basis, momentum_score,
        score, coverage, today,
    )
    return SignalComputation(
        signal_id=spec.signal_id, frame=frame, status=status,
        combination=combination, contributions=contributions,
        input_provenance=provenance, input_sources=sources,
        input_series_ids=[i.series_id for i in spec.inputs],
    )


def _compute_single_or_average(
    spec, series, status, combination, provenance, sources,
    macro_config, today, neutral, direction, zscore_clip,
) -> SignalComputation:
    """single / average: the chain runs per input; composites are equal-weight
    means of the per-input bases and scores."""
    level_type = _basis_type(spec)
    momentum_type = _momentum_type(spec)
    level_scale = _basis_scale(macro_config, spec.signal_id, "level")
    momentum_scale = _basis_scale(macro_config, spec.signal_id, "momentum")

    per_level: dict[str, pd.Series] = {}
    per_level_score: dict[str, pd.Series] = {}
    per_momentum: dict[str, pd.Series] = {}
    per_momentum_score: dict[str, pd.Series] = {}
    per_input_score: dict[str, pd.Series] = {}
    for input_spec in spec.inputs:
        sid = input_spec.series_id
        if sid not in series:
            continue
        level_basis = _level_basis(series[sid], spec)
        momentum_basis = _momentum_basis(level_basis, spec)
        level_score = map_score(level_basis, level_type, neutral, direction, level_scale, zscore_clip)
        momentum_score = None
        if momentum_basis is not None:
            momentum_score = map_score(
                momentum_basis, momentum_type, neutral, direction, momentum_scale, zscore_clip
            )
        per_level[sid] = level_basis
        per_level_score[sid] = level_score
        if momentum_basis is not None:
            per_momentum[sid] = momentum_basis
            per_momentum_score[sid] = momentum_score
        per_input_score[sid] = _weighted_component(level_score, momentum_score, spec)

    union = _union_index(series)
    n_declared = len(spec.inputs)
    n_available = len(per_level)

    level = pd.concat(per_level, axis=1).mean(axis=1).reindex(union)
    level_score = pd.concat(per_level_score, axis=1).mean(axis=1).reindex(union)
    if per_momentum:
        momentum = pd.concat(per_momentum, axis=1).mean(axis=1).reindex(union)
        momentum_score = pd.concat(per_momentum_score, axis=1).mean(axis=1).reindex(union)
    else:
        momentum = pd.Series(float("nan"), index=union)
        momentum_score = pd.Series(float("nan"), index=union)
    score = _weighted_component(level_score, momentum_score, spec)

    # Coverage per date: share of DECLARED inputs with a computable level
    # basis on that date (transform warm-up rows count as not covered).
    covered = (
        pd.concat(per_level, axis=1).notna().sum(axis=1).reindex(union, fill_value=0)
        / n_declared
    ).astype(float)

    # Contribution breakdown: additive score points; the composite score is
    # the equal-weight mean of the per-input scores, so each available input
    # contributes score_i / N_available and the parts sum to the whole.
    contributions = pd.concat(per_input_score, axis=1).reindex(union)
    contributions = contributions.div(n_available).where(contributions.notna())

    frame = _finalize(
        spec.signal_id, status, union, level, level_score, momentum, momentum_score,
        score, covered, today,
    )
    return SignalComputation(
        signal_id=spec.signal_id, frame=frame, status=status,
        combination=combination, contributions=contributions,
        input_provenance=provenance, input_sources=sources,
        input_series_ids=[i.series_id for i in spec.inputs],
    )


def _union_index(series: Mapping[str, pd.Series]) -> pd.DatetimeIndex:
    union: pd.DatetimeIndex | None = None
    for values in series.values():
        union = values.index if union is None else union.union(values.index)
    return pd.DatetimeIndex([]) if union is None else union.sort_values()


def compute_core_signals(
    registry,  # SignalRegistry
    input_series: Mapping[str, pd.Series],
    macro_config: Mapping,
    today: pd.Timestamp,
    input_provenance: Optional[Mapping[str, str]] = None,
    input_sources: Optional[Mapping[str, str]] = None,
) -> dict[str, SignalComputation]:
    """Compute every layer=core signal; market/structural stay untouched (V1.6)."""
    return {
        signal_id: compute_signal(
            spec, input_series, macro_config, today, input_provenance, input_sources
        )
        for signal_id, spec in registry.core.items()
    }
