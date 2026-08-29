"""V1.5C Macro Factor Engine tests: aggregation, breadth, confidence, regime.

Deterministic: factor/regime logic is exercised on constructed signal
outputs and FactorResult dataclasses - no network, no canonical files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.macro import (
    MacroConfigError,
    classify_provenance,
    classify_regime,
    compute_factor,
    load_macro_config,
)
from macro_compass.macro.factors import FactorResult, SignalContribution
from macro_compass.signals.engine import SignalComputation, compute_signal
from macro_compass.signals.registry import SignalSpec

TODAY = pd.Timestamp("2026-08-29")

MACRO_CONFIG = {
    "score_mapping": {
        "zscore_clip": 3.0,
        "scales": {"default": {"level": 2.0, "momentum": 1.0}},
    },
    "factor_weights": {
        "growth": {"G1": 1.0, "G2": 1.0},
        "inflation": {"I1": 1.0},
        "domestic_financial": {},
        "global_financial": {},
    },
    "confidence": {
        "default_max_staleness_days": 90,
        "min_confidence": 0.5,
        "source_quality": {"OECD": 1.0, "WIND": 0.6},
        "default_source_quality": 0.5,
    },
    "regime": {
        "score_threshold": 0.15,
        "min_breadth": 2,
        "breadth_min_score": 0.10,
    },
}


def _series(values, start: str = "2026-01-01") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, dtype=float, index=index)


def _spec(signal_id: str, inputs: list[str]) -> SignalSpec:
    return SignalSpec(
        signal_id=signal_id,
        name=signal_id,
        layer="core",
        factor="growth",
        mechanism="test mechanism",
        inputs=[{"series_id": sid, "role": "level"} for sid in inputs],
        transforms=[{"type": "level"}],
        direction="positive",
        neutral=0.0,
        level_weight=1.0,
        momentum_weight=0.0,
    )


def _computation(
    signal_id: str,
    inputs: list[str],
    values: dict[str, list[float]],
    provenance: dict[str, str] | None = None,
    sources: dict[str, str] | None = None,
) -> SignalComputation:
    series = {sid: _series(vals) for sid, vals in values.items()}
    return compute_signal(
        _spec(signal_id, inputs),
        series,
        MACRO_CONFIG,
        TODAY,
        input_provenance=provenance,
        input_sources=sources,
    )


# --- factor aggregation --------------------------------------------------------


def test_factor_score_is_configured_weight_mean_of_signal_scores() -> None:
    g1 = _computation("G1", ["CLI"], {"CLI": [1.0]})  # 1/2 -> 0.5
    g2 = _computation("G2", ["PMI"], {"PMI": [-1.0]})  # -1/2 -> -0.5
    result = compute_factor(
        "growth", ["G1", "G2"], {"G1": g1, "G2": g2}, MACRO_CONFIG, {}, TODAY
    )
    assert result.score == pytest.approx(0.0)
    assert result.signals["G1"].contribution == pytest.approx(0.25)
    assert result.signals["G2"].contribution == pytest.approx(-0.25)


def test_factor_weights_from_config_not_equal() -> None:
    config = dict(MACRO_CONFIG)
    config["factor_weights"] = {"growth": {"G1": 3.0, "G2": 1.0}}
    g1 = _computation("G1", ["CLI"], {"CLI": [1.0]})
    g2 = _computation("G2", ["PMI"], {"PMI": [-1.0]})
    result = compute_factor(
        "growth", ["G1", "G2"], {"G1": g1, "G2": g2}, config, {}, TODAY
    )
    assert result.score == pytest.approx((3 * 0.5 + 1 * -0.5) / 4.0)


def test_unscored_signals_excluded_never_zero_filled() -> None:
    g1 = _computation("G1", ["CLI"], {"CLI": [1.0]})
    missing = _computation("G2", ["PMI"], {})  # no data -> MISSING_INPUT
    result = compute_factor(
        "growth", ["G1", "G2"], {"G1": g1, "G2": missing}, MACRO_CONFIG, {}, TODAY
    )
    assert result.score == pytest.approx(0.5)  # only G1 contributes
    assert result.signals["G2"].score is None
    assert result.signals["G2"].contribution is None


def test_contributions_sum_to_factor_score() -> None:
    outputs = {
        signal_id: _computation(signal_id, [sid], {sid: value})
        for signal_id, sid, value in
        (("G1", "CLI", [2.0]), ("G2", "PMI", [-0.4]), ("G4", "PROP", [1.2]))
    }
    result = compute_factor(
        "growth", ["G1", "G2", "G4"], outputs, MACRO_CONFIG, {}, TODAY
    )
    total = sum(c.contribution for c in result.signals.values())
    assert total == pytest.approx(result.score)


def test_breadth_counts_mechanisms_not_series() -> None:
    # three signals, all real (one mechanism each): two agree, one opposes
    outputs = {
        signal_id: _computation(signal_id, [sid], {sid: value})
        for signal_id, sid, value in
        (("G1", "CLI", [1.0]), ("G2", "PMI", [0.8]), ("G4", "PROP", [-1.0]))
    }
    result = compute_factor(
        "growth", ["G1", "G2", "G4"], outputs, MACRO_CONFIG, {}, TODAY
    )
    assert result.breadth == 2
    assert result.breadth_detail == ["G1", "G2"]


def test_breadth_ignores_scores_below_min_score() -> None:
    outputs = {
        signal_id: _computation(signal_id, [sid], {sid: value})
        for signal_id, sid, value in
        (("G1", "CLI", [0.3]), ("G2", "PMI", [0.15]))  # 0.075 < 0.10 min
    }
    result = compute_factor(
        "growth", ["G1", "G2"], outputs, MACRO_CONFIG, {}, TODAY
    )
    assert result.breadth_detail == ["G1"]


def test_confidence_components_coverage_freshness_source() -> None:
    g1 = _computation(
        "G1", ["CLI"], {"CLI": [1.0]},
        sources={"CLI": "OECD"},
    )
    g2 = _computation(
        "G2", ["PMI"], {"PMI": [-1.0]},
        sources={"PMI": "WIND"},
    )
    # G2's data ends 89 days ago? -> series length 1 (2026-01-01) -> stale (>90)
    old = _computation("G4", ["PROP"], {"PROP": [1.0]}, sources={"PROP": "OECD"})
    result = compute_factor(
        "growth", ["G1", "G2", "G4"],
        {"G1": g1, "G2": g2, "G4": old}, MACRO_CONFIG, {}, TODAY,
    )
    assert result.confidence["coverage"] == pytest.approx(1.0)
    # all three inputs end 2026-01-01 = 240 days old -> all stale
    assert result.confidence["freshness"] == pytest.approx(0.0)
    # every contributing signal flagged stale
    assert all(c.stale for c in result.signals.values())
    # source quality = mean of OECD(1.0), WIND(0.6), OECD(1.0)
    assert result.confidence["source_quality"] == pytest.approx((1.0 + 0.6 + 1.0) / 3.0)
    assert result.confidence["composite"] == pytest.approx(
        (result.confidence["coverage"] + result.confidence["freshness"]
         + result.confidence["source_quality"]) / 3.0
    )


def test_staleness_budget_from_data_sources_config() -> None:
    today = pd.Timestamp("2026-08-20")
    index = pd.date_range("2026-08-01", periods=1, freq="D")
    values = pd.Series([1.0], index=index)  # 19 days old, budget 95 -> fresh
    g1 = compute_signal(
        _spec("G1", ["CLI"]), {"CLI": values}, MACRO_CONFIG, today,
        input_sources={"CLI": "OECD"},
    )
    result = compute_factor("growth", ["G1"], {"G1": g1}, MACRO_CONFIG, {"CLI": 95}, today)
    assert result.confidence["freshness"] == pytest.approx(1.0)
    assert not result.signals["G1"].stale
    # the same observation breaches a tight budget
    stale = compute_factor("growth", ["G1"], {"G1": g1}, MACRO_CONFIG, {"CLI": 10}, today)
    assert stale.signals["G1"].stale


def test_factor_has_no_path_to_raw_series() -> None:
    # structural check: compute_factor only accepts SignalComputation outputs
    import inspect

    from macro_compass.macro import factors

    signature = inspect.signature(factors.compute_factor)
    assert "signal_outputs" in signature.parameters
    source = inspect.getsource(factors)
    assert "canonical_store" not in source
    assert "read_parquet" not in source


# --- provenance ------------------------------------------------------------------


def test_classify_provenance_by_source_file_markers() -> None:
    result = classify_provenance(
        {
            "A": ["wind_macro_sample.csv"],
            "B": ["oecd_export_2026.csv"],
            "C": ["wind_macro_sample.csv", "manual.xlsx"],
            "D": [""],
        },
        ["wind_macro_sample"],
    )
    assert result == {"A": "synthetic", "B": "real", "C": "mixed", "D": "unknown"}


# --- regime -----------------------------------------------------------------------


def _factor(factor: str, score, breadth: int, confidence: float = 0.9) -> FactorResult:
    return FactorResult(
        factor=factor,
        score=score,
        breadth=breadth,
        breadth_detail=[],
        confidence={
            "coverage": confidence, "freshness": confidence,
            "source_quality": confidence, "composite": confidence,
        },
        signals={},
        asof=None,
    )


def test_regime_four_quadrants() -> None:
    cases = {
        ("up", "up"): "Reflation",
        ("up", "down"): "Goldilocks",
        ("down", "up"): "Stagflation",
        ("down", "down"): "Deflationary Slowdown",
    }
    scores = {"up": 0.5, "down": -0.5}
    for (g, i), expected in cases.items():
        factors = {"growth": _factor("growth", scores[g], 2),
                   "inflation": _factor("inflation", scores[i], 2)}
        assert classify_regime(factors, MACRO_CONFIG).regime == expected


def test_regime_no_signal_when_factor_not_computable() -> None:
    factors = {"growth": _factor("growth", None, 0),
               "inflation": _factor("inflation", 0.5, 2)}
    result = classify_regime(factors, MACRO_CONFIG)
    assert result.regime == "NO_SIGNAL"
    assert result.growth_state == "none"


def test_regime_low_confidence_overrides_quadrant() -> None:
    factors = {"growth": _factor("growth", 0.5, 2, confidence=0.4),
               "inflation": _factor("inflation", 0.5, 2, confidence=0.9)}
    assert classify_regime(factors, MACRO_CONFIG).regime == "LOW_CONFIDENCE"


def test_regime_transition_when_axis_inside_threshold() -> None:
    factors = {"growth": _factor("growth", 0.10, 2),   # |0.10| <= 0.15
               "inflation": _factor("inflation", -0.5, 2)}
    result = classify_regime(factors, MACRO_CONFIG)
    assert result.regime == "TRANSITION"
    assert result.growth_state == "neutral"


def test_regime_mixed_when_breadth_too_thin() -> None:
    factors = {"growth": _factor("growth", 0.5, 1),
               "inflation": _factor("inflation", 0.5, 2)}
    result = classify_regime(factors, MACRO_CONFIG)
    assert result.regime == "MIXED"
    assert any("breadth" in line for line in result.rationale)


# --- config loader ------------------------------------------------------------------


def test_load_macro_config_real_file() -> None:
    config = load_macro_config(paths.MACRO_YAML)
    assert config["regime"]["min_breadth"] >= 1
    assert "growth" in config["factor_weights"]
    assert config["score_mapping"]["zscore_clip"] > 0
    assert config["synthetic_markers"]


def test_load_macro_config_missing_section_rejected(tmp_path) -> None:
    bad = tmp_path / "macro.yaml"
    bad.write_text("score_mapping:\n  zscore_clip: 3.0\n", encoding="utf-8")
    with pytest.raises(MacroConfigError, match="factor_weights"):
        load_macro_config(bad)


def test_load_macro_config_missing_file(tmp_path) -> None:
    with pytest.raises(MacroConfigError, match="not found"):
        load_macro_config(tmp_path / "nope.yaml")
