# Task — V2 Asset Compass（Window E）

> 状态：**占位文件，尚未撰写**。打开对应开发窗口之前，必须先补全本 Task Spec。

## 版本范围

V2 Asset Compass：AssetScore = Σ beta × MacroFactor，7 资产池（CN_EQUITY / HK_EQUITY /
CN_GOV_BOND / CN_CREDIT / GOLD / INDUSTRIAL_COMMODITY / CNY）。

## 硬性前置条件（负责人 2026-08-30 批准，三者缺一不开窗）

1. v0.4c Economic Coverage PASS（tag `v0.4c-pre-market-stable`）；
2. V1.6A Market Confirmation PASS（tag 见 50 号任务书）；
3. R2 Asset Prior Matrix 调研完成并经协调员验收（52 号）。

## 范围要点（负责人方案 §26–§27）

- 先验矩阵来自 R2 证据（sign + importance tier + prior range），可配置；
- 每资产输出：Score / View / 1M change / 3M change / Factor contribution /
  Signal contribution / Market confirmation / Confidence；
- 全链路可追溯：Asset → Factor → Signal → Raw Series → Provider；
- Asset Score ≠ 预期收益 ≠ 交易信号 ≠ 仓位建议（00_MASTER_SPEC §13）；
- 不得用历史收益自动搜索权重（V2.5 之前禁止）。

## 撰写要求

参照既有任务书（45、47、50）的格式补全，完成后进入 V2.5 Historical Validation
（负责人明确：V2 之后立即 V2.5，不做 UI，防止"看起来合理=有效"的认知偏差）。
