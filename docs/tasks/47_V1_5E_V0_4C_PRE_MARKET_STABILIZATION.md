# Task — V1.5E / v0.4c Pre-Market Stabilization

> **来源与状态**：本任务书由项目负责人 2026-08-30 评审意见《v0.4b 之后的项目评估与下一阶段
> 推进方案》整理而成，已经项目所有者批准，**立即生效**。建议完成 tag：`v0.4c-pre-market-stable`。
>
> **协调员派发补充**（与正文同等约束力）：
> 1. 基线核对：pytest 应为 163 passed；tag `v0.4b-data-quality`；
>    文档与代码冲突时以代码为准并先报告；
> 2. 外部调研档案（实现前需重新 smoke test 相关端点）：
>    `docs/research/2026-08-29_data_sources_survey.md`（第一轮）、
>    `docs/research/2026-08-30_data_layer_round2_validation.md`（第二轮）、
>    `docs/review/2026-08-30_gate_ab_review_brief.md`（上轮评审简报，含 §6 遗留问题）；
> 3. 正文 §9 的 D2/D4 Wind 历史回填依赖**用户人工导出文件**
>    （wind_backfill_tsf.csv，Total TSF Flow + Government Bond Financing Flow，
>    ≥60 个月、推荐 120 个月）。文件未就绪时先做全部其他任务，回填任务放最后；
>    若窗口结束时文件仍未就绪，如实输出等待状态，不得用其他来源凑数；
> 4. 正文 §44 列出的外部事实（NBS CPI 页含核心 CPI、Treasury Par Real Yield、
>    Fed H.10、PBOC 社融存量表）实现前必须 endpoint smoke test；
> 5. X1 切换 Treasury primary 前的 overlap check（≥60 共同交易日）是硬性验收项；
> 6. D3 spike 严格 time-box，Stop Rule 生效即停止，不得演变成新爬虫项目；
> 7. 正文 §5.1 的状态修复要求「共享 resolve_signal_status」——这是架构要求：
>    禁止任何报告脚本各自复制状态判断逻辑；
> 8. 网络 integration test 保持 opt-in；全程禁止 silent fallback。

---

# Personal Macro Asset Compass
## v0.4b 之后的项目评估与下一阶段推进方案

**评审基线：** `v0.4b-data-quality` / commit `656d120`  
**评审日期：** 2026-08-30  
**当前测试基线：** 163 passed / 0 failed，另有 6 个 opt-in 网络集成测试  
**用途：** 项目负责人决策 + 原开发窗口/后续 LLM 窗口直接执行  
**核心原则：** 继续坚持“低维护成本 > 数据可追溯 > 解释力 > 稳定性 > 功能丰富度 > 模型复杂度”。

---

# 1. 执行摘要

## 1.1 当前项目性质已经发生变化

项目已经不再处于“搭建工程框架”阶段。

截至 `v0.4b-data-quality`，系统已经具备：

```text
自动/手工数据获取
→ canonical Parquet
→ DuckDB
→ transform
→ signal
→ factor
→ breadth / confidence
→ macro regime
```

同时已经建立：

- append / replace_window / full_refresh 三类更新语义；
- synthetic production isolation；
- WARMUP；
- signal saturation diagnostics；
- as-of/release lag；
- raw snapshot / vintage；
- provider failure isolation；
- deterministic fixture tests。

因此当前主要风险不再是：

> “代码能不能跑”。

而是：

> **关键经济机制是否有足够完整、及时、可长期维护的真实数据支撑。**

---

# 2. 对 v0.4b 的正式验收意见

## 2.1 建议：接受 Gate A/B 交付

原 Gate A 目标：

```text
Core REAL-computable >= 12/15
```

实际：

```text
READY      9
WARMUP     2
PARTIAL    1
MISSING    3
```

虽然形式上未达到 12/15，但本轮应视为：

> **工程验收 PASS，覆盖率 KPI 未完成但原因合理。**

原因：

