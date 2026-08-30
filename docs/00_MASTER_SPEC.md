# Personal Macro Asset Compass — MASTER SPEC

> 本文件是项目长期有效的“项目宪法”。新 LLM 窗口必须阅读，但不得擅自修改核心原则。

## 1. 项目定位

Personal Macro Asset Compass 是一个**个人使用、本地优先、低维护、可解释**的宏观资产配置辅助系统。

核心任务：

1. 自动获取主要宏观与市场数据；
2. 将原始数据压缩为少量、彼此尽量独立的经济机制信号；
3. 形成宏观状态；
4. 监测市场是否确认宏观状态；
5. 输出对大类资产的宏观顺风/逆风指引；
6. 保持所有结论可追溯到原始数据。

项目不是：

- Wind/Bloomberg 仿制品；
- 高频量化平台；
- 自动交易系统；
- 个股选股系统；
- 黑箱 AI 预测系统；
- 自动决定仓位的组合优化器。

## 2. 最高优先级

长期开发排序：

> 低人工维护成本 > 数据可追溯性 > 模型解释力 > 稳定性 > 功能丰富度 > 模型复杂度

新增设计如果显著增加维护成本但不能带来新的独立信息机制，应拒绝。

## 3. 核心模型

固定为：

- 15 个 Core Fundamental Signals
- 6 个 Market Confirmation Signals
- 3 个 Structural Risk Signals

新增 Core Signal 必须证明它代表新的经济机制，而不是已有信号的重复表达。

## 4. Fundamental 与 Market 隔离

禁止：

```text
股市上涨
→ Growth Score 上升
→ 模型因此继续看多股市
```

市场价格只属于 Market Confirmation 层，不得反向修改 Fundamental Score。

## 5. 15 个 Core Fundamental Signals

### Growth Pulse
- G1 China CLI
- G2 PMI New Orders
- G3 Hard Activity Composite：工业增加值 + 社零
- G4 Property Demand Composite：商品房销售面积 + 销售额
- G5 Export Demand：出口同比

### Inflation Pulse
- I1 Consumer Inflation：Core CPI 优先，Headline CPI 可 fallback
- I2 Industrial Inflation：PPI
- I3 Cost Pressure Composite：PMI Input Price + GSCPI

### Domestic Financial / Policy
- D1 Funding Condition：DR007 - Policy Rate
- D2 Private Credit Impulse：Total TSF - Government Bond Financing
- D3 Excess Liquidity：M2 YoY - Private TSF YoY
- D4 Fiscal Support：Government Bond Financing impulse

### Global Financial Conditions
- X1 US 10Y Real Yield
- X2 Broad USD
- X3 ANFCI

## 6. 6 个 Market Confirmation Signals

- M1 CSI 300
- M2 Hang Seng Index
- M3 China 10Y Government Yield
- M4 AAA Credit Spread
- M5 USD/CNY
- M6 Industrial Commodity / Copper proxy

## 7. 3 个 Structural Risk Signals

- S1 Credit-to-GDP Gap
- S2 Debt Service Ratio
- S3 Property Vulnerability

Structural Risk 不进入短期 Asset Score。

## 8. Asset Compass 首版资产池

仅做：

- CN_EQUITY
- HK_EQUITY
- CN_GOV_BOND
- CN_CREDIT
- GOLD
- INDUSTRIAL_COMMODITY
- CNY

暂不做行业轮动、个股、自动仓位、自动交易。

## 9. 数据源原则

优先级：

### P1 官方 / 机器可读
- FRED
- OECD
- ChinaMoney
- ChinaBond
- SAFE
- Chicago Fed
- New York Fed

### P2 官方网页/文件
- NBS
- PBOC
- Customs

### P3 社区 Adapter
- AKShare

AKShare 是访问层，不是权威来源。尽量同时记录 `provider` 与 `original_source`。

### P4 Wind Manual
Wind 只承担：

- 免费源失败后的补洞；
- 某些专有数据；
- 一次性历史回填；
- 数据校验；
- 后续 Consensus / Surprise。

正常月份核心系统应尽量做到**不打开 Wind 也可更新**。

## 10. 数据架构

固定：

```text
Source Adapter
→ Canonical Normalizer
→ Validator
→ Canonical Parquet
→ Local DuckDB
→ Transform
→ Signal
→ Factor
→ Asset
→ UI
```

约束：

- Canonical Parquet = 数据真源
- DuckDB = 可重建本地缓存
- Adapter 不得绕过 Canonical 层
- 数据源与宏观模型解耦

## 11. 模型原则

### 不统一使用普通 Z-score

