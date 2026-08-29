# Task — V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate（Gate A/B）

> **来源与状态**：本任务书由外部项目负责人 2026-08-29 评审后签发的任务执行框架整理而成，
> 已经项目所有者批准，**立即生效**。它修订了 MASTER SPEC §15 的版本顺序（见该节批注）：
> V1.6 拆分为 V1.6A（Market Confirmation），Structural Risk 后移为 V2.6。
> 建议完成 tag：`v0.4b-data-quality`。
>
> **协调员派发补充**（与正文同等约束力）：
> 1. 基线核对：pytest 应为 137 passed；文档与代码冲突时以代码为准并先报告；
> 2. 正文 §3.1 提到的「最新项目评审简报」实际路径为
>    `docs/review/2026-08-29_project_review_brief.md`；
> 3. 数据源端点验证状态以 `docs/research/2026-08-29_data_sources_survey.md` 为基础，
>    其中 VERIFIED 条目协调员已抽验 3/3；UNVERIFIED 条目（TSF/政府债券融资）
>    本窗口实现时必须先实测再入库，禁止照抄调研结论；
> 4. NBS 新闻稿解析必须配离线 fixture test（正文 §14 已要求）；
>    NBS 数据门户 WAF 403，不得尝试直连 easyquery API；
> 5. AKShare 未安装属环境 blocker，按正文 §16 的 blocker 分类如实记录；
> 6. 网络 integration test 保持 opt-in（`-m network`），不得污染核心 pytest；
> 7. 若 Gate A 覆盖目标确有无法达成的项，按 §16 说明 blocker 类型后如实交付，
>    不得为达标放松任何禁止项——宁可 11/15 + blocker 说明，不要 12/15 里有水分。

---

# Personal Macro Asset Compass
## 下一阶段任务执行框架：V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate

**用途：** 直接交给当前原开发窗口评估并推进  
**当前基线：** `v0.4-macro-engine` 已完成并冻结  
**当前测试基线：** `137 passed / 0 failed`  
**当前核心问题：** 15 个 Core Fundamental Signals 中仅 3 个完整可计算、2 个 PARTIAL、10 个缺失；当前 `NO_SIGNAL` 主要由真实数据覆盖不足导致，而不是引擎缺陷。

---

# 1. 本轮唯一目标

本轮不要按旧计划直接进入 V1.6 + V2。

只完成两个连续 Gate：

```text
Gate A
V1.2C Data Coverage Hardening
        ↓
Gate B
V1.5D Signal Quality Gate
```

完成两个 Gate 后，才进入：

```text
V1.6A Market Confirmation
→ V2 Asset Compass
```

原则：**先让现有 Macro Engine 在真实数据上可靠运行，再增加资产映射。**

---

# 2. 本轮开发边界

## 允许修改

重点允许：

```text
src/macro_compass/data_sources/
config/data_sources.yaml
数据更新 orchestration
canonical update policy
source metadata
freshness metadata
status/report scripts
production/synthetic isolation
必要的 tests/fixtures
```

如确有必要，可以做最小范围调整：

```text
Signal status handling
Freshness status
WARMUP status
diagnostic output
```

## 默认冻结

除非明确发现 bug，不重写：

```text
V1 ingestion
Canonical schema 核心含义
Raw archive
DuckDB rebuild
Transform Engine
Signal Engine 核心公式
Macro Factor Engine 权重
Regime 逻辑
```

## 明确禁止

```text
V1.6 Market Confirmation
Asset Compass
Structural Risk production implementation
Streamlit
Cloud
ML / HMM
组合优化
历史收益调参
为了提高覆盖缩短 rolling window
为了避免 STALE 随意放宽阈值
用 synthetic 填 production 缺口
silent fallback
```

---

# 3. 第一阶段：Assessment Only

在修改代码前先做完整评估。

## 3.1 必须读取

```text
README.md
docs/00_MASTER_SPEC.md
docs/01_CURRENT_STATE.md
docs/02_ARCHITECTURE.md
docs/research/2026-08-29_data_sources_survey.md
最新项目评审简报
相关 data source adapter
Signal Engine
Macro Factor Engine
```

## 3.2 建立 baseline

运行：

```bash
python -m pytest
python scripts/signal_status.py
python scripts/macro_report.py
python scripts/update_sources.py --dry-run
```

若仓库命令不同，以实际代码为准并说明。

记录：

```text
Test Count
READY Core Signals
PARTIAL Core Signals
MISSING Core Signals
Current Factor Coverage
Current Regime
Current Provider Status
```

## 3.3 生成 Data Gap Matrix

必须覆盖全部 15 Core Signals：

| Signal | Required Inputs | Current Status | Current Provider | Problem | Recommended Fix |
|---|---|---|---|---|---|

至少回答：

