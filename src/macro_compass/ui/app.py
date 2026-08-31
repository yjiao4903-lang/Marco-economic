"""V3 Local Dashboard - Streamlit entry point.

Four read-only panels over the report snapshots:

1. 宏观总览  - Regime + four factors + the 15-core signal table
2. 市场确认  - Market Data Matrix + divergence states
3. 资产指引  - 7-asset directions + full Asset -> Factor -> Signal ->
               Raw Series -> Provider drill-down
4. 结构风险  - S1/S2/S3 fragility diagnostics (explicitly not part of the
               Asset Score)

Red lines honoured here (and asserted in ``tests/test_ui_loader.py``):

* read-only: this file imports only ``loader`` - never an engine module, never
  a data-update trigger / recomputation;
* synthetic is never shown as real (a visible marker is rendered when a row is
  not ``real``);
* no buy / sell / position vocabulary - Asset views are 顺风 / 逆风 / 中性 only;
* no auth / multi-user / cloud.

Run it with:
    python -m streamlit run src/macro_compass/ui/app.py
Run the four reports first (with the same --today) to refresh the snapshots.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass.ui import loader  # noqa: E402  (only the read-only loader)


st.set_page_config(
    page_title="宏观资产罗盘",
    layout="wide",
    initial_sidebar_state="expanded",
)

_REAL_MARK = "●"      # real data
_SYNTH_MARK = "◆"     # any non-real provenance shown with a visible marker


def _fmt(v, spec: str = ".3f") -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "n/a"
        return format(v, spec)
    except (TypeError, ValueError):
        return str(v)


def _score_style(value) -> str:
    if value is None:
        return " ⚪ 中性"
    if value >= 0.15:
        return " 🟩 顺风"
    if value <= -0.15:
        return " 🟥 逆风"
    return " ⚪ 中性"


def _colored_state(state: str) -> str:
    color = {
        "CONFIRMED_POSITIVE": "🟢",
        "CONFIRMED_NEGATIVE": "🔴",
        "POSITIVE_MACRO_DIVERGENCE": "🟠",
        "NEGATIVE_MACRO_DIVERGENCE": "🟣",
        "MIXED": "⚪",
    }.get(state, "⚪")
    return f"{color} {state}"


def _signal_provenance(row: dict) -> str:
    prov = str(row.get("provenance") or "").lower()
    if prov == "real":
        return f"{_REAL_MARK} 真实"
    return f"{_SYNTH_MARK} 非真实（synthetic 隔离，不展示为真实）"


def _render_header(state: loader.DashboardState) -> None:
    st.title("宏观资产罗盘 · 本地快照")
    st.caption(
        "只读快照（读取报告已产出的 CSV），不触发数据更新 / 不重新计算。"
        f" as-of 快照日：**{state.snapshot_date or '（未记录）'}**。"
    )
    if state.regime:
        st.markdown(f"#### 宏观 Regime：**{state.regime}**")


def _render_regime(state: loader.DashboardState) -> None:
    st.subheader("Regime 判定依据")
    if not state.regime_rationale:
        st.write("（无）")
    for line in state.regime_rationale:
        st.markdown(f"- {line}")


def _render_factor_cards(state: loader.DashboardState) -> None:
    if not state.factors:
        st.write("（无因子快照）")
        return
    cols = st.columns(len(state.factors))
    for col, f in zip(cols, state.factors):
        with col:
            st.metric(
                label=f"{f.get('factor_name')} ({f.get('factor')})",
                value=_fmt(f.get("score"), "+.3f"),
                delta=f"breadth {f.get('breadth')} · conf {_fmt(f.get('confidence_composite'), '.2f')}",
            )


def _signal_table(state: loader.DashboardState) -> None:
    st.subheader("15 个 Core Fundamental 信号")
    if not state.signals:
        st.write("（无信号快照）")
        return
    df = pd.DataFrame(state.signals)
    cols = [
        "signal_id", "name", "factor_name", "status", "provenance",
        "score", "level_score", "momentum_score", "coverage", "freshness",
    ]
    show = df[[c for c in cols if c in df.columns]].copy()
    show = show.rename(
        columns={
            "signal_id": "ID", "name": "信号", "factor_name": "因子",
            "status": "状态", "provenance": "数据", "score": "总分",
            "level_score": "水平分", "momentum_score": "动量分",
            "coverage": "覆盖", "freshness": "时新(天)",
        }
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption("状态：README 语义（READY / WARMUP / MISSING_INPUT）；数据 ●=真实，◆=非真实（synthetic 隔离）。")


def _signal_detail(state: loader.DashboardState, signal_id: str) -> None:
    meta = state.signal_meta.get(signal_id, {})
    if meta.get("mechanism"):
        st.markdown(f"**机制**：{meta['mechanism']}")
    row = next((s for s in state.signals if str(s.get("signal_id")) == signal_id), None)
    if row is None:
        st.write("（该信号无最新快照）")
        return
    st.markdown(f"**数据来源**：{_signal_provenance(row)}")
    st.markdown(f"**组合方式**：{row.get('combination')}（{row.get('breakdown_unit')}）")
    if row.get("breakdown"):
        st.markdown(f"**贡献分解**：`{row['breakdown']}`")
    if row.get("missing"):
        st.markdown(f"**缺失输入**：{row['missing']}")
    else:
        st.markdown("**缺失输入**：无")


def _render_market(state: loader.DashboardState) -> None:
    st.subheader("市场确认 · Market Data Matrix")
    if not state.market:
        st.write("（无市场快照）")
        return
    df = pd.DataFrame(state.market)
    cols = [
        "signal_id", "signal_name", "series_id", "status", "direction_convention",
        "as_of", "move_1m", "move_3m", "adj_trend_6m", "adj_percentile", "state",
    ]
    show = df[[c for c in cols if c in df.columns]].copy()
    show["方向"] = show["state"].map(_colored_state)
    show = show.rename(
        columns={
            "signal_id": "ID", "signal_name": "信号", "series_id": "序列",
            "status": "状态", "as_of": "as-of", "move_1m": "1M",
            "move_3m": "3M", "adj_trend_6m": "6M(方向调整)",
            "adj_percentile": "分位", "state": "Divergence",
        }
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption(
        "Divergence 五状态命名＝以未被市场确认的宏观方向命名；方向adjust按 config/market.yaml；"
        "市场层只读 factor 输出，永不反向修改基本面。"
    )


def _render_assets(state: loader.DashboardState) -> None:
    st.subheader("资产指引 · 顺风 / 逆风 / 中性")
    if not state.assets:
        st.write("（无资产快照）")
        return
    overview = pd.DataFrame(state.assets)
    show = overview[
        ["asset", "asset_name", "status", "score", "view",
         "change_1m", "change_3m", "market_state", "confidence_composite", "as_of"]
    ].copy()
    show["资产"] = show["asset_name"] + " (" + show["asset"] + ")"
    show["View"] = show["score"].map(_score_style)
    show = show.rename(
        columns={
            "asset_name": "资产名", "status": "状态", "score": "Score",
            "view": "方向", "change_1m": "1M变化", "change_3m": "3M变化",
            "market_state": "市场确认", "confidence_composite": "置信(数据质量)",
            "as_of": "as-of",
        }
    )
    st.dataframe(
        show[["资产", "状态", "Score", "View", "1M变化", "3M变化", "市场确认", "置信(数据质量)", "as-of"]],
        use_container_width=True, hide_index=True,
    )
    st.caption("Asset Score = 当前宏观环境对该资产的顺风/逆风程度；≠ 预期收益 ≠ 交易信号。市场确认为并列观察，不进入评分。")

    # ---- drill-down: Asset -> Factor -> Signal -> Raw Series -> Provider ----
    asset_ids = [a.get("asset") for a in state.assets]
    selected = st.selectbox("下钻资产（Asset → Factor → Signal → Raw Series → Provider）", asset_ids)
    st.markdown(f"### {selected}")

    factors = state.asset_factors.get(selected, [])
    if factors:
        fdf = pd.DataFrame(factors)
        chart = fdf[["factor", "factor_contribution"]].dropna().copy()
        if not chart.empty:
            chart = chart.rename(columns={"factor": "因子", "factor_contribution": "贡献(分)"})
            st.bar_chart(chart.set_index("因子"))
        st.dataframe(fdf, use_container_width=True, hide_index=True)

    sigs = state.asset_signals.get(selected, [])
    if sigs:
        st.markdown("**Signal 贡献（Asset → Factor → Signal → Series/Provider）**")
        sdf = pd.DataFrame(sigs)
        show_s = sdf[["signal_id", "factor", "signal_score", "contribution", "series_source"]].copy()
        show_s = show_s.rename(
            columns={
                "signal_id": "Signal", "factor": "因子", "signal_score": "信号分",
                "contribution": "贡献(分)", "series_source": "Raw Series → Provider",
            }
        )
        st.dataframe(show_s, use_container_width=True, hide_index=True)

        sig_options = {str(r.get("signal_id")): r for r in sigs}
        sel_sig = st.selectbox("下钻 Signal（→ Raw Series → Provider 叶子）", list(sig_options.keys()))
        row = sig_options[sel_sig]
        st.markdown(f"**{sel_sig} → {row.get('series_source')}**")
        _render_series_leaves(state, str(row.get("series_source")))
    else:
        st.write("（该资产无 signal 级贡献快照；可先运行 asset_report.py 生成）")


def _render_series_leaves(state: loader.DashboardState, series_source: str) -> None:
    """Render the Raw Series -> Provider leaf metadata for each series."""
    st.markdown("| Raw Series | 名称 | 单位 | 频率 | Provider(primary) | Fallback | 原始来源 |")
    st.markdown("|---|---|---|---|---|---|---|")
    for token in series_source.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        series_id, provider = token.split("=", 1)
        series_id = series_id.strip()
        meta = state.series_meta.get(series_id, {})
        st.markdown(
            f"| {series_id} | {meta.get('name', '')} | {meta.get('unit', '')} "
            f"| {meta.get('frequency', '')} | {provider.strip()} "
            f"| {meta.get('fallback', '')} | {meta.get('original_source', '')} |"
        )
    st.caption("Provider 取自 report 的 series/源 追踪与 data_sources.yaml 路由。")


def _render_structural(state: loader.DashboardState) -> None:
    st.subheader("结构风险 · Structural Risk（不进入资产评分）")
    st.warning("S 信号为中长期脆弱性诊断，明确不进入短期 Asset Score（MASTER SPEC §7）。")
    if not state.structural:
        st.write("（无结构风险快照）")
        return
    df = pd.DataFrame(state.structural)
    cols = [
        "signal_id", "signal_name", "display_status", "series_id", "as_of",
        "level", "percentile", "trend", "diagnostic", "provenance", "source",
    ]
    show = df[[c for c in cols if c in df.columns]].copy()
    show = show.rename(
        columns={
            "signal_id": "ID", "signal_name": "信号", "display_status": "状态",
            "series_id": "序列", "as_of": "as-of", "level": "最新值",
            "percentile": "40季分位", "trend": "4季变化", "diagnostic": "诊断",
            "provenance": "数据", "source": "来源",
        }
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption("NO_SIGNAL：无数据 ou 最新值超时（显式，禁止 synthetic）；BIS 季频约滞后 8 个月，解读为滞后确认的脆弱性指标。")


def main() -> None:
    side = st.sidebar
    side.markdown("## 本地只读 Dashboard")
    side.markdown(
        "读取四个报告脚本产出的快照 CSV，**不触发更新 / 不重新计算**。"
        "\n\n刷新快照："
        "\n```\npython scripts/macro_report.py\n"
        "python scripts/market_report.py\n"
        "python scripts/asset_report.py\n"
        "python scripts/structural_report.py\n```"
        "\n\n四脚本用**同一 --today** 时各面板 as-of 同天对齐。"
    )

    try:
        state = loader.load_dashboard()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    aligned, alignment_gaps, snapshot_dates = loader.same_day_alignment(state)
    if not aligned:
        detail = []
        if alignment_gaps:
            detail.append("缺少 snapshot_date：" + ", ".join(alignment_gaps))
        if len(snapshot_dates) > 1:
            detail.append("发现多个快照日：" + ", ".join(sorted(snapshot_dates)))
        st.error("快照未通过同日对齐门，页面已阻断；" + "；".join(detail))
        return

    synthetic = loader.synthetic_rows(state)
    if synthetic:
        st.warning(
            "检测到非真实数据，相关信号已明确降级展示（不得视为真实数据）："
            + ", ".join(synthetic)
        )
    redline_hits = loader.forbidden_words(state)
    if redline_hits:
        st.error("检测到红线词，页面已阻断：" + "；".join(redline_hits))
        return

    if state.snapshot_date:
        side.caption(f"快照日期：{state.snapshot_date}")

    _render_header(state)

    tab_macro, tab_market, tab_asset, tab_struct = st.tabs(
        ["宏观总览", "市场确认", "资产指引", "结构风险"]
    )

    with tab_macro:
        _render_regime(state)
        _render_factor_cards(state)
        _signal_table(state)
        sig_ids = [str(s.get("signal_id")) for s in state.signals]
        sel = st.selectbox("查看信号详情（含贡献分解 / 缺失输入 / 机制）", sig_ids)
        _signal_detail(state, sel)

    with tab_market:
        _render_market(state)

    with tab_asset:
        _render_assets(state)

    with tab_struct:
        _render_structural(state)

    st.divider()
    st.caption(
        "红线自检：只读快照 ✓ · synthetic 不显示为真实 ✓ · 无买卖/仓位字样 ✓ · "
        "无鉴权/多用户/云功能 ✓"
    )


if __name__ == "__main__":
    main()