1. 未使用 synthetic 填充 production；
2. 未缩短 rolling window；
3. 未通过放宽 stale 阈值掩盖数据问题；
4. blocker 已分类；
5. 系统正确输出 `NO_SIGNAL / WARMUP / PARTIAL / MISSING`；
6. 163 个 deterministic tests 全部通过；
7. 当前已首次使用真实数据输出 macro regime。

因此不建议把 V1.2C 判定为失败并反复重做。

---

# 3. 但不建议马上进入原计划 V1.6 + V2

当前状态：

| Factor | READY |
|---|---:|
| Growth | 5 / 5 |
| Inflation | 2 / 3 |
| Domestic | 1 / 4 |
| Global | 1 / 3 |
| Total | 9 / 15 |

真正的问题不是总数 9。

而是：

```text
Domestic = 1/4
Global   = 1/3
```

对于后续 Asset Compass：

- A 股；
- 港股；
- 中国利率债；
- 中国信用债；
- 黄金；
- 人民币；

Domestic / Global 恰恰是核心解释变量。

因此如果现在进入 V2：

> 即使 Asset Engine 工程上成功，其经济信息结构仍然偏科。

---

# 4. 新增一个短版本：v0.4c Pre-Market Stabilization

建议在 V1.6A 之前插入：

# V1.5E / v0.4c — Pre-Market Stabilization

它不是新模型版本。

目标只有：

> **用最低新增维护成本，补齐几个已经非常接近解决的关键经济机制。**

本轮目标：

```text
Growth      5 / 5 READY
Inflation   3 / 3 READY
Domestic   >=3 / 4 READY
Global      3 / 3 READY

Total target:
14 / 15 READY

Minimum acceptable:
13 / 15 READY
AND
Domestic >= 3/4
AND
Global = 3/3
```

唯一允许长期留下 PARTIAL 的 Core Signal：

```text
D3 Excess Liquidity
```

前提是 D1/D2/D4 已经 READY。

---

# 5. v0.4c Task 0 — 修复两个明确的小缺陷

## 5.1 `signal_status.py` WARMUP 状态显示错误

当前：

```text
signal_status.py
D2 / D4 → READY

macro_report.py
D2 / D4 → WARMUP
```

应统一使用同一个状态判断函数。

禁止两个 CLI 各自复制状态逻辑。

建议：

```text
signal_state.py / shared helper
```

形成：

```python
resolve_signal_status(...)
```

所有报告入口复用。

### 验收

D2/D4 在相同 as-of 下：

```text
signal_status
macro_report
signal_quality
```

状态必须一致。

---

# 6. v0.4c Task 1 — 优先修复 I1 Consumer Inflation

## 6.1 当前判断需要修正

当前项目将 I1 视为：

> Core CPI 需要等待 NBS “解读栏目”命中。

但 2026 年 7 月国家统计局正式 CPI 发布页本身已经在主要数据表中直接提供：

```text
“不包括食品和能源”
环比
同比
累计同比
```

因此 I1 不应长期依赖解读文章。

建议 Primary：

```text
NBS CPI monthly release page/table
```

Fallback：

```text
Headline CPI
```

必要时：

```text
Eastmoney / AKShare
```

只作为数据获取 fallback。

## 6.2 数据语义

Core CPI：

```text
exclude food and energy
```

必须与 Headline CPI 使用不同 `series_id`。

禁止因为 Core CPI 获取失败就 silently 将 headline 写入 core series。

Fallback 应发生在 Signal 层：

```text
I1:
Primary input = CN_CORE_CPI_YOY
Fallback input = CN_CPI_YOY
```

并输出：

```text
fallback_used = true
```

### 目标

```text
I1 READY
Inflation = 3/3
```

---

# 7. v0.4c Task 2 — X1 不再单点依赖 FRED

## X1 US 10Y Real Yield

当前：

```text
FRED DFII10
```

endpoint 本身正常，但本机网络存在间歇 timeout。

建议改变 source hierarchy：

```text
Primary:
U.S. Treasury Daily Par Real Yield Curve
10Y

Secondary:
FRED DFII10

Manual:
optional
```

原因：