1. 哪些缺口可通过已验证 endpoint 直接补齐？
2. 哪些序列应该更换 live source，而不是只增加 fallback？
3. 现有 Adapter 是否支持 `append / replace_window / full_refresh`？
4. synthetic 与 real 是否存在 production 混用风险？
5. freshness 是否支持 release lag / release calendar？
6. 哪些 Signal 出现 normalization saturation？
7. 达到真实覆盖 Gate 还缺哪些 series？

## 3.4 Assessment Stop Condition

修改前先输出：

```text
## Baseline
## Data Gap Matrix
## Proposed Changes
## Files Expected to Change
## Risks
## Gate Feasibility
```

如果发现 baseline pytest 失败、仓库状态与评审简报重大不一致、Canonical 无法支撑新更新语义等严重 blocker，则先停下来说明。

否则直接继续执行 Gate A，不需要额外等待确认。

---

# 4. Gate A — V1.2C Data Coverage Hardening

## 4.1 Gate A 成功标准

最终最低真实覆盖：

```text
Core REAL-computable >= 12 / 15

Growth >= 4 / 5
Inflation >= 2 / 3
Domestic >= 3 / 4
Global = 3 / 3
```

`REAL-computable` 定义：

- 输入来自真实公开数据或 Wind manual；
- 不使用 synthetic；
- 满足 minimum history；
- 不处于 MISSING；
- 不靠 silent fallback；
- transformation 可以真实计算。

允许 WARMUP / PARTIAL，但不能伪装 READY。

---

# 5. Gate A — 数据修复优先级

## P0：Global Financial Conditions

### X1 US 10Y Real Yield

Primary：FRED。增加/验证 `fredgraph CSV` fallback。

目标：`X1 READY`。

### X2 Broad USD

同样：

```text
FRED normal path
→ fail
fredgraph CSV
```

目标：`X2 READY`。

### X3 ANFCI

优先复用 FRED 或 Chicago Fed 直链 CSV，不创建重复架构。

目标：`X3 READY`。

---

# 6. Gate A — Inflation

## I1 Consumer Inflation

优先 Core CPI；若自动获取长期不稳定，Headline CPI 可作为正式 fallback。

如果历史长度不足：

```text
status = WARMUP
score = null
```

禁止 `window = min(required, available)`。

## I2 PPI

优先 NBS / AKShare。要求明确口径、original_source 和历史回填。

目标：`I2 READY`。

## I3 Cost Pressure

输入：

```text
PMI Input Price
+
GSCPI
```

GSCPI 必须支持：

```yaml
update_policy:
  mode: full_refresh
```

每次更新保存 `asof_date`，Raw snapshot 不覆盖旧 vintage。

如果 PMI Input Price 暂时拿不到，允许 GSCPI 单腿运行，但必须显式 `coverage < 1`。

---

# 7. Gate A — Growth

## G2 PMI New Orders

优先 NBS 新闻稿 parser 或 AKShare。

要求：

- 不用 headline PMI 替代；
- AKShare 必须记录 original_source；
- parser 使用离线 fixture test。

## G3 Hard Activity

当前 OECD IP/Retail 若 live 时滞过长：

```text
Historical backfill = OECD
Live source = NBS / AKShare
```

不要通过放宽 stale 阈值解决。

## G4 Property Demand

输入：

```text
商品房销售面积
商品房销售额
```

注意 NBS 常见是 YTD 累计值。必须先做：

```text
YTD cumulative
→ single-period / comparable growth
```

增加 fixture test 覆盖：

- 年初重置；
- 跨月差分；
- 缺月；
- 修订；
- 累计值异常下降。

## G5 Export

当前已有真实数据时不重写结构，只检查 freshness、history、saturation。

---

# 8. Gate A — Domestic Financial

## D1 Funding Condition

核心：

```text
DR007 - Policy Rate
```

DR007：

```text
Live = ChinaMoney
Historical backfill = AKShare / Wind
```

因为 ChinaMoney 静态 CSV 仅滚动保留近期数据。

Policy Rate 必须配置化，不写死在代码。

## D2 Private Credit Impulse

需要：

```text
Total TSF
Government Bond Financing
```

核心：

```text
Private TSF = Total TSF - Government Bond Financing
```

优先 PBOC，AKShare fallback。不要把易变化 PBOC URL 硬编码进核心逻辑。

## D3 Excess Liquidity

需要：

```text
M2 YoY
Private TSF YoY
```

缺一条腿：

```text
PARTIAL
score = null
```

禁止补 0。

## D4 Fiscal Support

需要 Government Bond Financing。

与 D2 共用输入但经济机制不同：

```text
D2 = private credit
D4 = fiscal financing
```

二者必须保留独立解释。

---

# 9. Gate A — Update Policy

如现有 source architecture 只有 append，必须扩展为：

```text
append
replace_window
full_refresh
```

