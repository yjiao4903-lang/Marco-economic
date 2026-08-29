"""V1.5B Signal Engine tests: score mapping, combinations, contract, statuses.

All tests are deterministic (constructed series, fixed ``today``); no network,
no canonical files, no storage side effects.
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.config import load_indicator_config
from macro_compass.signals import (
    MISSING_INPUT,
    PARTIAL,
    READY,
    SignalSpec,
    compute_core_signals,
    compute_signal,
    load_signal_registry,
)
from macro_compass.signals.engine import CONTRACT_COLUMNS, map_score

TODAY = pd.Timestamp("2026-08-29")

MACRO_CONFIG = {
    "score_mapping": {
        "zscore_clip": 3.0,
        "scales": {
            "default": {"level": 2.0, "momentum": 1.0},
            "S1": {"level": 4.0, "momentum": 2.0},
        },
    }
}


def _series(values, start: str = "2026-01-01", freq: str = "D") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, dtype=float, index=index)


def _spec(
    signal_id: str = "T1",
    inputs: list[tuple[str, str]] | None = None,
    transforms: list[dict] | None = None,
    momentum: dict | None = None,
    direction: str = "positive",
    neutral: float = 0.0,
    level_weight: float = 0.5,
    momentum_weight: float = 0.5,
    combination: str | None = None,
) -> SignalSpec:
    return SignalSpec(
        signal_id=signal_id,
        name="test signal",
        layer="core",
        factor="growth",
        mechanism="test mechanism",
        inputs=[{"series_id": sid, "role": role} for sid, role in (inputs or [("A", "level")])],
        transforms=transforms or [{"type": "level"}],
        momentum_transform=momentum,
        direction=direction,
        neutral=neutral,
        level_weight=level_weight,
        momentum_weight=momentum_weight,
        combination=combination,
    )


# --- score mapping -----------------------------------------------------------


def test_percentile_mapping_is_linear_around_neutral() -> None:
    basis = pd.Series([0.25, 0.5, 0.9])
    score = map_score(basis, "rolling_percentile", neutral=0.5, direction="positive", scale=99.0, zscore_clip=3.0)
    assert score.tolist() == pytest.approx([-0.5, 0.0, 0.8])


def test_percentile_mapping_uses_declared_neutral_anchor() -> None:
    score = map_score(pd.Series([0.6]), "rolling_percentile", neutral=0.0, direction="positive", scale=1.0, zscore_clip=3.0)
    assert score.iloc[0] == pytest.approx(1.0)  # clipped at +1


def test_zscore_mapping_clips_to_configured_band() -> None:
    basis = pd.Series([1.5, -5.0, 2.9])
    score = map_score(basis, "robust_zscore", neutral=0.0, direction="positive", scale=1.0, zscore_clip=3.0)
    assert score.tolist() == pytest.approx([0.5, -1.0, 2.9 / 3.0])


def test_gap_mapping_uses_declared_scale_and_clips() -> None:
    basis = pd.Series([-8.0, 2.0])
    score = map_score(basis, "neutral_gap", neutral=0.0, direction="positive", scale=4.0, zscore_clip=3.0)
    assert score.tolist() == pytest.approx([-1.0, 0.5])


def test_negative_direction_flips_score_sign() -> None:
    basis = pd.Series([0.9, 0.2])
    score = map_score(basis, "rolling_percentile", neutral=0.5, direction="negative", scale=1.0, zscore_clip=3.0)
    assert score.tolist() == pytest.approx([-0.8, 0.6])


def test_unknown_scale_rejected() -> None:
    from macro_compass.signals.engine import _basis_scale

    with pytest.raises(ValueError, match="scale"):
        _basis_scale({"score_mapping": {"scales": {"default": {"level": 0.0}}}}, "X", "level")


# --- single input signals ------------------------------------------------------


def test_output_contract_columns_exact() -> None:
    spec = _spec(momentum={"type": "delta", "periods": 1})
    result = compute_signal(spec, {"A": _series([1.0, 2.0, 3.0])}, MACRO_CONFIG, TODAY)
    assert list(result.frame.columns) == CONTRACT_COLUMNS


def test_score_is_weighted_level_plus_momentum() -> None:
    spec = _spec(
        transforms=[{"type": "level"}],
        momentum={"type": "delta", "periods": 1},
        level_weight=0.75,
        momentum_weight=0.25,
    )
    values = _series([0.0, 1.0, 4.0])  # level basis; delta = 3 on last row
    result = compute_signal(spec, {"A": values}, MACRO_CONFIG, TODAY)
    last = result.frame.iloc[-1]
    # level 4.0 / scale 2.0 -> 1.0 (clipped); momentum 3.0 / 1.0 -> 1.0
    assert last["level_score"] == pytest.approx(1.0)
    assert last["momentum_score"] == pytest.approx(1.0)
    assert last["score"] == pytest.approx(0.75 * 1.0 + 0.25 * 1.0)


def test_score_renormalises_when_momentum_warmup() -> None:
    spec = _spec(momentum={"type": "delta", "periods": 1})
    values = _series([1.0, 2.0])
    result = compute_signal(spec, {"A": values}, MACRO_CONFIG, TODAY)
    first = result.frame.iloc[0]
    assert pd.isna(first["momentum_score"])
    # only the level component is present: score == level_score, no silent zero
    assert first["score"] == pytest.approx(first["level_score"])


def test_freshness_counts_days_to_today() -> None:
    spec = _spec()
    result = compute_signal(spec, {"A": _series([1.0, 2.0, 3.0])}, MACRO_CONFIG, TODAY)
    assert result.frame["freshness"].tolist() == [240, 239, 238]


def test_missing_all_inputs_is_missing_input_with_empty_frame() -> None:
    spec = _spec()
    result = compute_signal(spec, {}, MACRO_CONFIG, TODAY)
    assert result.status == MISSING_INPUT
    assert result.frame.empty
    assert list(result.frame.columns) == CONTRACT_COLUMNS


def test_per_signal_scale_override_from_config() -> None:
    spec = _spec(signal_id="S1", transforms=[{"type": "neutral_gap", "reference": 0}])
    values = _series([4.0])
    result = compute_signal(spec, {"A": values}, MACRO_CONFIG, TODAY)
    assert result.frame.iloc[-1]["level_score"] == pytest.approx(1.0)  # 4.0 / 4.0


# --- composite combinations ----------------------------------------------------


def test_average_composite_equal_weight_and_breakdown_sums_to_score() -> None:
    spec = _spec(
        inputs=[("A", "component"), ("B", "component")],
        transforms=[{"type": "level"}],
        momentum={"type": "delta", "periods": 1},
    )
    a = _series([2.0, 4.0])
    b = _series([0.0, 2.0])
    result = compute_signal(spec, {"A": a, "B": b}, MACRO_CONFIG, TODAY)
    last = result.frame.iloc[-1]
    assert result.combination == "average"
    assert result.status == READY
    assert last["coverage"] == pytest.approx(1.0)
    # level scores: A -> 4/2=1.0 (clip), B -> 2/2=1.0; momentum: +1 each -> 1.0
    assert last["level_score"] == pytest.approx(1.0)
    assert last["score"] == pytest.approx(1.0)
    contributions = result.contributions.iloc[-1]
    assert contributions.sum() == pytest.approx(last["score"])
    assert contributions["A"] == pytest.approx(contributions["B"])  # equal weight


def test_average_composite_partial_coverage_with_null_score_rows() -> None:
    spec = _spec(
        inputs=[("A", "component"), ("B", "component")],
        transforms=[{"type": "level"}],
    )
    a = _series([2.0, 4.0, 6.0])
    b = _series([1.0])  # B stops early: later dates have half coverage
    result = compute_signal(spec, {"A": a, "B": b}, MACRO_CONFIG, TODAY)
    # registry availability semantics are series-level: both series exist, so
    # the signal is READY even though late dates have only one input
    assert result.status == READY
    tail = result.frame.iloc[-1]
    assert tail["coverage"] == pytest.approx(0.5)
    # single available input still computes (documented degraded mode);
    # 6.0 / scale 2.0 = 3.0 -> clipped to +1
    assert tail["score"] == pytest.approx(1.0)
    assert result.contributions.iloc[-1]["B"] != result.contributions.iloc[-1]["B"]  # NaN


def test_difference_combination_subtracts_in_declared_order() -> None:
    spec = _spec(
        inputs=[("A", "spread_leg"), ("B", "spread_leg")],
        transforms=[{"type": "level"}],
        momentum={"type": "delta", "periods": 1},
        combination="difference",
    )
    a = _series([5.0, 7.0])
    b = _series([3.0, 3.0])
    result = compute_signal(spec, {"A": a, "B": b}, MACRO_CONFIG, TODAY)
    last = result.frame.iloc[-1]
    assert result.combination == "difference"
    assert last["level"] == pytest.approx(4.0)   # 7 - 3
    assert last["level_score"] == pytest.approx(1.0)  # 4/2 clipped
    # signed shares of the raw composite: 7/10 and -3/10
    shares = result.contributions.iloc[-1]
    assert shares["A"] == pytest.approx(0.7)
    assert shares["B"] == pytest.approx(-0.3)


def test_difference_with_missing_leg_has_null_scores_and_half_coverage() -> None:
    spec = _spec(
        inputs=[("A", "spread_leg"), ("B", "spread_leg")],
        transforms=[{"type": "level"}],
        combination="difference",
    )
    result = compute_signal(spec, {"A": _series([5.0, 7.0])}, MACRO_CONFIG, TODAY)
    assert result.status == PARTIAL
    assert not result.frame.empty
    assert result.frame["score"].isna().all()
    assert result.frame["coverage"].eq(0.5).all()


def test_fallback_uses_preferred_then_fallback_role_order() -> None:
    spec = _spec(
        inputs=[("CORE", "preferred"), ("HEAD", "fallback")],
        transforms=[{"type": "level"}],
        neutral=0.0,
    )
    both = compute_signal(
        spec, {"CORE": _series([1.0]), "HEAD": _series([99.0])}, MACRO_CONFIG, TODAY
    )
    assert both.combination == "fallback"
    assert both.status == READY
    assert both.frame.iloc[-1]["level"] == pytest.approx(1.0)  # preferred wins

    only_fallback = compute_signal(spec, {"HEAD": _series([99.0])}, MACRO_CONFIG, TODAY)
    assert only_fallback.status == PARTIAL
    assert only_fallback.frame.iloc[-1]["level"] == pytest.approx(99.0)
    assert only_fallback.frame.iloc[-1]["coverage"] == pytest.approx(0.5)


def test_provenance_is_synthetic_real_or_mixed() -> None:
    spec = _spec(inputs=[("A", "component"), ("B", "component")], transforms=[{"type": "level"}])
    real_only = compute_signal(
        spec, {"A": _series([1.0]), "B": _series([2.0])}, MACRO_CONFIG, TODAY,
        input_provenance={"A": "real", "B": "real"},
    )
    assert real_only.provenance == "real"
    mixed = compute_signal(
        spec, {"A": _series([1.0]), "B": _series([2.0])}, MACRO_CONFIG, TODAY,
        input_provenance={"A": "synthetic", "B": "real"},
    )
    assert mixed.provenance == "mixed"


# --- full registry run ----------------------------------------------------------


def test_compute_core_signals_covers_all_15_core() -> None:
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    computations = compute_core_signals(registry, {}, MACRO_CONFIG, TODAY)
    assert set(computations) == set(registry.core)
    assert len(computations) == 15
    for comp in computations.values():
        assert list(comp.frame.columns) == CONTRACT_COLUMNS
        assert comp.status == MISSING_INPUT
    # market/structural are never computed by the V1.5B engine (V1.6 scope)
    assert not ({"M1", "S1"} & set(computations))