美国财政部官方 Daily Treasury Rates 页面直接提供：

```text
Daily Treasury Par Real Yield Curve Rates
5Y / 7Y / 10Y / 20Y / 30Y
CSV / XML
```

这样 X1 可以减少对单一 FRED 域名的依赖。

### 注意

Treasury 10Y real yield 与 FRED DFII10 应在切换前做 overlap check。

至少比较：

```text
最近 60 个共同交易日
```

检查：

```text
max abs diff
median abs diff
missing dates
```

如果定义/方法存在差异：

> 不能简单拼接。

需要选定一个长期 canonical definition。

建议：

```text
Treasury = canonical
FRED = validation/fallback
```

或者反过来，但必须固定。

---

# 8. v0.4c Task 3 — X2 Broad USD 做双官方源容错

当前：

```text
FRED DTWEXBGS
```

数据本身仍在正常更新。

但本机网络到 FRED 不稳定。

建议：

```text
Primary:
FRED DTWEXBGS

Fallback:
Federal Reserve Board H.10 daily indexes
```

但需注意：

Federal Reserve Board 已公告 Data Download Program 正处于调整/逐步退役过程。

因此 H.10 DDP 不应成为新的长期唯一依赖。

实现原则：

```text
FRED
→ fail
Fed H.10
→ fail
MANUAL_REQUIRED
```

不要围绕 DDP 建复杂长期架构。

### 目标

```text
X2 READY
Global = 3/3
```

---

# 9. v0.4c Task 4 — D2/D4 不等 9 个月，使用一次性 Wind 历史回填

当前：

```text
D2 Private Credit Impulse = WARMUP
D4 Fiscal Support         = WARMUP
```

原因不是 live source 不通。

而是：

> PBOC 自动链只有有限历史。

这类问题最不应该继续开发复杂爬虫。

对于个人使用者，最低总成本方案是：

# 一次性 Wind Backfill + PBOC 自动增量

建议一次从 Wind 导出：

```text
Total TSF Flow
Government Bond Financing Flow
```

历史长度：

```text
至少 60 个月
推荐 120 个月
```

频率：

```text
monthly
```

建议文件：

```text
wind_backfill_tsf.csv
```

canonical：

```text
series_id
date
value
source=WIND
source_file
import_time
```

一旦历史补齐：

```text
过去历史 = Wind
未来更新 = PBOC
```

生产系统不再要求你每月从 Wind 更新这两条。

这是典型的：

> **一次人工成本换长期自动化。**

### 验收

导入完成后：

```text
D2 READY
D4 READY
Domestic >= 3/4
```

---

# 10. 为什么不建议开发 gov.cn 历史爬虫作为首选

候选方案：

```text
A. gov.cn/PBOC 历史页面深度爬取
B. Wind 一次性回填
C. 等 9 个月自然积累
```

建议：

```text
B > A > C
```

理由：

### B
- 一次性 1–2 小时人工；
- 数据历史完整；
- 不增加长期维护代码；
- 符合项目既定 Wind manual fallback 原则。

### A
- 页面动态；
- URL 结构易变；
- parser 需要长期维护；
- 对一个“一次性历史问题”投入过多工程成本。

### C
- 延迟 V2.5 有效验证；
- 9 个月等待成本远高于一次人工回填。

---

# 11. v0.4c Task 5 — D3 暂不阻塞，但做一个短研究 Spike

当前：

```text
D3 Excess Liquidity = PARTIAL
```

缺：

```text
社融存量腿
```

本轮外部核对发现：

PBOC 官方确实存在：

```text
社会融资规模存量统计表
Aggregate Financing to the Real Economy (Stock)
```

表中包含：

```text
AFRE total stock
Government bonds stock
以及各分项同比增速
```

因此 D3 不能直接定义为：

> “官方无数据源”。

更准确的说法应是：

> **自动发现/稳定抓取当前 PBOC stock table 的工程路线尚未解决。**

建议做一个最多半个任务的 Spike：

### 验证

1. PBOC stock table 历史文件是否可稳定发现；
2. PDF/附件格式跨年份是否一致；
3. 能否构造：

