"""V1.2C + V1.5D tests: parsers, cumulative conversion, update policies,
synthetic isolation, WARMUP and saturation diagnostics.

All tests are deterministic: offline fixtures, no network, no repo writes
(tmp_path for any canonical/vintage IO).
"""

from __future__ import annotations

import pandas as pd
import pytest

from macro_compass.data_sources.chicagofed import parse_nfci_csv
from macro_compass.data_sources.chinabond import parse_yz_query
from macro_compass.data_sources.chinamoney import parse_dr007_csv
from macro_compass.data_sources.cumulative import cumulative_to_monthly
from macro_compass.data_sources.manual_series import expand_steps_daily, read_steps
from macro_compass.data_sources.nbs import (
    parse_cpi_article,
    parse_listing,
    parse_pmi_input_price,
    parse_pmi_new_orders,
    parse_property_article,
)
from macro_compass.data_sources.nyfed import parse_gscpi_csv
from macro_compass.data_sources.pbc import (
    parse_omo_announcement,
    parse_omo_listing,
    parse_report_cumulative,
    parse_stats_listing,
)
from macro_compass.signals import SignalSpec, compute_signal
from macro_compass.signals.engine import _required_history
from macro_compass.synthetic_guard import filter_synthetic, is_synthetic


# --- cumulative conversion ------------------------------------------------------


def test_cumulative_year_resets_to_first_period_flow() -> None:
    dates, flows = cumulative_to_monthly(
        [11, 12, 1, 2], [2025, 2025, 2026, 2026], [100.0, 150.0, 40.0, 90.0]
    )
    assert flows == [50.0, 50.0]
    assert [d.month for d in dates] == [12, 2]


def test_cumulative_jan_feb_combined_release_is_one_flow() -> None:
    # NBS reports 1-2月 combined: the February cumulative IS the period flow
    dates, flows = cumulative_to_monthly([2, 3], [2026, 2026], [80.0, 130.0])
    assert flows == [50.0]
    assert dates[0].month == 3


def test_cumulative_missing_month_not_zero_filled() -> None:
    dates, flows = cumulative_to_monthly(
        [1, 3], [2026, 2026], [10.0, 40.0]  # February missing entirely
    )
    # Neither first point nor March after a missing February is a monthly flow.
    assert dates == []
    assert flows == []


def test_cumulative_chain_resumes_after_gap_with_new_consecutive_pair() -> None:
    dates, flows = cumulative_to_monthly([1, 3, 4], [2026, 2026, 2026], [10.0, 40.0, 55.0])
    assert [d.month for d in dates] == [4]
    assert flows == [15.0]


def test_cumulative_revision_wins_and_negative_flow_kept() -> None:
    # later report revises February cumulative downward -> negative March flow
    dates, flows = cumulative_to_monthly(
        [2, 2, 3], [2026, 2026, 2026], [100.0, 90.0, 85.0]
    )
    assert flows == [-5.0]


# --- provider parsers -------------------------------------------------------------


def test_chicagofed_csv_parses_friday_column() -> None:
    text = (
        "Friday_of_Week,NFCI,ANFCI,Risk\n"
        "01/08/1971,0.6,0.584,0.627\n"
        "01/15/1971,0.633,0.638,0.657\n"
    )
    dates, values = parse_nfci_csv(text, "ANFCI")
    assert dates == [pd.Timestamp("1971-01-08").date(), pd.Timestamp("1971-01-15").date()]
    assert values == [0.584, 0.638]


def test_chinamoney_dr007_csv_parses_column_layout() -> None:
    text = (
        "2026-08-28,,,,,,1.3378,1.3859,1.4069\n"
        "2026-08-27,,,,,,1.3594,1.395,1.41\n"
    )
    dates, values = parse_dr007_csv(text, "DR007")
    assert dates[-1] == pd.Timestamp("2026-08-28").date()
    assert values == [1.395, 1.3859]