建议配置：

```yaml
update_policy:
  mode: append
```

或：

```yaml
update_policy:
  mode: replace_window
  revision_periods: 3
```

或：

```yaml
update_policy:
  mode: full_refresh
```

`full_refresh` 至少用于 GSCPI。

---

# 10. Gate A — Synthetic Production Isolation

必须正式隔离 REAL / SYNTHETIC。

生产命令默认：

```text
allow_synthetic = false
```

至少以下入口不得默认读取 synthetic：

```text
calculate_signals
signal_status
macro_report
future asset calculation
```

测试时才允许 `--allow-synthetic`。

Fixture 不删除；只禁止其进入 production calculation。

---

# 11. Gate A — Snapshot / Vintage

从本轮开始，每次真实 fetch 至少保留：

```text
asof_date
provider
original_source
fetch_time
```

对 GSCPI、OECD CLI 等可修订序列优先保留 raw snapshot。

目标：从系统上线开始积累自己的 vintage history。

---

# 12. Gate A — Freshness Metadata

本轮只准备 metadata，不大改 Signal Engine。

建议：

```yaml
freshness:
  frequency: monthly
  expected_release_lag_days: 20
  acceptable_delay_days: 15
  stale_after_days: 60
```

如有官方 release calendar：

```yaml
release_calendar:
  provider: oecd
```

优先级：

```text
official release calendar
>
series-specific expected lag
>
frequency default
```

禁止根据异常长的历史间隔自动不断放宽 stale 阈值。

---

# 13. Gate A — Status Output

每个 Core Signal 必须显示：

```text
Signal ID
READY / PARTIAL / WARMUP / MISSING
Inputs
Provider
Latest Observation
Freshness
History Length
Synthetic? yes/no
```

继续输出：

```text
data_status.csv
manual_fetch_required.csv
signal_status report
```

---

# 14. Gate A — 测试要求

必须增加 deterministic tests，至少覆盖：

### Provider
- FRED CSV fallback parser
- ChinaMoney DR007 parser
- NBS/AKShare mapping
- GSCPI full refresh
- ChinaBond replacement endpoint

### Data semantics
- cumulative-to-period conversion
- revision overwrite behavior
- duplicate prevention
- real/synthetic isolation
- fallback status
- network failure isolation

网络 integration test 继续 opt-in，不污染核心 pytest。

---

# 15. Gate A — Smoke Test

完成后实际运行：

```bash
python -m pytest
python scripts/update_sources.py
python scripts/signal_status.py
python scripts/macro_report.py
```

若生产网络不允许完整 update：

- 不伪造；
- 输出实际失败 provider；
- 证明 fallback/status 正常。

---

# 16. Gate A — Acceptance Checklist

逐项 PASS/FAIL：

```text
[ ] Core REAL-computable >= 12/15
[ ] Growth >= 4/5
[ ] Inflation >= 2/3
[ ] Domestic >= 3/4
[ ] Global = 3/3
[ ] synthetic not used in production
[ ] append supported
[ ] replace_window supported
[ ] full_refresh supported
[ ] provider failures isolated
[ ] no silent fallback
[ ] no rolling-window shrink
[ ] DuckDB rebuild still works
[ ] full pytest PASS
```

未达到覆盖 Gate，不得声称 V1.2C 完成。

必须区分 blocker 类型：

```text
code blocker
network blocker
source blocker
history warmup
```

---

# 17. Gate B — V1.5D Signal Quality Gate

只有 Gate A 完成后执行。

这是一个小型质量版本，不新增经济机制。

## 17.1 WARMUP

正式增加：

```text
WARMUP
```

适用于：有真实数据但 minimum_history 未达到。

示例：

```text
Available = 36
Required = 60
Status = WARMUP
Score = null
```

与 MISSING / PARTIAL / STALE 区分。

## 17.2 Saturation Diagnostics

对所有 Core Signal 计算：

```text
saturation_ratio_24m
saturation_ratio_60m
```

定义：`|score| >= 0.95` 的比例。

例如：

```text
G5 Export
24M saturation = 46%
60M saturation = 31%
STATUS = SCALE_SATURATED
```

## 17.3 Normalization Review

允许依据：

```text
信号自身历史分布
经济自然锚点
robust statistics
```

修正 normalization scale / percentile / robust z-score 参数。

禁止依据未来资产收益调 scale。

## 17.4 Composite Completeness

每个 composite 必须输出：

```text
available inputs
required inputs
coverage
```

是否允许单腿计算由 Signal Registry 决定，不在代码里猜。

## 17.5 As-of Consistency

检查宏观快照是否使用了当时尚未发布的数据。

至少考虑：

```text
observation_date
release_date / known lag
asof_date
```

release_date 缺失时使用配置 expected lag，不假设 observation_date 当天可知。