```text
Private TSF Stock
=
AFRE Stock
-
Government Bond Stock
```

4. 能否计算可比 YoY；
5. 统计口径变更是否需要 breakpoint metadata。

### Stop Rule

如果在短 Spike 内不能形成稳定自动源：

> 停止开发。

D3 继续 PARTIAL。

不要让它阻塞 V2。

---

# 12. v0.4c Task 6 — Policy Rate 人工维护进一步降低

当前：

```text
data/manual_series/CN_POLICY_RATE_7D.csv
```

是人工转录利率台阶。

现有 PBOC OMO route 已能抓近期公告。

下一窗口需要检查：

> 当前 live OMO rate 是否已经持久化进 canonical。

如果已经持久化：

```text
新的降息
→ update_sources
→ 自动获取最新 7D reverse repo rate
→ 写 canonical
```

那么人工 policy-rate step 只需要历史 bootstrap，不应每次降息手动追加。

如果目前实现没有自动持久化：

> 增加 step-change persistence。

目标：

```text
正常运行后：
Policy Rate maintenance ≈ 0
```

Manual CSV 只作为：

```text
historical backfill / emergency fallback
```

---

# 13. v0.4c Task 7 — G3 Current Activity 换 live source

当前：

```text
G3 = READY
```

但 OECD Industrial Production / Retail 已约 121 天未更新。

对于一个叫：

```text
Current Activity
```

的信号，四个月延迟在经济意义上不可接受。

因此：

```text
Historical backfill:
OECD

Live:
NBS / Eastmoney / AKShare

Fallback:
OECD
```

优先复用当前已经为：

```text
PMI
PPI
```

建立的 Eastmoney/NBS provider。

不要为 G3 新造一套架构。

### 验收

最新 observation 的 age 应符合中国月度活动数据正常发布时间。

不要通过扩大 `stale_after_days` 来解决。

---

# 14. v0.4c Task 8 — G4/G5 Saturation Review

当前已知：

```text
G4 level
G5 momentum
```

存在贴 ±1 截断边现象。

不要马上重新定参数。

先输出：

```text
24M saturation
60M saturation
raw distribution
pre-clip score distribution
post-clip score distribution
```

建议 Review Trigger：

```text
24M saturation > 25%
OR
60M saturation > 15%
```

该阈值只是工程检查阈值，不是经济理论常数。

若触发 Review：

允许：

```text
MAD
rolling percentile
distribution-based scale
economic neutral point
```

重新校准。

禁止：

```text
用未来资产收益选择 scale
```

### 变更纪律

任何 normalization 修改必须：

1. 在 config 中显式；
2. 输出 before/after；
3. 增加 regression test；
4. 在 CURRENT_STATE 记录；
5. 不改变 Factor 权重。

---

# 15. v0.4c 的真正完成标准

目标不是：

```text
15/15
```

而是：

# Economic Coverage Gate

```text
Growth       5/5
Inflation    3/3
Domestic    >=3/4
Global       3/3
```

因此理想：

```text
14/15 READY
D3 PARTIAL
```

这比：

```text
15/15 但包含脆弱数据源
```

更好。

---

# 16. v0.4c Acceptance Checklist

```text
[ ] signal_status WARMUP 语义修复
[ ] I1 Core CPI 自动来源 READY
[ ] X1 有第二个独立官方 source
[ ] X2 有独立官方 fallback
[ ] Global = 3/3 READY
[ ] D2 Wind backfill 完成
[ ] D4 Wind backfill 完成
[ ] Domestic >= 3/4 READY
[ ] D3 source spike 有明确结论
[ ] Policy Rate 自动持久化评估完成
[ ] G3 live source freshness 改善
[ ] G4/G5 saturation review 完成
[ ] synthetic production isolation 保持
[ ] full pytest PASS
[ ] real-data macro_report 可运行
[ ] CURRENT_STATE 更新
```

---

# 17. 建议 Git checkpoint

完成后：

```text
tag:
v0.4c-pre-market-stable
```

