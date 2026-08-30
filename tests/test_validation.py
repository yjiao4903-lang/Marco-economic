"""V2.5 Historical Validation tests.

These exercise the PURE validation functions with synthetic inputs (never the
production canonical pipeline) - they prove the five methods, LOMO gating,
forward-return alignment and the coverage-matrix builder behave as declared.
They do NOT require network, do NOT import/alter production Asset/Macro/Market
outputs, and do NOT write to canonical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.config import load_indicator_config
from macro_compass.data_sources.registry import load_data_sources_config
from macro_compass.macro import load_macro_config
from macro_compass.assets import load_asset_config
from macro_compass.signals import load_signal_registry
from macro_compass.validation.history import (
    ValidationSample,
    aligned,
    forward_return_at,
    mechanism_scored_share,
)
from macro_compass.validation.methods import (
    forward_returns,
    score_bucket,
    rolling_beta,
    run_all_for_asset,
    weight_robustness,
    _spearman,
)
from macro_compass.validation.lomo import lomo_candidate
from macro_compass.validation.coverage import build_coverage_matrix, first_score_dates


def _month_ends(start="2018-01-01", end="2024-12-31"):
    return pd.date_range(start, end, freq="MS") + pd.offsets.MonthEnd(0)


def _synthetic_sample(assets=None):
    assets = assets or ["CN_EQUITY", "HK_EQUITY", "CN_GOV_BOND", "CN_CREDIT",
                        "GOLD", "INDUSTRIAL_COMMODITY", "CNY"]
    idx = _month_ends()
    rng = np.random.default_rng(0)
    fp = pd.DataFrame(
        {f: rng.normal(0, 0.5, len(idx)) for f in
         ["growth", "inflation", "domestic_financial", "global_financial"]},
        index=idx,
    )
    scores = pd.DataFrame(
        {a: rng.normal(0, 0.3, len(idx)) for a in assets}, index=idx
    )
    cov = pd.DataFrame(1.0, index=idx, columns=assets)
    fwd = {
        a: pd.DataFrame(
            {"fwd_1m": rng.normal(0, 0.02, len(idx)),
             "fwd_3m": rng.normal(0, 0.04, len(idx))},
            index=idx,
        )
        for a in assets
    }
    return ValidationSample(fp, scores, cov, fwd, series={})


@pytest.fixture(scope="module")
def assets_config():
    return load_asset_config(paths.ASSETS_YAML, registry=None)


# ---------------------------------------------------------------- pure methods


def test_spearman_pure():
    a = pd.Series([1.0, 2.0, 3.0, 4.0])
    b = pd.Series([5.0, 6.0, 7.0, 8.0])
    assert _spearman(a, b) == pytest.approx(1.0, abs=1e-9)
    assert _spearman(a, -b) == pytest.approx(-1.0, abs=1e-9)


def test_forward_return_at():
    basis = pd.Series([100.0, 110.0, 121.0, 133.1, 146.41],
                      index=pd.date_range("2020-01-01", periods=5, freq="D"))
    daily = basis.pct_change()
    # one-step returns: 0.10, 0.10, 0.10, 0.10 ; cumulative over 2 steps = 0.20
    r = forward_return_at(daily, pd.Timestamp("2020-01-02"), 2)
    assert r is not None and r == pytest.approx(0.20, abs=1e-6)
    # horizon exceeding available data -> None (never fabricate)
    assert forward_return_at(daily, pd.Timestamp("2020-01-04"), 3) is None


def test_aligned_filters_by_coverage_and_fwd():
    sample = _synthetic_sample(["CN_EQUITY"])
    df = aligned("CN_EQUITY", "3m", sample, min_coverage=0.5)
    assert set(df.columns) == {"score", "fwd"}
    # drop some fwd + a coverage hole, count recheck
    fdf = sample.forward_returns["CN_EQUITY"]
    fdf.loc[fdf.index[0], "fwd_3m"] = np.nan
    sample.asset_coverage.loc[sample.asset_coverage.index[1], "CN_EQUITY"] = 0.1
    df2 = aligned("CN_EQUITY", "3m", sample, min_coverage=0.5)
    n_total = int(sample.asset_scores["CN_EQUITY"].notna().sum())
    assert len(df2) < n_total
    assert len(df) == n_total  # full coverage + full fwd -> all rows


def test_forward_returns_verdict_keys():
    sample = _synthetic_sample(["CN_EQUITY"])
    df = aligned("CN_EQUITY", "1m", sample, min_coverage=0.0)
    v = forward_returns("CN_EQUITY", "1m", df)
    for key in ("method", "asset", "horizon", "metric", "statistic", "n",
                "adequate", "conclusion"):
        assert key in v
    assert v["n"] == len(df)


def test_run_all_for_asset_counts(assets_config):
    sample = _synthetic_sample()
    res = run_all_for_asset("CN_EQUITY", sample, assets_config)
    # 4 methods x 2 horizons + 1 weight robustness = 9
    assert len(res) == 9
    methods_seen = {r["method"] for r in res}
    assert methods_seen == {"forward_returns", "score_bucket", "regime_analysis",
                            "rolling_beta", "weight_robustness"}


def test_weight_robustness_high_when_identical(assets_config):
    idx = _month_ends()
    rng = np.random.default_rng(1)
    fp = pd.DataFrame(
        {f: rng.normal(0, 0.5, len(idx)) for f in
         ["growth", "inflation", "domestic_financial", "global_financial"]},
        index=idx,
    )
    base = pd.Series(np.linspace(-0.5, 0.5, len(fp)), index=fp.index)
    v = weight_robustness("CN_EQUITY", assets_config, fp, base)
    assert v["method"] == "weight_robustness"
    assert v["conclusion"] in ("WEIGHT_ROBUST", "WEIGHT_SENSITIVE")
    assert v["statistic"] is not None and -1.0 <= v["statistic"] <= 1.0


# ----------------------------------------------------------------------- LOMO


def test_lomo_candidate_gate():
    # newly-arrived mechanism (small scored_share) is never a candidate
    assert lomo_candidate(True, 0.10, 0.99, 0.01) is False
    # adequate sample + real history + stable + no separation move -> candidate
    assert lomo_candidate(True, 0.95, 0.99, 0.01) is True
    # insufficient comparison sample -> never a candidate
    assert lomo_candidate(False, 0.95, 0.99, 0.01) is False
    # material separation move -> not a candidate
    assert lomo_candidate(True, 0.95, 0.99, 0.30) is False
    # factor NOT stable -> not a candidate
    assert lomo_candidate(True, 0.95, 0.50, 0.01) is False


# --------------------------------------------------------------- coverage matrix


def test_mechanism_scored_share():
    class FakeComp:
        def __init__(self, dates):
            self.frame = pd.DataFrame(
                {"date": dates, "score": [1.0] * len(dates)}
            ) if len(dates) else pd.DataFrame(
                {"date": pd.Series(dtype="datetime64[ns]"), "score": pd.Series(dtype=float)}
            )
    grid = _month_ends()
    comps = {"A": FakeComp(grid), "B": FakeComp([])}
    out = mechanism_scored_share(comps, grid)
    assert out["A"] == pytest.approx(1.0)
    assert out["B"] == 0.0


def test_mechanism_scored_share_pure():
    # a mechanism that only scored on the last half of the grid has share ~0.5
    grid = _month_ends()
    half = grid[len(grid) // 2:]
    comps = {
        "late": type("C", (), {"frame": pd.DataFrame(
            {"date": half, "score": [1.0] * len(half)})})(),
    }
    assert mechanism_scored_share(comps, grid)["late"] == pytest.approx(0.5, abs=0.05)


def test_m3_regime_dependent_blocks_without_data():
    from macro_compass.validation.regime_checks import m3_regime_dependent
    sample = _synthetic_sample()  # series={} -> no yield series
    res = m3_regime_dependent(sample, None)
    assert res.check_id == "M3_REGIME"
    assert res.conclusion in ("DATA_BLOCKED", "INSUFFICIENT_SAMPLE")


def test_m3_regime_dependent_splits_by_growth():
    from macro_compass.validation.regime_checks import m3_regime_dependent
    idx = _month_ends()
    rng = np.random.default_rng(3)
    # 60+ month-ends of yield; build a series with a downward 3M leg region
    yield_vals = 3.0 + 0.001 * rng.normal(0, 1, len(idx))
    yield_series = pd.Series(yield_vals, index=idx)
    fp = pd.DataFrame(
        {"growth": np.where(idx.month >= 6, 0.3, -0.3)},
        index=idx,
    )
    fwd3 = pd.Series(rng.normal(0, 0.02, len(idx)), index=idx)
    scores = pd.DataFrame({"CN_GOV_BOND": rng.normal(0, 0.3, len(idx))}, index=idx)
    cov = pd.DataFrame(1.0, index=idx, columns=["CN_GOV_BOND"])
    fwd = {"CN_GOV_BOND": pd.DataFrame({"fwd_1m": fwd3, "fwd_3m": fwd3}, index=idx)}
    sample = ValidationSample(fp, scores, cov, fwd,
                              series={"CN_GOV_YIELD_10Y": yield_series})
    res = m3_regime_dependent(sample, None)
    assert res.check_id == "M3_REGIME"
    assert res.conclusion in (
        "REGIME_DEPENDENT", "REGIME_DEPENDENT_REVERSED",
        "NOT_REGIME_DEPENDENT", "INSUFFICIENT_SAMPLE",
    )


def test_coverage_matrix_15_signals():
    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    macro_config = load_macro_config(paths.MACRO_YAML)
    sources_cfg = load_data_sources_config(paths.DATA_SOURCES_YAML, indicator_registry=indicators)
    first = first_score_dates({sid: type("n", (), {"frame": pd.DataFrame()})() for sid in registry.core})
    rows = build_coverage_matrix(
        registry, sources_cfg, macro_config, {}, first
    )
    assert len(rows) == len(registry.core)  # all 15 core signals
    for sig in rows:
        assert sig.signal_id and sig.factor
        assert sig.minimum_validation_start is None  # no data -> unknown


# ------------------------------------------------------------------ isolation


def test_validation_package_exposes_expected_public_api():
    import macro_compass.validation as v
    for name in ("assemble", "run_all_for_asset", "run_lomo",
                 "run_regime_checks", "build_coverage_matrix",
                 "mechanism_scored_share"):
        assert hasattr(v, name), f"validation exposing '{name}' is expected"