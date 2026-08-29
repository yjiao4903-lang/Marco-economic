"""v0.4c Pre-Market Stabilization tests: shared status resolution, Treasury /
H.10 / core-CPI parsers, private TSF derivation, fallback history preference,
overlap-check comparison. All offline and deterministic."""

from __future__ import annotations

import pandas as pd
import pytest

from macro_compass.config import load_indicator_config
from macro_compass.data_sources.fedh10 import parse_h10_broad
from macro_compass.data_sources.nbs import parse_cpi_article
from macro_compass.data_sources.pbc import derive_private_tsf_yoy, parse_report_stocks
from macro_compass.data_sources.treasury import parse_real_yield_csv
from macro_compass.signals import (
    load_signal_registry,
    resolve_signal_status,
)
from macro_compass.signals.engine import compute_signal, resolve_combination
from macro_compass.signals.status import load_core_computations


# --- shared status resolution (v0.4c Task 0) ------------------------------------


def test_resolve_signal_status_prefers_engine_warmup(tmp_path) -> None:
    indicators = load_indicator_config(paths_module().INDICATORS_YAML)
    registry = load_signal_registry(paths_module().SIGNALS_YAML, indicators)
    macro_config = {"synthetic_markers": [], "score_mapping": {"zscore_clip": 3.0, "scales": {}}}
    snapshot = load_core_computations(registry, macro_config)
    resolved = resolve_signal_status(registry, snapshot.availability, snapshot.computations)
    # every core signal has exactly one resolved status, from the engine
    for signal_id in registry.core:
        assert resolved[signal_id] == snapshot.computations[signal_id].status
    # market/structural come from registry availability, never the engine
    for signal_id in registry.by_layer("market"):
        assert resolved[signal_id] == snapshot.availability[signal_id].status


def paths_module():
    from macro_compass import paths

    return paths


# --- NBS core CPI table (v0.4c Task 1) -------------------------------------------


def test_nbs_core_cpi_from_release_table() -> None:
    title = "2026年7月份居民消费价格同比上涨0.5%"
    text = (
        "2026 年 7 月份居民消费价格主要数据 环比涨跌幅 （ % ） 同比涨跌幅 （ % ） "
        "其中：不包括食品和能源 0.3 0.9 1.1 按类别分"
    )
    rows = parse_cpi_article(title, text)
    assert rows == [(pd.Timestamp("2026-07-31"), 0.9)]


def test_nbs_core_cpi_negative_and_missing_values() -> None:
    title = "2026年1月份居民消费价格同比上涨0.5%"
    text = "其中：不包括食品和能源 0.8 -0.1 -  按类别分"
    assert parse_cpi_article(title, text) == [(pd.Timestamp("2026-01-31"), -0.1)]
    text_missing = "其中：不包括食品和能源 - - -  按类别分"
    assert parse_cpi_article(title, text_missing) == []


# --- Treasury par real yield (v0.4c Task 2) ---------------------------------------


def test_treasury_real_yield_csv() -> None:
    text = (
        'Date,"5 YR","7 YR","10 YR","20 YR","30 YR"\n'
        "08/28/2026,2.18,2.29,2.42,2.76,2.96\n"
        '08/27/2026,2.07,2.19,2.34,2.71,2.92\n'
    )
    dates, values = parse_real_yield_csv(text, "10")
    assert values == [2.34, 2.42]  # sorted ascending by date
    assert dates[-1] == pd.Timestamp("2026-08-28").date()


def test_treasury_rejects_unknown_tenor() -> None:
    with pytest.raises(Exception, match="no column"):
        parse_real_yield_csv('Date,"5 YR"\n08/28/2026,2.18', "10")


# --- Fed H.10 broad index (v0.4c Task 3) -------------------------------------------