当前不要使用：

```text
v0.5
```

因为 Asset Compass 尚未开发。

---

# 18. 完成 v0.4c 后，正式进入 V1.6A

下一窗口：

# Window D1 — Market Confirmation

只做市场层。

不要同时做 Asset Compass。

---

# 19. V1.6A 的输入

六个市场确认信号：

```text
M1 CSI300
M2 Hang Seng Index
M3 China 10Y Government Yield
M4 AAA Credit Spread
M5 USD/CNY
M6 Industrial Commodity / Copper
```

其中当前已有基础：

```text
ChinaBond adapter
USD/CNY
AKShare
Eastmoney adapter
```

因此优先复用。

---

# 20. V1.6A 第一阶段不是写 divergence engine，而是 Market Data Readiness

先做：

```text
Market Data Matrix
```

| Market Signal | Provider | History | Frequency | Current Freshness | READY? |
|---|---|---:|---|---|---|

最低：

```text
5 / 6 real READY
```

推荐：

```text
6 / 6
```

禁止 synthetic 进入 production Market Confirmation。

---

# 21. V1.6A Market Signal 设计

首版无需复杂模型。

统一计算：

```text
1M move
3M move
6M trend
rolling percentile
```

但必须按经济方向统一。

例如：

```text
CSI300 ↑ = positive risk signal

China 10Y yield ↓
不能简单视为 positive
必须与 Growth/Bond context 对齐

AAA spread ↑ = negative credit signal

USD/CNY ↑ = CNY weaker / China financial condition less favorable
```

Market layer 只表示：

> 市场价格方向。

不要让它反向修改 Fundamental Score。

---

# 22. V1.6A 的核心产出：Divergence

至少：

```text
CONFIRMED_POSITIVE
CONFIRMED_NEGATIVE
POSITIVE_MACRO_DIVERGENCE
NEGATIVE_MACRO_DIVERGENCE
MIXED
```

并保留：

```text
macro direction
market direction
agreement
confidence
```

不要把 Divergence 直接翻译成：

```text
BUY / SELL
```

---

# 23. V1.6A 完成后再进入 V2

V2 单独开窗口。

原因：

> Asset Mapping 是整个项目中第一个真正接近“投资决策”的模块，应给予单独研究与验收。

---

# 24. V2 开发前增加一个只读研究任务 R2

建议在 V1.6A 开发期间并行启动：

# R2 — Asset Prior Matrix Research

这是只读调研窗口，不修改仓库。

目标：

对：

```text
CN_EQUITY
HK_EQUITY
CN_GOV_BOND
CN_CREDIT
GOLD
INDUSTRIAL_COMMODITY
CNY
```

逐资产研究：

```text
主要宏观驱动
方向
理论机制
中国市场特异性
历史稳定性
可能的 regime dependence
```

输出不是：

```text
精确最优 beta
```

而是：

```text
sign
importance tier
reasonable prior range
evidence
```

例如：

```text
CN_EQUITY

Growth:
sign +
importance HIGH

Private Credit:
sign +
importance HIGH

Excess Liquidity:
sign +
importance MEDIUM/HIGH

Global Financial:
sign +
importance MEDIUM
```

---

# 25. R2 研究交付标准

每个资产至少包含：

```text
Driver
Expected Sign
Importance
Economic Mechanism
Supporting Research
Contradictory Evidence
Regime Dependence
Confidence
```

优先：

- 学术论文；
- BIS / IMF / central bank；
- 国内大型券商资产配置研究；
- 可复现统计研究。

禁止：

- 博客观点直接成为权重依据；
- 单一年份相关性决定长期 beta；
- 根据本项目历史回测反推先验。

---

# 26. V2 Asset Compass

只有以下 Gate 完成后开始：

```text
v0.4c Economic Coverage PASS
+
V1.6A Market Confirmation PASS
+
R2 Asset Prior Matrix completed
```

然后才实现：

```text
AssetScore =
Σ beta * MacroFactor
```

---

# 27. V2 的输出纪律

每个 Asset 必须输出：