- PMI：neutral gap + momentum
- CLI：relative-to-100 + momentum
- CPI/PPI：rolling percentile + momentum
- spread/rate：robust z-score 或 percentile + momentum

### Level + Momentum

每个主要信号至少保留 Level 与 Momentum，权重配置化。

### Hierarchical Aggregation

```text
Raw Series
→ Economic Mechanism
→ Factor
→ Asset
```

禁止所有原始序列直接平均。

### Breadth

Factor 必须显示有多少独立经济机制支持当前方向。

### Confidence

至少分解：

- Coverage
- Freshness
- Source Quality

Confidence 不是预测概率。

## 12. Macro Regime

- Growth ↑ + Inflation ↑ = Reflation
- Growth ↑ + Inflation ↓ = Goldilocks
- Growth ↓ + Inflation ↑ = Stagflation
- Growth ↓ + Inflation ↓ = Deflationary Slowdown

必须允许 Mixed / Transition / Low Confidence / No Signal。

## 13. Asset Score

Asset Score 表示：

> 当前宏观环境对该资产的顺风/逆风程度。

不是 Expected Return、Trading Signal 或 Portfolio Weight。

必须可追溯：

```text
Asset
→ Factor
→ Signal
→ Raw Series
→ Data Source
```

## 14. 明确后置

- 云同步：V4
- ML / HMM：非默认路线
- 组合优化：非默认路线
- 自动交易：不在当前 Roadmap
- 新闻 NLP：不在当前 Roadmap

## 15. 版本顺序

```text
V1        DONE
V1.2      Multi-Source Acquisition
V1.3      Signal Registry
V1.5A     Transform Engine
V1.5B     Signal Engine
V1.5C     Macro Factor Engine
V1.2C     Data Coverage Hardening          ← 2026-08-29 负责人批准插入
V1.5D     Signal Quality Gate              ← 2026-08-29 负责人批准插入
V1.5E     Pre-Market Stabilization         ← 2026-08-30 负责人批准插入（v0.4c）
V1.6A     Market Confirmation              ← V1.6 拆分，Structural Risk 后移
V2        Asset Compass（前置：R2 先验矩阵调研）
V2.5      Historical Validation
V2.6      Structural Risk                  ← 原 V1.6 的一部分，后移
V3        Local Dashboard
V4        Cloud Mirror
V4.5      Historical Completion            ← 2026-08-30 负责人批准（偿还 Coverage Gate
                                              Waiver 数据债；补齐真实历史供经验验证）
V4.6      Empirical Validation Round 2     ← 2026-08-30 负责人批准（V4.5 Gate 通过后开窗）
Shadow Operation                           ← V4.6 后 3–6 个月观察（非开发窗口）
Product Stable Review                      ← 决定是否模型升级 / Signal 精简 / 新功能
V5        Optional Research                ← 原占位，优先级在 Shadow 之后
```

未经用户明确批准，不应跳版本。

> 修订记录（2026-08-29，经项目负责人评审批准）：原计划 V1.6（Market Confirmation +
> Structural Risk）+ V2 之前插入 V1.2C + V1.5D 两个数据质量 Gate；Structural Risk 从
> V1.6 后移至 V2.6（其不进入短期 Asset Score，不应因 BIS 数据阻塞 V2）。任务书见
> `docs/tasks/45_V1_2C_V1_5D_DATA_QUALITY_GATES.md`。
>
> 修订记录（2026-08-30，经项目负责人批准，来源需求文档
> `Personal_Macro_Asset_Compass_V4.5-V4.6_数据补全与经验验证开发需求_V1.0.md`）：V0–V4
> 工程完成（Engineering Foundation COMPLETE；Empirical Validation INCOMPLETE）。插入
> **V4.5 Historical Completion**（正式偿还 Economic Coverage Gate Waiver 数据债：Wind
> D2/D4 回填、Historical Coverage Matrix、source-transition 纪律、X1 overlap、X2 状态、
> Cloud size monitor、RELEASE_VERSION_POLICY）与 **V4.6 Empirical Validation Round 2**
> （补齐历史后重跑五方法 + LOMO + M3/Gold/Credit 研究性检验；Verdict 如实，禁强行正面；
> 禁以验证结果改权重）。V4.6 后进入 **Shadow Operation**（3–6 个月，Decision Journal +
> Shadow Metrics）→ **Product Stable Review**。任务书见
> `docs/tasks/85_V4_5_HISTORICAL_COMPLETION.md`、`docs/tasks/86_V4_6_EMPIRICAL_VALIDATION_R2.md`。