def test_chinabond_yz_query_parses_millis_series() -> None:
    text = (
        '[{"seriesData": [[1785686400000, 1.7169], [1785772800000, 1.7126]],'
        ' "dcq": 10.0, "ycDefName": "10年"}]'
    )
    dates, values = parse_yz_query(text)
    assert len(dates) == 2 and values == [1.7169, 1.7126]


def test_nyfed_gscpi_uses_latest_vintage_column() -> None:
    text = (
        "Date,Jan-22,Jul-26,Aug-26\n"
        "31-May-2026,#N/A,1.81,1.81\n"
        "30-Jun-2026,#N/A,1.25,1.19\n"
        "31-Jul-2026,#N/A,#N/A,0.79\n"
    )
    dates, values = parse_gscpi_csv(text)
    assert dates[-1].month == 7 and values[-1] == 0.79
    assert values == [1.81, 1.19, 0.79]


def test_pbc_omo_listing_and_announcement(tmp_path) -> None:
    html = (
        '<a href="/zhengcehuobisi/125207/125213/125431/125475/2026082808585347002/index.html"'
        ' title="公开市场业务交易公告 [2026]第168号">link</a>'
    )
    urls = parse_omo_listing(html, "http://www.pbc.gov.cn")
    assert len(urls) == 1 and "2026082808585347002" in urls[0]

    body = (
        "<p>2026年8月28日中国人民银行以固定利率、数量招标方式开展了200亿元7天期逆回购操作</p>"
        "<table><tr><td>7 天</td><td>1. 40 %</td><td>200 亿元</td></tr></table>"
        "文章来源： 2026-08-28 09:20:30"
    )
    parsed = parse_omo_announcement(body, urls[0])
    assert parsed is not None
    date, rate = parsed
    assert date == pd.Timestamp("2026-08-28") and rate == 1.40


def test_pbc_stats_report_cumulative() -> None:
    text = (
        "二、前七个月社会融资规模增量累计为22.25万亿元 其中，政府债券净融资7.76万亿元，"
        "同比少1.15万亿元；企业债券净融资2.52万亿元"
    )
    values = parse_report_cumulative(text)
    assert values["TSF_TOTAL"] == pytest.approx(222500.0)
    assert values["GOV_BOND_FINANCING"] == pytest.approx(77600.0)


def test_pbc_stats_listing_extracts_monthly_reports() -> None:
    html = (
        '<a href="/diaochatongjisi/116219/116225/2026081416320925645/index.html">'
        "2026年7月金融统计数据报告</a>"
        '<a href="/x/index.html">2026年上半年金融统计数据报告</a>'
    )
    reports = parse_stats_listing(html, "http://www.pbc.gov.cn")
    assert any("2026年7月" in t for t, _ in reports)
    assert any("上半年" in t for t, _ in reports)


# --- NBS article parsers ------------------------------------------------------------


def test_nbs_listing_parse_dedupes_titles() -> None:
    html = (
        '<a href="./202607/t20260731_1964253.html">2026年7月中国采购经理指数运行情况</a>'
        '<a href="./202607/t20260731_1964253.html">2026年7月中国采购经理指数运行情况</a>'
    )
    assert len(parse_listing(html)) == 1


def test_nbs_pmi_new_orders_sentence() -> None:
    title = "2026年7月中国采购经理指数运行情况"
    text = " 新订单指数为 48.5% ，比上月下降 2.7 个百分点。"
    rows = parse_pmi_new_orders(title, text)
    assert rows == [(pd.Timestamp("2026-07-31"), 48.5)]


def test_nbs_pmi_input_price_table() -> None:
    text = (
        "购进价格 出厂 价格 产成品 库存 在手 订单 生产经营活动预期 "
        "2025年7月 47.1 47.8 49.5 51.5 48.3 47.4 44.7 "
        "2025年6月 50.2 48.1 49.3 52.0 48.1 47.2 44.9"
    )
    rows = parse_pmi_input_price(text)
    assert len(rows) == 2
    assert rows[0] == (pd.Timestamp("2025-06-30"), 50.2)
    assert rows[1] == (pd.Timestamp("2025-07-31"), 47.1)