```text
Score
View
1M change
3M change
Factor contribution
Signal contribution
Market confirmation
Confidence
```

必须可追溯：

```text
Asset
→ Factor
→ Signal
→ Raw Series
→ Provider
```

---

# 28. V2 后立即 V2.5，不先做 UI

这条继续保持。

原因：

Asset Compass 一旦有可视化，很容易产生：

> “模型看起来很合理，所以模型有效”

的认知偏差。

因此：

```text
V2 Asset
→ V2.5 Validation
→ V3 UI
```

不变。

---

# 29. V2.5 前应提前准备 Historical Backfill

这是当前项目下一阶段非常重要、但容易被忽略的问题。

当前部分真实信号历史仅约：

```text
30 months
```

例如 G2/G4。

30 个月不足以可靠验证多个宏观 regime。

因此从 v0.4c 开始，就应建立：

# Historical Coverage Matrix

对每个 Core Signal 记录：

```text
earliest observation
comparable-history start
source
breakpoints
revision risk
minimum validation start
```

---

# 30. 历史回填原则

不要为了“全自动”拒绝 Wind。

对历史数据：

> 一次性人工导出往往比长期维护一个脆弱爬虫更便宜。

适合 Wind 一次性 backfill：

```text
TSF
Government Bond Financing
PMI components
Property history
Core CPI if public comparable history不足
Credit spread
某些资产指数
```

未来 live update 继续使用公开源。

---

# 31. 历史验证建议最低样本

理想目标：

```text
2012–present
```

如果不可比：

```text
2015–present
```

比强行拼接更好。

每个 series 应记录：

```text
breakpoint
methodology change
base-year change
```

不要偷偷拼成一条“连续一致”的历史。

---

# 32. V2.5 增加 Information Increment Test

除了：

```text
forward returns
score bucket
regime analysis
rolling beta
weight robustness
```

增加：

# Leave-One-Mechanism-Out

例如 Growth：

```text
Full Growth
Without CLI
Without PMI Orders
Without Hard Activity
Without Property
Without Export
```

观察：

```text
Factor stability
Asset-score stability
Forward-return separation
```

目的：

> 找出长期没有贡献独立信息、但增加维护成本的 Signal。

如果一个 signal：

```text
维护成本高
+
增量信息弱
```

应考虑：

```text
Core → Diagnostic
```

这与个人轻量化目标高度一致。

---

# 33. Structural Risk 继续后移

建议：

```text
V2.6 Structural Risk
```

放在：

```text
V2.5 后
V3 前
```

原因：

- 不参与 Asset Score；
- BIS 数据为季度；
- 不应该阻塞主线；
- 适合独立实现。

---

# 34. synthetic fixture 的最终治理决策

当前已经完成 production isolation。

因此不需要删除 fixture。

正式决策：

```text
Synthetic fixtures 永久保留
```

用途：

```text
unit test
integration test
edge-case test
```

但：

```text
production default = reject synthetic
```

这已经足够。

不再开发“自动退役 fixture”。

这样减少无价值工作。

---

# 35. 风险优先级重新排序

## Risk 1 — 数据源网络/域名单点依赖

优先：

```text
关键 series 至少有一个独立 fallback
```

但不要每条都有三个 source。

目标是：

> Critical Core Signal 有 2 条可用路径。

---

## Risk 2 — 历史样本不足

这是 V2.5 前最大的模型风险。

解决：

```text
一次性 backfill
+
methodology metadata
```

---

## Risk 3 — 先验模型未经验证

当前允许。

不要提前根据收益调参。

统一在 V2.5 处理。

---

## Risk 4 — 数据 revision

已有：

```text
asof
snapshot
full_refresh
```

继续积累。

这是正确路线。

---

## Risk 5 — LLM 继续扩需求

仍然通过：

```text
MASTER_SPEC
CURRENT_STATE
TASK SPEC
Git checkpoint
```

控制。

---

# 36. 推荐的新版路线图