def test_h10_broad_row() -> None:
    html = (
        "<p>Release Date: August 24, 2026</p>"
        "<table><tr><th>COUNTRY</th><th>CURRENCY</th><th>Aug. 17</th><th>Aug. 18</th>"
        "<th>Aug. 19</th><th>Aug. 20</th><th>Aug. 21</th></tr>"
        "<tr><td>Memo:</td><td>UNITED STATES</td><td>1) BROAD JAN06=100</td>"
        "<td>118.8140</td><td>118.9831</td><td>118.3328</td><td>118.2548</td>"
        "<td>118.0628</td></tr></table>"
    )
    dates, values = parse_h10_broad(html)
    assert len(dates) == 5 and values[0] == 118.8140
    assert dates[0] == pd.Timestamp("2026-08-17").date()


def test_h10_rejects_value_column_mismatch() -> None:
    html = (
        "<p>Release Date: August 24, 2026</p>"
        "<tr><th>COUNTRY</th><th>Aug. 17</th></tr>"
        "<tr><td>1) BROAD JAN06=100</td><td>118.8140</td><td>2</td></tr>"
    )
    with pytest.raises(Exception):
        parse_h10_broad(html)


# --- private TSF YoY derivation (v0.4c Task 5, D3 spike) ----------------------------


def test_private_tsf_yoy_derivation() -> None:
    stocks = parse_report_stocks(
        "2026年7月末社会融资规模存量为463.27万亿元，同比增长7.4%。"
        "政府债券余额102.68万亿元，同比增长14.1%。"
    )
    assert stocks["afre_stock"] == 463.27 and stocks["gov_stock"] == 102.68
    assert derive_private_tsf_yoy(stocks) == pytest.approx(5.63, abs=0.01)


def test_private_tsf_yoy_missing_paragraph_returns_none() -> None:
    assert parse_report_stocks("无存量段落") is None


# --- fallback prefers history-sufficient input (v0.4c Task 1) ------------------------


def _series(n: int) -> pd.Series:
    return pd.Series(range(n), dtype=float, index=pd.date_range("2026-01-01", periods=n))


def _fallback_spec() -> "object":
    from macro_compass.signals.registry import SignalSpec

    return SignalSpec(
        signal_id="T1", name="t", layer="core", factor="inflation",
        mechanism="m",
        inputs=[{"series_id": "CORE", "role": "preferred"}, {"series_id": "HEAD", "role": "fallback"}],
        transforms=[{"type": "rolling_percentile", "window": 60}],
        direction="positive", neutral=0.5,
        level_weight=0.5, momentum_weight=0.5,
    )


MACRO = {"score_mapping": {"zscore_clip": 3.0, "scales": {"default": {"level": 2.0, "momentum": 1.0}}}}


def test_fallback_uses_short_core_as_warmup() -> None:
    result = compute_signal(
        _fallback_spec(), {"CORE": _series(10)}, MACRO, pd.Timestamp("2026-08-29")
    )
    # headline missing entirely -> registry semantics: PARTIAL (data gap,
    # never converted to WARMUP); score still null (10 obs < window 60)
    assert result.status == "PARTIAL"
    assert result.frame["score"].isna().all()


def test_fallback_prefers_history_sufficient_headline() -> None:
    result = compute_signal(
        _fallback_spec(),
        {"CORE": _series(10), "HEAD": _series(223)},
        MACRO,
        pd.Timestamp("2026-08-29"),
    )
    # core present but below the declared minimum: the declared fallback wins
    assert result.status == "READY"
    assert list(result.contributions.columns) == ["HEAD"]


def test_fallback_returns_to_core_when_history_sufficient() -> None:
    result = compute_signal(
        _fallback_spec(),
        {"CORE": _series(80), "HEAD": _series(223)},
        MACRO,
        pd.Timestamp("2026-08-29"),
    )
    assert list(result.contributions.columns) == ["CORE"]


# --- overlap check comparison (v0.4c Task 2) ------------------------------------------


def test_compare_frames_stats() -> None:
    from scripts.overlap_check import compare_frames

    left = pd.DataFrame(
        {"date": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")], "value": [2.40, 2.42]}
    )
    right = pd.DataFrame(
        {"date": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-03")], "value": [2.39, 2.50]}
    )
    stats = compare_frames(left, right)
    assert stats["common_days"] == 1
    assert stats["max_abs_diff"] == pytest.approx(0.01)
    assert stats["left_only_days"] == 1 and stats["right_only_days"] == 1
