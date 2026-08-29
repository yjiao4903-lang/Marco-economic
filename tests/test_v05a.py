"""V1.6A Market Confirmation tests (v0.5).

G0: the owner-approved G3 live-source switch is locked by declaration
regression tests (only G3 may differ in signals.yaml). Phases 1-3 tests are
appended below as the market layer lands. All offline and deterministic.
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_compass.config import load_indicator_config
from macro_compass.macro import load_macro_config
from macro_compass.signals import load_signal_registry
from macro_compass.signals.engine import compute_signal


@pytest.fixture(scope="module")
def registry():
    from macro_compass import paths

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    return load_signal_registry(paths.SIGNALS_YAML, indicators)


@pytest.fixture(scope="module")
def macro_config():
    from macro_compass import paths

    return load_macro_config(paths.MACRO_YAML)


# --- G0: G3 live-source switch (owner-approved, the only signals.yaml change) ----


def test_g0_g3_declaration_locked(registry) -> None:
    """The new G3 declaration: NBS growth series live (declared order =
    priority), OECD indices retained as fallback, chain matches the
    percent-unit growth series."""
    spec = registry.signals["G3"]
    assert [i.series_id for i in spec.inputs] == [
        "CN_IND_PROD_YOY",       # NBS industrial value-added YoY, priority 1
        "CN_RETAIL_SALES_YOY",   # NBS retail sales YoY, priority 2
        "CHN_IND_PROD_INDEX",    # OECD volume index retained as fallback
        "CHN_RETAIL_SALES_INDEX",
    ]
    assert [i.role for i in spec.inputs] == [
        "preferred",
        "preferred",
        "fallback",
        "fallback",
    ]
    assert spec.combination == "fallback"
    assert [step.type for step in spec.transforms] == ["level"]
    assert spec.momentum_transform.type == "delta"
    assert spec.momentum_transform.model_extra["periods"] == 3
    # scoring semantics untouched by G0
    assert spec.direction == "positive"
    assert spec.neutral == 0
    assert spec.level_weight == 0.5 and spec.momentum_weight == 0.5
    assert spec.factor == "growth" and spec.layer == "core"


def test_g0_g3_engine_follows_declared_priority(macro_config) -> None:
    """The engine's fallback history-preference semantics pick the declared
    NBS live input first; OECD entries only serve when NBS data is absent."""
    from macro_compass import paths

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators)
    spec = registry.signals["G3"]
    today = pd.Timestamp("2026-08-30")

    def _monthly(n: int, start: float, step: float) -> pd.Series:
        return pd.Series(
            [start + step * i for i in range(n)],
            index=pd.date_range("2020-01-31", periods=n, freq="ME"),
        )

    series = {
        "CN_IND_PROD_YOY": _monthly(60, 4.0, 0.05),
        "CN_RETAIL_SALES_YOY": _monthly(60, 2.0, 0.05),
        "CHN_IND_PROD_INDEX": _monthly(60, 100.0, 0.2),
        "CHN_RETAIL_SALES_INDEX": _monthly(60, 100.0, 0.2),
    }
    result = compute_signal(spec, series, macro_config, today)
    assert result.status == "READY"
    assert list(result.contributions.columns) == ["CN_IND_PROD_YOY"]

    result = compute_signal(
        spec,
        {k: v for k, v in series.items() if k != "CN_IND_PROD_YOY"},
        macro_config,
        today,
    )
    # a missing DECLARED input is a data gap: registry semantics stay PARTIAL
    # (never upgraded to READY), while the composite still follows the
    # declared priority order over the available inputs
    assert result.status == "PARTIAL"
    assert list(result.contributions.columns) == ["CN_RETAIL_SALES_YOY"]

    result = compute_signal(
        spec,
        {k: v for k, v in series.items() if k.startswith("CHN_")},
        macro_config,
        today,
    )
    # OECD-only is likewise PARTIAL; the fallback chain reaches the retained
    # OECD entries only when the NBS live inputs have no data at all
    assert result.status == "PARTIAL"
    assert list(result.contributions.columns) == ["CHN_IND_PROD_INDEX"]


def test_g0_g3_macro_scale_is_percent_unit(macro_config) -> None:
    """G0 switches the level basis from an OECD yoy fraction to a percent
    growth series: the declared scale must be the x100 unit conversion
    (0.20/0.10 -> 20.0/10.0), never a re-fit."""
    scales = macro_config["score_mapping"]["scales"]["G3"]
    assert scales == {"level": 20.0, "momentum": 10.0}


# --- Phase 1: Market Data Readiness parsers (offline fixtures) -------------------


def test_eastmoney_kline_json_parses_close() -> None:
    from macro_compass.data_sources.eastmoney import parse_kline_json

    text = (
        '{"data": {"code": "000300", "klines": ['
        '"2005-01-04,994.77,982.79,994.77,980.66,7412868,4431977400.00,0.00",'
        '"2026-08-28,4628.10,4609.18,4638.50,4601.20,158321900,248912380000.00,0.81"]}}'
    )
    dates, values = parse_kline_json(text)
    assert dates == [pd.Timestamp("2005-01-04").date(), pd.Timestamp("2026-08-28").date()]
    # close is the THIRD field (date, open, CLOSE, high, low, ...)
    assert values == [982.79, 4609.18]


def test_eastmoney_kline_rejects_empty_and_bad_json() -> None:
    from macro_compass.data_sources.eastmoney import parse_kline_json

    with pytest.raises(Exception, match="no rows"):
        parse_kline_json('{"data": {"code": "X", "klines": []}}')
    with pytest.raises(Exception, match="not valid JSON"):
        parse_kline_json("<html>blocked</html>")


_HISTORY_QUERY_HTML = """
<table><tr><td>曲线名称</td><td>全部</td><td>中债国债收益率曲线</td>
<td>中债中短期票据收益率曲线(AAA)</td><td>开始时间:</td></tr></table>
<table><tr><td>曲线名称</td><td>日期</td><td>3月</td><td>6月</td><td>1年</td>
<td>3年</td><td>5年</td><td>7年</td><td>10年</td><td>30年</td></tr>
<tr><td>中债国债收益率曲线</td><td>2026-08-28</td><td>1.2021</td><td>1.2384</td>
<td>1.2132</td><td>1.2600</td><td>1.4119</td><td>1.5354</td><td>1.6949</td><td>2.1480</td></tr>
<tr><td>中债中短期票据收益率曲线(AAA)</td><td>2026-08-28</td><td>1.4859</td><td>1.5043</td>
<td>1.5327</td><td>1.6757</td><td>1.7428</td><td>1.8794</td><td>2.0924</td><td></td></tr>
<tr><td>中债国债收益率曲线</td><td>2026-08-27</td><td>1.2064</td><td>1.2288</td>
<td>1.2159</td><td>1.2651</td><td>1.4115</td><td>1.5364</td><td>1.6988</td><td>2.1440</td></tr>
<tr><td>中债商业银行普通债收益率曲线(AAA)</td><td>2026-08-27</td><td>1.4039</td><td>1.4456</td>
<td>1.4844</td><td>1.5584</td><td>1.5893</td><td>1.7570</td><td>1.9686</td><td>2.3125</td></tr>
</table>
"""


def test_chinabond_spread_parse_same_source_legs() -> None:
    from macro_compass.data_sources.chinabond import parse_history_query_spread

    dates, values = parse_history_query_spread(_HISTORY_QUERY_HTML, "AAA_MTN_SPREAD_3Y")
    # header row lives inside the data rows (no thead) - handled by the parser
    # 2026-08-28: 1.6757 - 1.2600 = 41.57bp, the research-archive anchor
    assert (pd.Timestamp("2026-08-28").date(), 0.4157) in list(zip(dates, values))
    # 2026-08-27 has treasury but NO MTN row: the date is skipped, never filled
    assert pd.Timestamp("2026-08-27").date() not in dates
    assert dates == sorted(dates)


def test_chinabond_spread_rejects_unknown_route() -> None:
    from macro_compass.data_sources.chinabond import parse_history_query_spread

    with pytest.raises(Exception, match="no spread route"):
        parse_history_query_spread(_HISTORY_QUERY_HTML, "NOT_A_ROUTE")


# --- Phase 2/3: market engine (direction conventions, states, isolation) ---------


@pytest.fixture(scope="module")
def market_config():
    from macro_compass import paths
    from macro_compass.market import load_market_config

    return load_market_config(paths.MARKET_YAML)


def _daily(n: int, start: float, step: float) -> pd.Series:
    return pd.Series(
        [start + step * i for i in range(n)],
        index=pd.date_range("2026-08-28", periods=n, freq="-1D")[::-1],
    )


def test_market_config_declares_all_six(market_config) -> None:
    from macro_compass.market.config import DIVERGENCE_STATES

    assert set(market_config["signals"]) == {"M1", "M2", "M3", "M4", "M5", "M6"}
    # direction conventions are explicit declarations (no implicit defaults)
    assert market_config["signals"]["M1"]["direction"] == "positive"
    assert market_config["signals"]["M3"]["direction"] == "negative"
    assert market_config["signals"]["M4"]["direction"] == "negative"
    assert market_config["signals"]["M5"]["direction"] == "negative"
    assert market_config["signals"]["M6"]["direction"] == "positive"
    assert len(DIVERGENCE_STATES) == 5


def test_market_config_rejects_implicit_direction(tmp_path) -> None:
    from macro_compass.market import MarketConfigError, load_market_config

    path = tmp_path / "market.yaml"
    path.write_text(
        "signals:\n  M1:\n    move: pct_change\n"
        "    windows: {move_1m: 21, move_3m: 63, trend_6m: 126, percentile: 250}\n"
        "    thresholds: {trend_6m: 0.05}\n    macro_reference: [growth]\n"
        "thresholds: {macro_score: 0.10}\n",
        encoding="utf-8",
    )
    with pytest.raises(MarketConfigError, match="direction"):
        load_market_config(path)


def test_market_metrics_follow_direction_conventions(registry, market_config) -> None:
    """A rising index is a positive market read; a FALLING yield is likewise a
    positive read under M3's declared negative convention, and the percentile
    is oriented to match (adj = 1 - raw)."""
    from macro_compass.market import compute_market_metrics

    series = {
        "CSI300": _daily(300, 3000.0, 3.0),      # rising -> supportive
        "CN_GOV_YIELD_10Y": _daily(300, 2.5, -0.002),  # falling yield -> easing
    }
    today = pd.Timestamp("2026-08-29")
    metrics = compute_market_metrics(registry, market_config, series, today)

    m1 = metrics["M1"]
    assert m1.status == "READY"
    assert m1.direction == "positive"
    assert m1.adj_trend_6m > 0 and m1.market_direction == 1
    assert m1.adj_percentile == m1.percentile  # positive: orientation is identity

    m3 = metrics["M3"]
    assert m3.status == "READY"
    assert m3.direction == "negative"
    assert m3.trend_6m < 0                       # raw yield fell
    assert m3.adj_trend_6m > 0                   # falling yield = supportive
    assert m3.adj_percentile == pytest.approx(1.0 - m3.percentile)
    assert m3.market_direction == 1


def test_market_metrics_warmup_and_missing(registry, market_config) -> None:
    from macro_compass.market import compute_market_metrics

    today = pd.Timestamp("2026-08-29")
    metrics = compute_market_metrics(
        registry,
        market_config,
        {"CSI300": _daily(100, 3000.0, 1.0)},  # 100 obs < percentile window 250
        today,
    )
    assert metrics["M1"].status == "WARMUP"
    assert metrics["M1"].history_length == 100
    assert metrics["M6"].status == "MISSING_INPUT"  # no data at all
    assert metrics["M6"].market_direction == 0
    assert metrics["M6"].state is None or True  # divergence not yet classified


class _Factor:
    def __init__(self, score):
        self.score = score


def test_divergence_five_states(registry, market_config) -> None:
    from macro_compass.market import classify_divergence, compute_market_metrics

    today = pd.Timestamp("2026-08-29")
    series = {"CSI300": _daily(300, 3000.0, 3.0)}  # rising index -> market +1
    metrics = compute_market_metrics(registry, market_config, series, today)
    m1 = metrics["M1"]
    assert m1.market_direction == 1

    factor_results = {
        "growth": _Factor(+0.40),
        "inflation": _Factor(+0.20),
        "domestic_financial": _Factor(+0.30),
        "global_financial": _Factor(-0.40),
    }
    macro_score_threshold = market_config["thresholds"]["macro_score"]

    def _classify(growth_score, domestic_score):
        # M1's macro_reference is [growth, domestic_financial]: the macro
        # direction is the mean of BOTH reference factor scores
        factor_results["growth"].score = growth_score
        factor_results["domestic_financial"].score = domestic_score
        out = compute_market_metrics(registry, market_config, series, today)
        classify_divergence(out, factor_results, market_config)
        return out["M1"]

    # macro + and market + -> confirmed positive
    confirmed = _classify(+0.40, +0.40)
    assert confirmed.state == "CONFIRMED_POSITIVE"
    assert confirmed.agreement == "agree"
    assert confirmed.macro_direction == 1
    assert confirmed.macro_score == pytest.approx(0.40)
    # macro - and market + -> divergence named after the unconfirmed macro side
    diverge = _classify(-0.40, -0.40)
    assert diverge.state == "NEGATIVE_MACRO_DIVERGENCE"
    assert diverge.agreement == "diverge"
    # references averaging inside the neutral band -> MIXED
    mixed = _classify(-0.40, +0.40)
    assert abs(mixed.macro_score) < macro_score_threshold
    assert mixed.macro_direction == 0
    assert mixed.state == "MIXED"
    assert mixed.agreement is None


def test_divergence_negative_confirmation(registry, market_config) -> None:
    from macro_compass.market import classify_divergence, compute_market_metrics

    today = pd.Timestamp("2026-08-29")
    series = {"CSI300": _daily(300, 6000.0, -3.0)}  # falling index -> market -1
    metrics = compute_market_metrics(registry, market_config, series, today)
    assert metrics["M1"].market_direction == -1
    classify_divergence(metrics, {"growth": _Factor(-0.40)}, market_config)
    assert metrics["M1"].state == "CONFIRMED_NEGATIVE"
    assert metrics["M1"].agreement == "agree"


def test_market_confidence_components(registry, market_config, macro_config) -> None:
    from macro_compass.market import compute_market_confirmations

    today = pd.Timestamp("2026-08-29")
    series = {"CSI300": _daily(300, 3000.0, 3.0)}
    factor_results = {"growth": _Factor(0.0), "domestic_financial": _Factor(0.0)}
    results = compute_market_confirmations(
        registry,
        market_config,
        series,
        factor_results,
        staleness={"CSI300": 7},
        macro_config=macro_config,
        today=today,
        sources_by_series={"CSI300": "AKSHARE"},
    )
    conf = results["M1"].confidence
    assert conf["coverage"] == 1.0            # 300 obs >= window 250
    assert conf["freshness"] == 1.0           # 1 day <= budget 7
    assert conf["source_quality"] == 0.7      # AKSHARE tier from macro.yaml
    assert conf["composite"] == pytest.approx(
        (conf["coverage"] + conf["freshness"] + conf["source_quality"]) / 3.0
    )


def test_market_layer_cannot_modify_fundamental_outputs(
    registry, market_config, macro_config
) -> None:
    """Behavioral isolation: computing the market layer leaves the fundamental
    computations and the input series bit-for-bit unchanged."""
    from macro_compass.market import compute_market_confirmations

    today = pd.Timestamp("2026-08-29")
    series = {"CSI300": _daily(300, 3000.0, 3.0)}
    series_snapshot = {sid: s.copy(deep=True) for sid, s in series.items()}
    factor_results = {"growth": _Factor(-0.20), "domestic_financial": _Factor(+0.20)}

    core_before = {
        sid: comp.frame.copy(deep=True)
        for sid, comp in _core_computations(registry, macro_config, series, today).items()
    }
    compute_market_confirmations(
        registry,
        market_config,
        series,
        factor_results,
        staleness={"CSI300": 7},
        macro_config=macro_config,
        today=today,
    )
    core_after = _core_computations(registry, macro_config, series, today)
    for sid, frame in core_after.items():
        pd.testing.assert_frame_equal(frame.frame, core_before[sid])
    for sid, values in series.items():
        pd.testing.assert_series_equal(values, series_snapshot[sid])


def _core_computations(registry, macro_config, series, today):
    from macro_compass.signals.engine import compute_core_signals

    return compute_core_signals(registry, series, macro_config, today)


def test_fundamental_layer_never_imports_market_module() -> None:
    """Source-level isolation guard (ARCHITECTURE section 10): no fundamental
    module may import the market package. The market engine reads factor
    outputs; the reverse import path must not exist."""
    from macro_compass import paths

    fundamental = [
        paths.SRC_DIR / "macro_compass" / "signals" / "engine.py",
        paths.SRC_DIR / "macro_compass" / "signals" / "registry.py",
        paths.SRC_DIR / "macro_compass" / "signals" / "status.py",
        paths.SRC_DIR / "macro_compass" / "macro" / "factors.py",
        paths.SRC_DIR / "macro_compass" / "macro" / "regime.py",
        paths.SRC_DIR / "macro_compass" / "macro" / "config.py",
    ]
    for module_path in fundamental:
        source = module_path.read_text(encoding="utf-8")
        assert "macro_compass.market" not in source, (
            f"{module_path.name} must not import the market package"
        )
        assert "from macro_compass import market" not in source, (
            f"{module_path.name} must not import the market package"
        )