def test_nbs_property_cumulative_yoy_signed() -> None:
    title = "2026年1—7月份全国房地产市场基本情况"
    text = (
        "1—7月份，新建商品房销售面积45021万平方米，同比下降11.8%；"
        "新建商品房销售额42718亿元，下降13.1%。"
    )
    parsed = parse_property_article(title, text)
    assert parsed["PROPERTY_SALES_AREA"] == [(pd.Timestamp("2026-07-31"), -11.8)]
    assert parsed["PROPERTY_SALES_VALUE"] == [(pd.Timestamp("2026-07-31"), -13.1)]


def test_nbs_core_cpi_yoy() -> None:
    title = "2026年7月份居民消费价格同比上涨0.5%"
    text = "核心CPI：扣除食品和能源价格后，环比上涨0.3%，同比上涨0.9%，保持稳定。"
    rows = parse_cpi_article(title, text)
    assert rows == [(pd.Timestamp("2026-07-31"), 0.9)]


# --- manual series ------------------------------------------------------------------


def test_manual_steps_expand_daily(tmp_path) -> None:
    path = tmp_path / "X.csv"
    path.write_text("date,value\n2024-01-01,1.80\n2024-07-22,1.70\n", encoding="utf-8")
    steps = read_steps(path)
    dates, values = expand_steps_daily(steps, pd.Timestamp("2024-07-24"))
    assert values == [1.80] * 203 + [1.70] * 3
    assert dates[-1] == pd.Timestamp("2024-07-24").date()


# --- synthetic isolation --------------------------------------------------------------


def test_synthetic_guard_row_level_filter() -> None:
    frame = pd.DataFrame(
        {
            "series_id": ["A", "A"],
            "date": [1, 2],
            "value": [1.0, 2.0],
            "source_file": ["wind_macro_sample.csv", "oecd_export.csv"],
        }
    )
    assert is_synthetic("wind_macro_sample.csv", ["wind_macro_sample"])
    real = filter_synthetic(frame, ["wind_macro_sample"])
    assert len(real) == 1 and real.iloc[0]["source_file"] == "oecd_export.csv"
    # explicit opt-in keeps everything
    assert len(filter_synthetic(frame, ["wind_macro_sample"], allow_synthetic=True)) == 2


def test_production_report_excludes_synthetic(tmp_path, monkeypatch) -> None:
    # canonical rows from the fixture must not feed the signal engine
    from macro_compass.signals.engine import SignalComputation  # noqa: F401

    frame = pd.DataFrame(
        {
            "series_id": ["CHN_CLI"] * 2,
            "date": [pd.Timestamp("2026-06-01"), pd.Timestamp("2026-06-02")],
            "value": [100.0, 100.0],
            "source": ["OECD", "WIND"],
            "source_file": ["oecd.csv", "wind_macro_sample.csv"],
        }
    )
    markers = ["wind_macro_sample"]
    filtered = filter_synthetic(frame, markers)
    # the OECD row survives, the synthetic WIND row is dropped
    assert filtered["source_file"].tolist() == ["oecd.csv"]


# --- WARMUP (V1.5D) -------------------------------------------------------------------


def _spec(transforms, momentum=None, combination=None) -> SignalSpec:
    inputs = [
        {"series_id": "A", "role": "level"},
        {"series_id": "B", "role": "level"},
    ]
    return SignalSpec(
        signal_id="T1", name="t", layer="core", factor="growth",
        mechanism="m", inputs=inputs, transforms=transforms,
        momentum_transform=momentum, direction="positive", neutral=0.0,
        level_weight=0.5, momentum_weight=0.5, combination=combination,
    )


def _series(n: int) -> pd.Series:
    return pd.Series(range(n), dtype=float, index=pd.date_range("2026-01-01", periods=n))


