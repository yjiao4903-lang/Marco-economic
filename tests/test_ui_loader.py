"""V3 UI acceptance checks - pure, deterministic (no network, no canonical
writes). data/local is git-ignored, so these tests build small snapshot
fixtures in tmp_path and inject them via ``paths_override`` / ``snapshot_sources``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from macro_compass.ui import loader
from macro_compass.ui.loader import DashboardState


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------

def _write_csv(tmp: Path, name: str, rows: list[dict]) -> Path:
    path = tmp / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _config(tmp: Path) -> Path:
    cfg = tmp / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "indicators.yaml").write_text(
        "CN_DR007:\n  name: 存款类机构7天质押回购利率\n  category: macro\n"
        "  frequency: daily\n  unit: percent\n",
        encoding="utf-8",
    )
    (cfg / "data_sources.yaml").write_text(
        "series:\n  CN_DR007:\n    primary: chinamoney\n    fallback: wind_manual\n"
        "    original_source: CFETS DR007\n",
        encoding="utf-8",
    )
    (cfg / "signals.yaml").write_text(
        "signals:\n  D1:\n    name: Funding Condition\n    layer: core\n"
        "    factor: domestic_financial\n    mechanism: test mechanism\n",
        encoding="utf-8",
    )
    return cfg


def _overrides(tmp: Path, date: str = "2026-08-30") -> dict:
    cfg = _config(tmp)
    return {
        "config_dir": cfg,
        "macro_dashboard": _write_csv(tmp, "macro_dashboard.csv", [
            {
                "signal_id": "G1", "name": "China CLI", "factor": "growth",
                "factor_name": "增长", "status": "READY", "provenance": "real",
                "score": -0.27, "level_score": -0.47, "momentum_score": -0.07,
                "coverage": 1.0, "freshness": 90, "combination": "single",
                "breakdown": "CHN_CLI: -0.277", "breakdown_unit": "additive score points",
                "missing": "", "snapshot_date": date,
            },
        ]),
        "macro_factors": _write_csv(tmp, "macro_factors.csv", [
            {
                "kind": "factor", "factor": "growth", "factor_name": "增长",
                "score": -0.357, "breadth": 4, "breadth_detail": "G1,G2,G4,G5",
                "confidence_coverage": 1.0, "confidence_freshness": 1.0,
                "confidence_source_quality": 0.8, "confidence_composite": 0.92,
                "snapshot_date": date,
            },
            {
                "kind": "regime", "factor": "", "factor_name": "Regime",
                "score": None, "breadth": None, "breadth_detail": "growth down",
                "confidence_coverage": None, "confidence_freshness": None,
                "confidence_source_quality": None, "confidence_composite": "TRANSITION",
                "snapshot_date": date,
            },
        ]),
        "market": _write_csv(tmp, "market.csv", [
            {
                "signal_id": "M5", "signal_name": "USD/CNY", "series_id": "USD_CNY",
                "status": "READY", "as_of": "2026-08-28", "snapshot_date": date,
                "state": "CONFIRMED_POSITIVE",
            },
        ]),
        "asset": _write_csv(tmp, "asset.csv", [
            {
                "asset": "CN_EQUITY", "asset_name": "A股", "status": "READY",
                "score": -0.08, "view": "中性", "change_1m": 0.009,
                "change_3m": -0.25, "as_of": "2026-08-28",
                "factor": "growth", "factor_contribution": -0.138,
                "confidence_composite": 0.86,
            },
        ]),
        "asset_signal": _write_csv(tmp, "asset_signal.csv", [
            {
                "asset": "CN_EQUITY", "asset_name": "A股",
                "signal_id": "D1", "factor": "domestic_financial",
                "signal_score": 0.54, "contribution": 0.055,
                "series_source": "CN_DR007=CHINAMONEY", "as_of": "2026-08-28",
                "snapshot_date": date,
            },
        ]),
        "structural": _write_csv(tmp, "structural.csv", [
            {
                "signal_id": "S1", "signal_name": "Credit-to-GDP Gap",
                "display_status": "READY", "series_id": "CN_CREDIT_TO_GDP_GAP",
                "as_of": "2025-12-31", "snapshot_date": date,
                "level": -7.688, "percentile": 0.275, "trend": -0.11,
                "diagnostic": "BELOW_TREND", "provenance": "real", "source": "BIS",
            },
        ]),
    }


def _state(tmp: Path, date: str = "2026-08-30") -> DashboardState:
    return loader.load_dashboard(paths_override=_overrides(tmp, date))


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_loads_readonly_snapshot(tmp_path):
    state = _state(tmp_path)
    assert state.snapshot_date == "2026-08-30"
    assert state.regime == "TRANSITION"
    assert state.regime_rationale == ["growth down"]
    assert len(state.factors) == 1
    assert len(state.signals) == 1
    assert len(state.market) == 1
    assert len(state.assets) == 1
    assert len(state.structural) == 1
    # series + signal metadata from static config YAML
    assert state.series_meta["CN_DR007"]["provider"] == "chinamoney"
    assert state.signal_meta["D1"]["factor"] == "domestic_financial"


def test_raises_when_snapshot_missing(tmp_path):
    over = _overrides(tmp_path)
    over["asset_signal"] = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError):
        loader.load_dashboard(paths_override=over)


def test_same_day_alignment_aligned(tmp_path):
    over = _overrides(tmp_path)
    sources = (
        ("macro_raw", over["macro_dashboard"]),
        ("asset_signal", over["asset_signal"]),
        ("market", over["market"]),
        ("structural", over["structural"]),
    )
    aligned, gaps, dates = loader.same_day_alignment(DashboardState(), snapshot_sources=sources)
    assert aligned is True
    assert gaps == []
    assert dates == {"2026-08-30"}


def test_same_day_alignment_detects_mismatch_and_gap(tmp_path):
    over = _overrides(tmp_path)
    _write_csv(tmp_path, "other.csv", [{"snapshot_date": "2026-08-01"}])
    sources = (
        ("macro_raw", over["macro_dashboard"]),
        ("asset_signal", over["asset_signal"]),
        ("market", tmp_path / "other.csv"),          # different day
        ("structural", tmp_path / "no_date.csv"),    # missing file -> gap
    )
    aligned, gaps, dates = loader.same_day_alignment(DashboardState(), snapshot_sources=sources)
    assert aligned is False
    assert "structural" in gaps
    assert dates == {"2026-08-30", "2026-08-01"}


def test_no_forbidden_vocabulary_on_clean_state(tmp_path):
    state = _state(tmp_path)
    assert loader.forbidden_words(state) == []
    # healthy asset views do not trip the red line
    for view in ("中性", "顺风", "逆风"):
        state.assets[0]["view"] = view
        assert loader.forbidden_words(state) == []


def test_forbidden_vocabulary_detected():
    state = DashboardState(assets=[{"asset_name": "测试", "view": "看多买入"}])
    assert loader.forbidden_words(state) != []


def test_synthetic_never_shown_as_real(tmp_path):
    state = _state(tmp_path)
    assert loader.synthetic_rows(state) == []
    state.signals[0]["provenance"] = "SYNTHETIC"
    state.signals[0]["score"] = 0.1
    assert loader.synthetic_rows(state) == ["G1"]


def test_asset_full_chain_traceability(tmp_path):
    state = _state(tmp_path)
    traces = loader.asset_chain(state, "CN_EQUITY")
    assert len(traces) == 1
    assert "CN_EQUITY -> domestic_financial -> D1 -> CN_DR007=CHINAMONEY" in traces[0]


def test_app_source_never_calls_engine_or_update(tmp_path):
    """AC2 source check: app.py must only import the read-only loader and must
    not reference any update / compute engine entry point."""
    src = (Path(__file__).parents[1] / "src" / "macro_compass" / "ui" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "update_sources" not in src
    for token in (
        "compute_factor", "compute_assets", "compute_market_confirmations",
        "compute_structural_readings", "load_core_computations", "classify_regime",
    ):
        assert token not in src
    # only the loader is imported from the project
    assert "from macro_compass.ui import loader" in src