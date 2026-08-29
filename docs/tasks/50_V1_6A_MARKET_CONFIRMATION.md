# Task — V1.6A Market Confirmation（Window D1）

> 状态：**占位文件，尚未撰写**。打开对应开发窗口之前，必须先补全本 Task Spec。

## 版本范围

V1.6A Market Confirmation（M1–M6 引擎）。**不含 Asset Compass**（负责人 2026-08-30 批准：
V2 独立开窗口；也不含 Structural Risk，后者已后移至 V2.6）。

## 前置条件

- v0.4c Pre-Market Stabilization 完成（tag `v0.4c-pre-market-stable`）；
- Fundamental Core 覆盖达到 Economic Coverage Gate（Growth 5/5、Inflation 3/3、
  Domestic ≥3/4、Global 3/3，D3 允许 PARTIAL）；
- Fundamental Core 自 v0.4c 起冻结。

## 范围要点（负责人方案 §18–§22）

1. **第一阶段是 Market Data Readiness 而非引擎**：先产出 Market Data Matrix
   （6 个市场信号的 provider/history/frequency/freshness/READY），
   最低 5/6 real READY，禁止 synthetic 进入 production Market Confirmation；
2. 复用既有 provider（ChinaBond、USD/CNY、AKShare、Eastmoney），不新造架构；
3. 市场信号首版统一计算 1M/3M move、6M trend、rolling percentile，
   并按经济方向统一（10Y yield 下行不能简单视为 positive，需与宏观语境对齐）；
4. 核心产出为 Divergence 状态（CONFIRMED_POSITIVE / CONFIRMED_NEGATIVE /
   POSITIVE_MACRO_DIVERGENCE / NEGATIVE_MACRO_DIVERGENCE / MIXED），
   保留 macro direction / market direction / agreement / confidence；
   禁止把 Divergence 翻译成 BUY/SELL；
5. Market 层与 Fundamental 层隔离的硬约束不变（00_MASTER_SPEC §4、02_ARCHITECTURE §10）。

## 撰写要求

参照既有任务书（45、47）的格式补全：逐条 Acceptance Criteria、smoke 命令、
Frozen Components 清单（含 v0.4c 新冻结项）、文档更新与 Git checkpoint
（建议 tag：v0.5-market-confirmation 或按协调员建议）。