```text
DONE
────────────────────────
V0 / V1
V1.2
V1.3 / V1.5A
V1.5B / V1.5C
V1.2C / V1.5D
tag v0.4b


NEXT
────────────────────────

v0.4c
Pre-Market Stabilization
│
├─ I1 Core CPI
├─ X1 Treasury fallback
├─ X2 Fed fallback
├─ D2/D4 Wind backfill
├─ D3 source spike
├─ G3 freshness
├─ Policy-rate persistence
└─ saturation review

          ↓

V1.6A
Market Confirmation
          ↓

R2 research
Asset Prior Matrix
          ↓

V2
Asset Compass
          ↓

V2.5
Historical Validation
          ↓

V2.6
Structural Risk
          ↓

V3
Dashboard
          ↓

V4
Cloud
```

---

# 37. 下一开发窗口建议

我建议仍可使用**当前原开发窗口**完成 v0.4c。

原因：

- 它刚完成数据质量专项；
- 熟悉 provider；
- 熟悉 signal status；
- 熟悉 CURRENT_STATE blockers；
- v0.4c 本质是上轮收尾，不是新的 subsystem。

完成 v0.4c 后：

> 再切新窗口进入 V1.6A。

---

# 38. 给原开发窗口的直接 Prompt

```text
继续当前 Personal Macro Asset Compass 项目。

当前 tag：
v0.4b-data-quality

本轮不要进入 V1.6 / V2。

请执行一个短版本：

V1.5E / v0.4c Pre-Market Stabilization

目标不是继续追求形式上的 15/15，而是让关键经济模块达到可进入 Asset 主线的覆盖质量。

目标 Gate：

Growth = 5/5 READY
Inflation = 3/3 READY
Domestic >= 3/4 READY
Global = 3/3 READY

理想总覆盖：
14/15 READY

允许：
D3 Excess Liquidity 保持 PARTIAL，
前提是 D1/D2/D4 READY。

首先重新运行：
python -m pytest
python scripts/signal_status.py
python scripts/signal_quality.py
python scripts/macro_report.py

然后按优先顺序执行：

P0：
1. 修复 signal_status 与 macro_report 对 WARMUP 状态显示不一致。
2. 修复 I1：
   国家统计局正式 CPI 发布页本身包含“不包括食品和能源”的核心 CPI 数据，
   不再仅等待 NBS 解读栏目。
3. X1：
   增加 U.S. Treasury Daily Par Real Yield Curve 10Y 官方源，
   与 FRED DFII10 做 overlap check，并建立明确 primary/fallback。
4. X2：
   保留 FRED DTWEXBGS，增加 Federal Reserve H.10 official fallback，
   但考虑 DDP 正在调整，不把 H.10 DDP 设计成新的唯一长期依赖。

P1：
5. 使用 Wind 一次性回填至少 60 个月、推荐 120 个月：
   - Total TSF Flow
   - Government Bond Financing Flow
   之后继续使用现有 PBOC live update。
   目标让 D2/D4 立即从 WARMUP → READY。
6. 对 D3 做一个 time-boxed source spike：
   验证 PBOC “社会融资规模存量统计表”是否可形成稳定 source。
   若不能快速稳定实现，停止，D3 保持 PARTIAL，不阻塞后续。
7. 检查 CN_POLICY_RATE_7D：
   如果 PBOC OMO live rate 已抓取，应确保新政策利率自动持久化，
   manual CSV 只作为历史/bootstrap fallback。
8. 将 G3 live source 从滞后的 OECD IP/Retail 优先切换为现有 NBS/Eastmoney/AKShare route；
   OECD 保留 historical/fallback。

P2：
9. 对 G4 level、G5 momentum 输出完整 saturation diagnostics。
   只有存在明显长期饱和时才调整 normalization。
   禁止使用未来资产收益调 scale。

严格禁止：
- V1.6
- Asset Compass
- UI
- Cloud
- ML
- synthetic production
- 缩短 rolling window
- silent fallback
- 用资产未来收益调整 normalization/factor weight

完成后必须运行完整 pytest 和 real-data smoke test。

最终输出：
1. baseline
2. files changed
3. 15 Core Signal status matrix
4. provider/fallback matrix
5. Growth/Inflation/Domestic/Global coverage
6. saturation review
7. tests
8. acceptance checklist
9. known issues
10. CURRENT_STATE changes
11. suggested commit
12. suggested tag = v0.4c-pre-market-stable
13. next task = V1.6A Market Confirmation

完成后停止，不继续下一版本。
```

