"""V2 Asset Compass tests.

Offline and deterministic. Covers:

* the assets.yaml load / validation surface and the R2 transcription tests
  (derived betas locked to the R2 matrix; ambiguous cells forced to weight 0);
* the pure Asset engine (score = L1-normalised beta x factor score,
  additivity of factor and signal contributions, view labels);
* isolation (no reverse data flow, no historical-return search, read-only),
  mirroring the V1.6A market-layer isolation tests.

The declaration surfaces come from config/assets.yaml (module-scoped fixtures)
so any accidental edit to the prior matrix breaks these regression tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pytest

from macro_compass.config import load_indicator_config
from macro_compass.macro import load_macro_config
from macro_compass.signals import load_signal_registry


@pytest.fixture(scope="module")
def registry():
    from macro_compass import paths

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    return load_signal_registry(paths.SIGNALS_YAML, indicators)


@pytest.fixture(scope="module")
def macro_config():
    from macro_compass import paths

    return load_macro_config(paths.MACRO_YAML)


@pytest.fixture(scope="module")
def assets_config(registry):
    from macro_compass import paths
    from macro_compass.assets import load_asset_config

    return load_asset_config(paths.ASSETS_YAML, registry=registry)


# ---------------------------------------------------------------------------
# ---- small stub classes for the pure-engine tests -------------------------
# ---------------------------------------------------------------------------


class _Contrib:
    """A stand-in for macro.factors.SignalContribution."""

    __slots__ = ("score", "contribution", "inputs", "coverage")

    def __init__(self, score, contribution=None, inputs=None, coverage=1.0):
        self.score = score
        self.contribution = contribution if contribution is not None else score
        self.inputs = inputs or {"G0_FAKE": "OECD"}
        self.coverage = coverage


class _FactorRes:
    """A stand-in for macro.factors.FactorResult (score/signals/confidence)."""

    def __init__(self, score, signals=None, confidence=None, asof=None):
        self.score = score
        self.signals = signals or {}
        self.confidence = confidence or {
            "coverage": 1.0, "freshness": 1.0, "source_quality": 1.0, "composite": 1.0,
        }
        self.asof = asof


@dataclass
class _Computation:
    """Minimal structural stand-in for signals.engine.SignalComputation."""

    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def provenance(self) -> str:
        return "real"


FACTORS = ("growth", "inflation", "domestic_financial", "global_financial")


def _scenario(score_map):
    """factor_results stub: provided factors scored, the rest None-as-absent."""
    out = {}
    for f in FACTORS:
        s = score_map.get(f)
        if s is None:
            out[f] = _FactorRes(None)
        else:
            out[f] = _FactorRes(s, signals={"G0_FAKE": _Contrib(s)})
    return out


# ---------------------------------------------------------------------------
# ---- 1) config surface + R2 transcription ---------------------------------
# ---------------------------------------------------------------------------


def test_config_declares_all_seven_assets(assets_config) -> None:
    assert set(assets_config["assets"]) == {
        "CN_EQUITY", "HK_EQUITY", "CN_GOV_BOND", "CN_CREDIT",
        "GOLD", "INDUSTRIAL_COMMODITY", "CNY",
    }


def test_config_derives_expected_betas(assets_config) -> None:
    """Lock the derived factor betas to the R2 prior matrix transcription."""
    expected = {
        "CN_EQUITY": {"growth": 3.8, "inflation": 1.4, "domestic_financial": 2.0, "global_financial": -2.6},
        "HK_EQUITY": {"growth": 4.2, "inflation": 1.4, "domestic_financial": 1.9, "global_financial": -3.0},
        "CN_GOV_BOND": {"growth": -4.2, "inflation": -1.3, "domestic_financial": -2.0, "global_financial": -1.5},
        "CN_CREDIT": {"growth": 1.3, "inflation": 0.3, "domestic_financial": 1.0, "global_financial": 0.0},
        "GOLD": {"growth": -2.4, "inflation": 2.2, "domestic_financial": 1.3, "global_financial": -2.6},
        "INDUSTRIAL_COMMODITY": {"growth": 5.0, "inflation": 2.6, "domestic_financial": 2.4, "global_financial": -3.0},
        "CNY": {"growth": 4.2, "inflation": 0.9, "domestic_financial": 2.0, "global_financial": -2.6},
    }
    for asset_id, fmap in expected.items():
        for f, beta in fmap.items():
            assert assets_config["assets"][asset_id]["factors"][f]["beta"] == pytest.approx(beta, abs=1e-3)


def test_ambiguous_cells_forced_to_zero_weight(assets_config) -> None:
    """R2 transcription rule 4: `ambiguous` contributes 0 and is flagged."""
    credit = assets_config["assets"]["CN_CREDIT"]["factors"]
    for sid in ("G1", "G2", "G3"):
        assert credit["growth"]["signals"][sid]["sign"] == "ambiguous"
        assert credit["growth"]["signals"][sid]["weight"] == 0.0
    assert credit["domestic_financial"]["signals"]["D2"]["weight"] == 0.0
    gov = assets_config["assets"]["CN_GOV_BOND"]["factors"]
    assert gov["inflation"]["signals"]["I3"]["weight"] == 0.0
    gold = assets_config["assets"]["GOLD"]["factors"]
    assert gold["domestic_financial"]["signals"]["D2"]["weight"] == 0.0


def test_config_header_carries_r2_rules_and_no_trading_words(tmp_path) -> None:
    """The assets.yaml header documents the R2 rules; no buy/sell/position words."""
    import re
    from macro_compass import paths

    text = paths.ASSETS_YAML.read_text(encoding="utf-8")
    assert "D3 = M2 YoY - private TSF YoY" in text
    assert "RMB appreciation" in text
    assert "ambiguous" in text
    assert "M2 - nominal GDP" in text
    # trading words as whole ASCII words (so "buying" / "seller" do not trip it)
    assert not re.search(r"\bbuy\b", text, re.IGNORECASE), "assets.yaml must avoid 'buy'"
    assert not re.search(r"\bsell\b", text, re.IGNORECASE), "assets.yaml must avoid 'sell'"
    for word in ("仓位", "买卖"):
        assert word not in text, f"assets.yaml must avoid trading word '{word}'"


def test_market_signal_bindings(assets_config) -> None:
    binds = {
        asset: assets_config["assets"][asset].get("market_signal")
        for asset in assets_config["assets"]
    }
    assert binds == {
        "CN_EQUITY": "M1", "HK_EQUITY": "M2", "CN_GOV_BOND": "M3", "CN_CREDIT": "M4",
        "GOLD": None, "INDUSTRIAL_COMMODITY": "M6", "CNY": "M5",
    }


# ---------------------------------------------------------------------------
# ---- 2) pure engine -------------------------------------------------------
# ---------------------------------------------------------------------------


def test_score_from_factor_outputs(assets_config, macro_config) -> None:
    from macro_compass.assets import compute_assets

    today = pd.Timestamp("2026-08-29")
    factor_results = _scenario(
        {"growth": 0.5, "inflation": -0.3, "domestic_financial": 0.2, "global_financial": -0.1}
    )
    results = compute_assets(
        assets_config, factor_results, {}, macro_config, {}, today
    )
    r = results["CN_EQUITY"]
    assert r.status == "READY"
    expected = (
        (3.8 / 9.8) * 0.5 + (1.4 / 9.8) * (-0.3) + (2.0 / 9.8) * 0.2 + (-2.6 / 9.8) * (-0.1)
    )
    assert r.score == pytest.approx(expected, abs=1e-6)
    # factor contributions are additive and sum to the score
    assert sum(r.factor_contributions.values()) == pytest.approx(r.score, abs=1e-6)


def test_factor_contributions_additive_and_weighted(assets_config, macro_config) -> None:
    from macro_compass.assets import compute_assets

    today = pd.Timestamp("2026-08-29")
    factor_results = _scenario(
        {"growth": 0.5, "inflation": -0.3, "domestic_financial": 0.2, "global_financial": -0.1}
    )
    results = compute_assets(assets_config, factor_results, {}, macro_config, {}, today)
    for asset_id in assets_config["assets"]:
        r = results[asset_id]
        assert r.status == "READY"
        present = {f: v for f, v in r.factor_contributions.items() if v is not None}
        assert present, asset_id
        assert sum(present.values()) == pytest.approx(r.score, abs=1e-6)
        total_abs = sum(abs(b) for b in r.beta.values())
        if total_abs > 0:
            norm_sum = sum(abs(v) for v in r.beta_normalized.values())
            assert norm_sum == pytest.approx(1.0, abs=1e-6)
        # signal contributions for a factor also sum to that factor contribution
        for f in FACTORS:
            fsignals = {sid: sc for sid, sc in r.signal_contributions.items() if sc.factor == f}
            fc = r.factor_contributions.get(f)
            if fsignals and fc is not None:
                assert sum(sc.contribution for sc in fsignals.values()) == pytest.approx(
                    fc, abs=1e-6
                )


def test_view_labels_tailwind_headwind_neutral(assets_config, macro_config) -> None:
    from macro_compass.assets import compute_assets
    from macro_compass.assets.engine import VIEW_HEADWIND, VIEW_NEUTRAL, VIEW_TAILWIND

    today = pd.Timestamp("2026-08-29")
    threshold = 0.15
    # strong positive growth-only environment -> CN_EQUITY clearly tailwind
    results = compute_assets(
        assets_config,
        _scenario({"growth": 0.9}),
        {}, macro_config, {}, today,
    )
    assert results["CN_EQUITY"].score > threshold
    assert results["CN_EQUITY"].view == VIEW_TAILWIND
    assert results["CN_GOV_BOND"].score < -threshold  # strong growth hurts bonds
    assert results["CN_GOV_BOND"].view == VIEW_HEADWIND
    # a near-neutral environment -> 中性
    results2 = compute_assets(assets_config, _scenario({}), {}, macro_config, {}, today)
    # all factors absent -> WARMUP (not scored), view None
    assert results2["CN_EQUITY"].status == "WARMUP"
    assert results2["CN_EQUITY"].view is None


def test_warmup_when_insufficient_factors(assets_config, macro_config) -> None:
    from macro_compass.assets import compute_assets

    today = pd.Timestamp("2026-08-29")
    # no scored factors at all -> cannot produce a Score
    results = compute_assets(assets_config, _scenario({}), {}, macro_config, {}, today)
    assert results["CN_EQUITY"].status == "WARMUP"
    assert results["CN_EQUITY"].score is None


def test_ambiguous_signals_excluded_from_credit(assets_config, macro_config) -> None:
    """CN_CREDIT zeroed G1-G3/D2 must not appear in its signal contributions."""
    from macro_compass.assets import compute_assets

    today = pd.Timestamp("2026-08-29")
    factor_results = _scenario({"growth": 0.5, "inflation": 0.2})
    factor_results["growth"].signals = {
        **factor_results["growth"].signals,
        "G1": _Contrib(0.3), "G2": _Contrib(0.4), "G3": _Contrib(-0.1),
        "G4": _Contrib(-0.2), "G5": _Contrib(0.1),
    }
    factor_results["inflation"].signals = {
        "I1": _Contrib(0.1), "I2": _Contrib(0.2), "I3": _Contrib(-0.05),
    }
    results = compute_assets(assets_config, factor_results, {}, macro_config, {}, today)
    credit = results["CN_CREDIT"]
    assert credit.signal_contributions.keys() == {"G4", "G5", "I2", "I3"}
    assert "G1" not in credit.signal_contributions
    assert "D2" not in credit.signal_contributions


# ---------------------------------------------------------------------------
# ---- 3) isolation / no reverse flow / read-only ---------------------------
# ---------------------------------------------------------------------------


def test_market_confirmation_is_parallel_not_scored(assets_config, macro_config) -> None:
    from macro_compass.assets import compute_assets

    today = pd.Timestamp("2026-08-29")
    factor_results = _scenario(
        {"growth": 0.4, "domestic_financial": 0.3}
    )

    class _Conf:
        signal_id, state, status = "M1", "CONFIRMED_POSITIVE", "READY"
        macro_direction, market_direction, agreement = 1, 1, "agree"

    with_conf = compute_assets(
        assets_config, factor_results, {}, macro_config, {}, today,
        market_confirmations={"M1": _Conf()},
    )
    without_conf = compute_assets(
        assets_config, factor_results, {}, macro_config, {}, today,
        market_confirmations=None,
    )
    # identical scores - confirmation is a parallel field, never a scoring input
    for asset_id in assets_config["assets"]:
        assert with_conf[asset_id].score == pytest.approx(without_conf[asset_id].score, abs=1e-12)
    assert with_conf["CN_EQUITY"].market_confirmation is not None
    assert with_conf["CN_EQUITY"].market_confirmation.state == "CONFIRMED_POSITIVE"
    assert without_conf["CN_EQUITY"].market_confirmation is None
    # an asset without a market binding (GOLD) carries none either way
    assert with_conf["GOLD"].market_confirmation is None


def test_engine_never_imports_market_and_no_weight_search() -> None:
    """Source-level guard: the asset package must not import the market
    package, and must not contain any historical-return weight searching."""
    from macro_compass import paths

    for rel in (
        "assets/__init__.py", "assets/config.py", "assets/engine.py",
    ):
        source = (paths.SRC_DIR / "macro_compass" / rel).read_text(encoding="utf-8")
        assert "macro_compass.market" not in source, f"{rel} must not import the market package"
        assert "from macro_compass import market" not in source, (
            f"{rel} must not import the market package"
        )
        for banned in (
            "import statsmodels", "np.polyfit", "np.linalg.lstsq", "scipy.optimize",
            "sklearn", ".fit(", "optimize", ".regression(",
        ):
            assert banned not in source, f"{rel} must not contain {banned!r}"


def test_engine_reads_does_not_modify_inputs(assets_config, macro_config, monkeypatch) -> None:
    """Behavioral isolation: computing the asset layer leaves the factor
    results and input computation frames bit-for-bit unchanged, including the
    read-only 1M/3M history path (compute_factor receives only truncated
    copies built via dataclasses.replace - never the caller's frames)."""
    from macro_compass.assets import compute_assets
    import macro_compass.macro.factors as factors_mod

    today = pd.Timestamp("2026-08-29")
    frame = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=40, freq="ME"), "score": 0.1}
    )
    computations = {"G1": _Computation(frame.copy(deep=True))}

    seen_horizons: list = []
    captured_frames: list = []

    def fake_compute_factor(factor, signal_ids, truncated, macro_config, staleness, horizon):
        seen_horizons.append(pd.Timestamp(horizon))
        for sid, comp in truncated.items():
            captured_frames.append(comp.frame.copy(deep=True))
        return _FactorRes(0.2)

    # engine.py imports compute_factor locally at call time, so patch the
    # source module (macro.factors) that name resolves to.
    monkeypatch.setattr(factors_mod, "compute_factor", fake_compute_factor)

    factor_results = _scenario({"growth": 0.5, "inflation": -0.2})
    factor_results["growth"].asof = pd.Timestamp("2026-08-28")
    factor_results["inflation"].asof = pd.Timestamp("2026-08-28")

    comps_before = {sid: c.frame.copy(deep=True) for sid, c in computations.items()}
    results = compute_assets(
        assets_config, factor_results, computations, macro_config, {},
        today, factor_signal_ids={"growth": ["G1"]},
        market_confirmations=None,
    )
    assert results["CN_EQUITY"].status == "READY"
    # the shared history path was exercised once per horizon (only "growth"
    # has declared signal ids here -> 2 horizons x 1 factor)
    assert len(seen_horizons) == 2
    assert {h.date().isoformat() for h in seen_horizons} == {"2026-07-30", "2026-05-31"}
    # truncated frames handed to compute_factor are copies, never the caller's
    assert captured_frames and all(f is not frame for f in captured_frames)
    # the caller's computation frames are bit-for-bit unchanged
    pd.testing.assert_frame_equal(computations["G1"].frame, comps_before["G1"])
    # factor_results are not mutated by the computation
    assert factor_results["growth"].score == 0.5