"""V2.6 Structural Risk tests.

Offline and deterministic. Covers:

* the signals.yaml S1/S2/S3 declarations (inputs + transform chains, no
  scoring config) and the structural.yaml declared priors;
* the pure structural engine: READY / WARMUP / MISSING_INPUT statuses, the
  percentile/trend read, the diagnostic labels, and the stale flag that
  drives the report's NO_SIGNAL output;
* isolation: structural risk NEVER enters the short-term Asset Score
  (source-level grep + behavioral check) and the core engine never computes
  structural signals;
* the resolve_signal_status structural branch.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from macro_compass.config import load_indicator_config
from macro_compass.signals import (
    DECLARED,
    MISSING_INPUT,
    READY,
    assess_availability,
    load_signal_registry,
    resolve_signal_status,
)
from macro_compass.signals.engine import WARMUP

STRUCTURAL_IDS = {"S1", "S2", "S3"}


@pytest.fixture(scope="module")
def registry():
    from macro_compass import paths

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    return load_signal_registry(paths.SIGNALS_YAML, indicators)


@pytest.fixture(scope="module")
def structural_config():
    from macro_compass import paths
    from macro_compass.structural import load_structural_config

    return load_structural_config(paths.STRUCTURAL_YAML)


# ---------------------------------------------------------------------------
# ---- 1) declarations ------------------------------------------------------
# ---------------------------------------------------------------------------


def test_structural_declarations_locked(registry) -> None:
    """S1/S2 declare their BIS inputs + level/delta(4) chains; S3 has no
    inputs until the B-package proxy pool lands."""
    s1 = registry.signals["S1"]
    assert [i.series_id for i in s1.inputs] == ["CN_CREDIT_TO_GDP_GAP"]
    assert [step.type for step in s1.transforms] == ["level"]
    assert s1.momentum_transform.type == "delta"
    assert s1.momentum_transform.model_extra["periods"] == 4

    s2 = registry.signals["S2"]
    assert [i.series_id for i in s2.inputs] == ["CN_DSR"]
    assert [step.type for step in s2.transforms] == ["level"]
    assert s2.momentum_transform.type == "delta"
    assert s2.momentum_transform.model_extra["periods"] == 4

    s3 = registry.signals["S3"]
    assert s3.inputs == []


def test_structural_signals_carry_no_scoring_config(registry) -> None:
    """Structural layer has no scoring config (V1.3 placeholder semantics)."""
    for signal_id in STRUCTURAL_IDS:
        spec = registry.signals[signal_id]
        assert spec.layer == "structural"
        assert spec.level_weight is None
        assert spec.momentum_weight is None
        assert spec.direction is None


def test_structural_yaml_declared_priors(structural_config) -> None:
    assert set(structural_config["signals"]) == STRUCTURAL_IDS
    assert structural_config["signals"]["S1"]["direction"] == "negative"
    assert structural_config["signals"]["S1"]["percentile_window"] == 40
    assert structural_config["signals"]["S1"]["trend_quarters"] == 4
    assert structural_config["signals"]["S1"]["thresholds"]["elevated"] == 10.0
    assert structural_config["signals"]["S2"]["thresholds"]["elevated_percentile"] == 0.80


def test_structural_yaml_rejects_implicit_direction(tmp_path) -> None:
    from macro_compass.structural import StructuralConfigError, load_structural_config

    path = tmp_path / "structural.yaml"
    path.write_text(
        "signals:\n  S1:\n    percentile_window: 40\n    trend_quarters: 4\n"
        "    thresholds: {elevated: 10.0}\n",
        encoding="utf-8",
    )
    with pytest.raises(StructuralConfigError, match="direction"):
        load_structural_config(path)


# ---------------------------------------------------------------------------
# ---- 2) pure engine -------------------------------------------------------
# ---------------------------------------------------------------------------


def _quarterly(n: int, values, start="2015-03-31") -> pd.Series:
    idx = pd.date_range(start, periods=n, freq="QE")
    return pd.Series(list(values), index=idx)


def _compute(registry, structural_config, series, today, staleness=None):
    from macro_compass.structural import compute_structural_readings

    return compute_structural_readings(
        registry, structural_config, series, today, staleness=staleness
    )


def test_s3_missing_input_no_synthetic(registry, structural_config) -> None:
    """S3 is declared without inputs until B-package -> MISSING_INPUT (the
    report shows NO_SIGNAL). No synthetic data is ever produced."""
    today = pd.Timestamp("2026-08-30")
    readings = _compute(registry, structural_config, {}, today)
    s3 = readings["S3"]
    assert s3.status == MISSING_INPUT
    assert s3.level is None and s3.percentile is None
    assert "B 包" in s3.message


def test_s1_missing_input_when_no_data(registry, structural_config) -> None:
    today = pd.Timestamp("2026-08-30")
    readings = _compute(registry, structural_config, {}, today)
    s1 = readings["S1"]
    assert s1.status == MISSING_INPUT
    assert s1.level is None


def test_s1_ready_read_and_diagnostic_below_trend(registry, structural_config) -> None:
    """A gap that is negative (below its HP trend) reads BELOW_TREND and READY."""
    today = pd.Timestamp("2026-08-30")
    n = 50  # >= percentile_window 40
    values = [0.0 - i * 0.2 for i in range(n)]  # 0 down to -9.8
    series = {"CN_CREDIT_TO_GDP_GAP": _quarterly(n, values)}
    r = _compute(registry, structural_config, series, today)["S1"]
    assert r.status == READY
    assert r.level < 0
    assert r.history_length == n
    assert r.diagnostic == "BELOW_TREND"
    assert r.percentile is not None and 0.0 <= r.percentile <= 1.0
    assert r.trend is not None


def test_s1_diagnostic_elevated_and_above_trend(registry, structural_config) -> None:
    today = pd.Timestamp("2026-08-30")
    n = 45
    # gap stuck around +12 (above the BIS red-zone prior 10) -> ELEVATED
    series = {"CN_CREDIT_TO_GDP_GAP": _quarterly(n, [12.0 + 0.01 * i for i in range(n)])}
    assert _compute(registry, structural_config, series, today)["S1"].diagnostic == "ELEVATED"
    # gap around +5 (positive but below 10) -> ABOVE_TREND
    series = {"CN_CREDIT_TO_GDP_GAP": _quarterly(n, [5.0 + 0.01 * i for i in range(n)])}
    assert _compute(registry, structural_config, series, today)["S1"].diagnostic == "ABOVE_TREND"


def test_s2_diagnostic_percentile_based(registry, structural_config) -> None:
    today = pd.Timestamp("2026-08-30")
    n = 50
    # strictly rising DSR -> latest is the window max -> percentile ~1.0 -> ELEVATED
    series = {"CN_DSR": _quarterly(n, [10.0 + 0.2 * i for i in range(n)])}
    r = _compute(registry, structural_config, series, today)["S2"]
    assert r.status == READY
    assert r.percentile >= 0.9
    assert r.diagnostic == "ELEVATED"
    # strictly falling DSR -> latest is the window min -> BENIGN
    series = {"CN_DSR": _quarterly(n, [20.0 - 0.2 * i for i in range(n)])}
    r = _compute(registry, structural_config, series, today)["S2"]
    assert r.diagnostic == "BENIGN"
    # latest lands near the median of its trailing window -> MODERATE
    series = {"CN_DSR": _quarterly(n, [10.0] * 30 + [20.0] * 19 + [15.0])}
    r = _compute(registry, structural_config, series, today)["S2"]
    assert 0.5 <= r.percentile < 0.8
    assert r.diagnostic == "MODERATE"


def test_warmup_when_history_below_window(registry, structural_config) -> None:
    today = pd.Timestamp("2026-08-30")
    series = {"CN_CREDIT_TO_GDP_GAP": _quarterly(20, [1.0 + i * 0.1 for i in range(20)])}
    r = _compute(registry, structural_config, series, today)["S1"]
    assert r.status == WARMUP
    assert r.diagnostic is None


def test_stale_flag_drives_no_signal(registry, structural_config) -> None:
    """A READY reading whose latest quarterly observation is far in the past
    is flagged stale -> the report emits NO_SIGNAL (never a silent value)."""
    today = pd.Timestamp("2026-08-30")
    # latest quarter-end 2024-12-31 (~600 days before today) exceeds budget 260
    series = {"CN_DSR": _quarterly(48, [12.0 + 0.1 * i for i in range(48)], start="2013-03-31")}
    r = _compute(
        registry, structural_config, series, today, staleness={"CN_DSR": 260}
    )["S2"]
    assert r.status == READY
    assert r.stale is True
    assert r.freshness_days > 260


# ---------------------------------------------------------------------------
# ---- 3) status resolution + isolation -------------------------------------
# ---------------------------------------------------------------------------


def test_resolve_signal_status_structural_branch(registry, structural_config) -> None:
    """resolve_signal_status takes the structural engine's status (V1.5D
    semantics) when supplied; without it the registry placeholder semantics
    (DECLARED / MISSING_INPUT) are kept."""
    from macro_compass.structural import compute_structural_readings

    today = pd.Timestamp("2026-08-30")

    n = 50
    series = {"CN_CREDIT_TO_GDP_GAP": _quarterly(n, [-5.0 + 0.1 * i for i in range(n)])}
    readings = compute_structural_readings(registry, structural_config, series, today)
    availability = assess_availability(registry, set(series))
    # with the structural engine: S1 takes the engine READY
    resolved = resolve_signal_status(
        registry, availability, {}, None, structural_computations=readings
    )
    assert resolved["S1"] == READY
    assert resolved["S2"] == MISSING_INPUT  # no DSR data -> engine MISSING_INPUT
    assert resolved["S3"] == MISSING_INPUT  # no inputs -> NO_SIGNAL material

    # without the structural engine: S1 (inputs + data) is DECLARED per the
    # registry's non-core placeholder semantics; S3 (no inputs) is DECLARED
    resolved_no_engine = resolve_signal_status(registry, availability, {})
    assert resolved_no_engine["S1"] == DECLARED
    assert resolved_no_engine["S3"] == DECLARED


def test_structural_signals_not_in_core_engine(registry) -> None:
    """The V1.5B core engine only computes layer=core signals; S1-S3 never
    appear in its output."""
    from macro_compass import paths
    from macro_compass.macro import load_macro_config
    from macro_compass.signals.engine import compute_core_signals

    macro_config = load_macro_config(paths.MACRO_YAML)
    today = pd.Timestamp("2026-08-30")
    n = 50
    series = {
        "CN_CREDIT_TO_GDP_GAP": _quarterly(n, [-5.0] * n),
        "CN_DSR": _quarterly(n, [15.0] * n),
    }
    computations = compute_core_signals(registry, series, macro_config, today)
    assert not (STRUCTURAL_IDS & set(computations))


def test_asset_layer_never_imports_structural() -> None:
    """Source-level isolation: the V2 asset package must not reference the
    structural package - S-signals have no path into any Asset Score."""
    from macro_compass import paths

    for rel in ("assets/__init__.py", "assets/config.py", "assets/engine.py"):
        source = (paths.SRC_DIR / "macro_compass" / rel).read_text(encoding="utf-8")
        assert "macro_compass.structural" not in source, f"{rel} must not import structural"
        assert "from macro_compass import structural" not in source, (
            f"{rel} must not import structural"
        )


def test_asset_score_identical_with_structural_present(registry) -> None:
    """Behavioral isolation: computing the asset layer never touches
    structural data (the asset engine has no structural input at all)."""
    from macro_compass import paths
    from macro_compass.assets import compute_assets, load_asset_config
    from macro_compass.macro import load_macro_config

    assets_config = load_asset_config(paths.ASSETS_YAML, registry=registry)
    macro_config = load_macro_config(paths.MACRO_YAML)
    today = pd.Timestamp("2026-08-29")

    class _Factor:
        score, signals, confidence, asof = 0.3, {}, {
            "coverage": 1.0, "freshness": 1.0, "source_quality": 1.0, "composite": 1.0,
        }, pd.Timestamp("2026-08-28")

    factor_results = {f: _Factor() for f in ("growth", "inflation",
                                             "domestic_financial", "global_financial")}
    results = compute_assets(assets_config, factor_results, {}, macro_config, {}, today)
    # the four core factor outputs are the ONLY scoring inputs; no S-signal
    # can enter, so every asset is simply scored from those factors
    for asset_id in assets_config["assets"]:
        assert results[asset_id].status == "READY"
        assert "S1" not in results[asset_id].signal_contributions
        assert "S2" not in results[asset_id].signal_contributions
        assert "S3" not in results[asset_id].signal_contributions