## 17.6 Quality Report

新增或扩展：

```bash
python scripts/signal_quality.py
```

输出：

```text
Signal
Status
History
Freshness
Coverage
24M Saturation
60M Saturation
Normalization
Warnings
```

---

# 18. Gate B — Acceptance

```text
[ ] WARMUP implemented
[ ] no adaptive rolling-window shrink
[ ] saturation diagnostics available
[ ] no unexplained long-term saturation
[ ] composite coverage explicit
[ ] release/as-of semantics documented
[ ] all Core Signals have explainable status
[ ] full pytest PASS
```

---

# 19. Gate B 完成后的 Stop Point

不要继续开发 V1.6。

完成后：

1. 更新 `docs/01_CURRENT_STATE.md`
2. 更新 README
3. 更新必要的数据源研究记录
4. 输出真实 Core Coverage
5. 输出 remaining manual-required
6. 给出 Git commit
7. 建议 tag：`v0.4b-data-quality`
8. 明确下一任务：`V1.6A Market Confirmation`
9. 停止

---

# 20. 后续主线规划

建议更新为：

```text
V1.2C Data Coverage Hardening
→ V1.5D Signal Quality Gate
→ V1.6A Market Confirmation
→ V2 Asset Compass
→ V2.5 Historical Validation
→ V2.6 Structural Risk
→ V3 Dashboard
→ V4 Cloud
```

Structural Risk 后移，因为它不进入短期 Asset Score，不应因 BIS provider 阻塞 V2。

Production Structural Risk 没有真实数据时输出 `NO_SIGNAL`，不要 synthetic 占位。

---

# 21. V2.5 未来新增验证要求

除 Forward Return / Score Bucket / Regime / Rolling Beta / Weight Robustness 外，增加：

## Information Increment Test

对 Core Mechanism 做 leave-one-out：

```text
Full Factor
vs Without CLI
vs Without Property
vs Without Export
...
```

目的不是优化权重，而是判断某个长期维护的数据源是否真的贡献独立信息。

如果长期没有独立贡献，后续可以从 Core 降级为 diagnostic，以继续降低维护成本。

---

# 22. 原窗口最终回复格式

```text
## 1. Baseline
- pytest
- current coverage
- current regime

## 2. Assessment
- Data Gap Matrix
- source problems
- semantic problems
- architecture impact

## 3. V1.2C Implementation
- files changed
- providers added/fixed
- update policies
- synthetic isolation
- freshness metadata

## 4. Real Data Coverage
- 15 Core Signals
- READY/PARTIAL/WARMUP/MISSING
- provider
- history length

## 5. V1.5D Signal Quality
- saturation
- warmup
- composite coverage
- as-of semantics

## 6. Tests
- pytest result
- integration result
- actual failed endpoints

## 7. Acceptance Checklist
PASS / FAIL each item

## 8. Known Issues

## 9. Updated Docs

## 10. Git
- commit
- recommended tag

## 11. Next Task
V1.6A Market Confirmation

不要开始下一版本。
```

---

# 23. 可直接发送给原开发窗口的启动指令

```text
你继续负责 Personal Macro Asset Compass，但当前不要按旧计划进入 V1.6 + V2。

根据最新项目评审，当前工程链路已经完整，主要瓶颈已经变成真实数据覆盖与数据语义。

请将本轮工作拆成两个连续 Gate：

Gate A：V1.2C Data Coverage Hardening
Gate B：V1.5D Signal Quality Gate

先阅读本任务书，并重新读取：
README.md
docs/00_MASTER_SPEC.md
docs/01_CURRENT_STATE.md
docs/02_ARCHITECTURE.md
docs/research/2026-08-29_data_sources_survey.md

第一阶段先 Assessment Only：
- 运行完整 baseline
- 生成 15 Core Signals Data Gap Matrix
- 评估 proposed changes
- 检查仓库实际状态与评审简报是否一致

如果 baseline 和架构没有严重 blocker，则直接继续完成 Gate A 和 Gate B，不需要等待额外确认。

本轮严禁：
- V1.6
- Asset Compass
- Structural Risk production
- UI
- Cloud
- ML
- 用 synthetic 填 production 数据
- 为提高覆盖缩短 rolling window
- 为避免 stale 随意放宽阈值
- 用资产未来收益调整 score scale

最终必须达到或明确说明为什么无法达到：

Core REAL-computable >= 12/15
Growth >= 4/5
Inflation >= 2/3
Domestic >= 3/4
Global = 3/3

并完成：
- update policy: append / replace_window / full_refresh
- synthetic production isolation
- WARMUP
- saturation diagnostics
- freshness/release metadata
- complete pytest
- real-data smoke test
- CURRENT_STATE 更新
- Git checkpoint

完成后停在 V1.6A 之前，不要继续下一版本。
```