MACRO = {"score_mapping": {"zscore_clip": 3.0, "scales": {"default": {"level": 2.0, "momentum": 1.0}}}}


def test_required_history_derived_from_declared_chain() -> None:
    assert _required_history(_spec([{"type": "level"}])) == 1
    assert _required_history(_spec([{"type": "rolling_percentile", "window": 60}])) == 60
    assert _required_history(
        _spec([{"type": "yoy", "periods": 12}], momentum={"type": "delta", "periods": 3})
    ) == 13


def test_warmup_when_history_below_declared_minimum() -> None:
    spec = _spec([{"type": "rolling_percentile", "window": 60}])
    result = compute_signal(spec, {"A": _series(36), "B": _series(36)}, MACRO, pd.Timestamp("2026-08-29"))
    assert result.status == "WARMUP"
    assert result.frame["score"].isna().all()  # no fabricated scores


def test_ready_once_history_reaches_declared_minimum() -> None:
    spec = _spec([{"type": "rolling_percentile", "window": 60}])
    result = compute_signal(spec, {"A": _series(60), "B": _series(60)}, MACRO, pd.Timestamp("2026-08-29"))
    assert result.status == "READY"
    assert result.frame["score"].notna().any()


def test_warmup_difference_needs_full_joint_history() -> None:
    spec = _spec([{"type": "rolling_percentile", "window": 60}], combination="difference")
    result = compute_signal(spec, {"A": _series(30), "B": _series(30)}, MACRO, pd.Timestamp("2026-08-29"))
    assert result.status == "WARMUP"


def test_missing_leg_stays_partial_not_warmup() -> None:
    spec = _spec([{"type": "level"}], combination="difference")
    result = compute_signal(spec, {"A": _series(10)}, MACRO, pd.Timestamp("2026-08-29"))
    assert result.status == "PARTIAL"


# --- canonical update policies ---------------------------------------------------------


@pytest.fixture
def tmp_canonical(tmp_path, monkeypatch):
    from macro_compass.storage import canonical_store

    macro_path = tmp_path / "macro.parquet"
    market_path = tmp_path / "market.parquet"
    monkeypatch.setattr(
        canonical_store, "CATEGORY_FILES",
        {"macro": macro_path, "market": market_path},
    )
    return canonical_store, macro_path


def _rows(series_id: str, dates: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": series_id,
            "date": [pd.Timestamp(d).date() for d in dates],
            "value": values,
            "source": "PBC",
            "source_file": "test",
            "import_time": pd.Timestamp.now(),
            "category": "macro",
        }
    )


def test_replace_window_preserves_outside_history(tmp_canonical) -> None:
    store, path = tmp_canonical
    store.append_canonical(_rows("S", ["2026-01-01", "2026-02-01", "2026-03-01"], [1, 2, 3]))
    revised = _rows("S", ["2026-02-01", "2026-03-01"], [2.5, 3.5])
    store.replace_window(revised)
    stored = store.read_canonical("macro")
    jan = stored[stored["date"] == pd.Timestamp("2026-01-01").date()]["value"].iloc[0]
    feb = stored[stored["date"] == pd.Timestamp("2026-02-01").date()]["value"].iloc[0]
    assert jan == 1 and feb == 2.5  # inside window replaced, outside preserved
    assert len(stored) == 3


def test_replace_series_full_refresh(tmp_canonical) -> None:
    store, path = tmp_canonical
    store.append_canonical(_rows("S", ["2026-01-01"], [1.0]))
    store.append_canonical(_rows("T", ["2026-01-01"], [9.0]))
    fresh = _rows("S", ["2026-01-01", "2026-02-01"], [1.5, 2.5])
    store.replace_series(fresh)
    stored = store.read_canonical("macro")
    assert set(stored["series_id"]) == {"S", "T"}  # other series untouched
    assert len(stored[stored["series_id"] == "S"]) == 2