---

# 39. v0.4c 完成后的用户人工动作

预计只需要一次：

## Wind Backfill

导出：

```text
Total TSF Flow
Government Bond Financing Flow
```

推荐：

```text
2015-01 至今
```

如果方便：

```text
2010-01 至今
```

更好。

不要为了这一步导出几十个指标。

本次只解决 D2/D4。

---

# 40. 是否现在顺手回填 D3

如果 Wind 中非常容易同时取得：

```text
Total TSF Stock
Government Bond Stock
```

那么建议顺手导出。

因为可以构造：

```text
Private TSF Stock
=
Total TSF Stock
-
Government Bond Stock
```

这样 D3 可能直接解决。

但这是：

> Opportunistic Backfill

不是强制任务。

如果 Wind 导出麻烦：

> 先不做。

---

# 41. 项目完成度重新评估

以 `v0.4b` 为基线：

| 维度 | 当前 |
|---|---:|
| Engineering Foundation | 90% |
| Data Architecture | 90% |
| Core Signal Engine | 90% |
| Real Data Coverage | 65–70% |
| Macro Model Operational | 65% |
| Market Confirmation | 0% |
| Asset Mapping | 0% |
| Empirical Validation | 0–10% |
| Local Product/UI | 0% |
| Cloud | 0% |

如果按最终“可个人实际使用”的产品计算：

> 当前大约完成 **45% 左右**。

这不是坏事。

前 45% 包含的是最重要的：

> 数据和模型骨架。

后面的代码量未必比前面更大，但验证要求会更高。

---

# 42. 当前最重要的项目管理判断

不要再把：

```text
功能数量
```

当作进度。

以后只看四个 Gate：

## GATE 1 — Economic Coverage

```text
关键机制是否有真实数据？
```

## GATE 2 — Explainability

```text
每个结论能否回到 raw source？
```

## GATE 3 — Empirical Value

```text
历史上是否真的提供信息？
```

## GATE 4 — Maintenance Cost

```text
一个月需要用户手工做多少工作？
```

最终一个 Signal 如果：

```text
预测价值一般
+
数据源脆弱
+
需要人工维护
```

即使经济理论很好：

> 也应该删掉。

---

# 43. 最终推荐

现在不要进入 V1.6。

先用原窗口完成一个非常收敛的：

> **v0.4c Pre-Market Stabilization**

重点只有：

```text
I1
X1
X2
D2
D4
G3 freshness
几个小质量问题
```

并通过一次 Wind backfill 把 Domestic 从 1/4 提升至至少 3/4。

完成后，项目就不再需要继续纠结 Core 数据覆盖。

届时：

> **冻结 Fundamental Core，正式进入 Market → Asset → Validation。**

这是当前最优的推进路径。

---

# 44. 本文使用的外部核对

除项目交付简报外，本次评估额外核对了：

1. 国家统计局 2026 年 7 月 CPI 正式发布页：正式表格已包含“扣除食品和能源”的核心 CPI 环比/同比；
2. FRED DFII10：2026 年 8 月仍正常日频更新；
3. FRED DTWEXBGS：2026 年 8 月仍正常更新；
4. U.S. Treasury Daily Treasury Rates：官方提供 Daily Par Real Yield Curve 及 CSV/XML 下载；
5. Federal Reserve H.10：官方仍提供 dollar index 数据下载，但 DDP 已公告未来调整；
6. PBOC 官方“社会融资规模存量统计表”存在，包含 AFRE 总存量、政府债券存量及同比增速，因此 D3 的问题更准确地属于“稳定自动抓取尚未解决”，而不是“官方无数据”。

这些外部事实应由开发窗口在实际实现前再次做 endpoint smoke test。
