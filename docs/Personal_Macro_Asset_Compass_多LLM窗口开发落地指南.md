# Personal Macro Asset Compass — 多 LLM 窗口开发落地指南

本文件用于总览；实际给开发窗口时，优先使用拆分后的 4 份基础文档 + 当前 Task Spec。



---

# Personal Macro Asset Compass — LLM 协作开发包

建议复制整个目录到项目仓库的 `docs/`。

文件结构：

```text
docs/
├─ 00_MASTER_SPEC.md
├─ 01_CURRENT_STATE.md
├─ 02_ARCHITECTURE.md
├─ 03_LLM_INTERACTION_GUIDE.md
└─ tasks/
   ├─ 10_V1_FREEZE_HANDOFF.md
   ├─ 20_V1_2_DATA_ACQUISITION.md
   ├─ 30_V1_3_V1_5A_SIGNAL_FOUNDATION.md
   ├─ 40_V1_5B_V1_5C_MACRO_ENGINE.md
   ├─ 50_V1_6_V2_ASSET_COMPASS.md
   ├─ 60_V2_5_VALIDATION.md
   ├─ 70_V3_UI.md
   └─ 80_V4_CLOUD.md
```

当前执行：

1. 旧窗口执行 `10_V1_FREEZE_HANDOFF.md`
2. 形成 V1 Git checkpoint
3. 在同一项目/仓库下开新窗口
4. 新窗口读取 README + 00 + 01 + 02 + `20_V1_2_DATA_ACQUISITION.md`
5. 运行 baseline pytest
6. 完成 V1.2A + V1.2B
7. Self Review
8. 更新 CURRENT_STATE
9. Git checkpoint
10. 再切下一窗口


---

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
V1.6      Market Confirmation + Structural Risk
V2        Asset Compass
V2.5      Historical Validation
V3        Local Dashboard
V4        Cloud Mirror
V5        Optional Research
```

未经用户明确批准，不应跳版本。


---

# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-29  
**当前阶段：** V1 Local Data Engine 已完成，准备进入 V1.2。

## 1. 已完成

### V0 Foundation — DONE
- Python 项目骨架
- YAML 配置基础
- synthetic fixtures
- Excel/CSV importer
- normalizer
- validator
- pytest 基础

### V1 Local Data Engine — DONE
- Wind Excel/CSV 手工导入
- raw archive
- SHA256 去重
- canonical Parquet
- DuckDB 本地缓存
- import manifest
- 数据质量检查
- DuckDB 可从 canonical 重建

## 2. Canonical 最小契约

```text
series_id
date
value
source
source_file
import_time
```

可扩展：

```text
series_name
unit
frequency
category
file_hash
provider
original_source
observation_date
release_date
asof_date
vintage_date
```

## 3. 当前架构

```text
Raw / External Data
→ Canonical Parquet
→ DuckDB
```

Parquet 是数据真源；DuckDB 是本地分析缓存。

## 4. 当前 README 已定义命令

```bash
python scripts/generate_fixtures.py
python scripts/import_wind.py data/fixtures/wind_macro_sample.xlsx --dry-run
python scripts/import_wind.py data/fixtures/wind_macro_sample.csv
python scripts/rebuild_db.py
python scripts/check_quality.py
python -m pytest
```

新窗口必须先验证这些命令是否仍成立。

## 5. Frozen Components

原则上视为已验收：

- 现有 ingestion 基础
- canonical schema
- raw archive
- DuckDB rebuild
- file hash / dedup

V1.2 默认只扩展，不重写。

## 6. 当前未开发

- 自动公共数据源
- 15+6+3 Signal Registry
- Transform Engine
- Signal Engine
- Macro Factor Engine
- Market Confirmation
- Structural Risk
- Asset Compass
- Historical Validation
- Streamlit Dashboard
- Cloud Mirror

## 7. 下一任务

> V1.2 Multi-Source Acquisition

建议同一个新开发窗口完成 V1.2A + V1.2B。

## 8. 旧窗口交接时必须填写

```text
Last Test Result: TO_BE_CONFIRMED
Last Test Count: TO_BE_CONFIRMED
Last Git Commit: TO_BE_FILLED
Last Git Tag: TO_BE_FILLED
Known Issues: TO_BE_FILLED
Modified Files Since Last Release: TO_BE_FILLED
```

## 9. 每次窗口结束必须更新

- Current Version
- Completed
- Tests
- Known Issues
- Frozen Components
- Next Task
- Git Commit / Tag

详细历史由 Git 保存，不在本文件堆积长日志。


---

# Personal Macro Asset Compass — ARCHITECTURE

## 1. 设计目标

针对：

- 单人使用
- Windows 本地
- 低维护
- 无 Wind API
- 长期运行
- 后续可能多 PC
- 需要历史回溯

因此不采用重型服务化架构。

## 2. 分层

```text
[External Sources]
        ↓
[Source Adapters]
        ↓
[Canonical Normalizer]
        ↓
[Validation]
        ↓
[Canonical Parquet]
        ↓
[DuckDB Cache]
        ├─────────────┐
        ↓             ↓
[Transform]      [Market Data]
        ↓             ↓
[Signal Engine] [Market Confirmation]
        ↓
[Macro Factor Engine]
        ↓
[Asset Mapping]
        ↓
[Asset Compass]
        ↓
[Streamlit]
```

## 3. Source Adapter

Adapter 只负责：

1. 请求数据；
2. 解析原始响应；
3. 映射 canonical-compatible DataFrame；
4. 返回元数据。

不负责 Factor、Asset、UI 或投资方向判断。

统一接口建议：

```python
class DataSourceAdapter:
    def fetch(self, series_id, start_date=None, end_date=None) -> pd.DataFrame:
        ...
```

## 4. Source Registry

使用：

```text
config/data_sources.yaml
```

每个 `series_id` 声明：

- primary provider
- fallback provider
- provider-specific code
- frequency
- source quality
- staleness threshold

## 5. Canonical Layer

最小：

```text
series_id
date
value
source
source_file
import_time
```

推荐扩展：

```text
provider
original_source
observation_date
release_date
asof_date
vintage_date
```

## 6. Data Status

每条 series 至少支持：

```text
OK
STALE
FAILED
FALLBACK_USED
MANUAL_REQUIRED
```

单个数据源失败不得让整个系统崩溃。

必须生成：

```text
data_status.csv
manual_fetch_required.csv
```

## 7. Transform Layer

Transform 必须纯函数化。

禁止网络访问、DB side effect、隐式 forward fill。

支持：

```text
level
delta
pct_change
yoy
mom
moving_average
rolling_percentile
robust_zscore
neutral_gap
rolling_sum
rolling_mean
acceleration
```

## 8. Signal Layer

每个 Signal 输出：

```text
signal_id
date
level
level_score
momentum
momentum_score
score
freshness
coverage
status
```

Composite Signal 必须提供 contribution breakdown。

## 9. Macro Layer

只读取 Signal 输出，不得直接跳回 raw series。

主要输出：

- Growth
- Inflation
- Domestic Financial Components
- Fiscal
- Global Financial Conditions
- Breadth
- Confidence
- Regime

## 10. Market Layer

Market 与 Fundamental 隔离。

输出：

- trend
- percentile
- confirmation state
- divergence state

不得反向改变 Growth/Inflation。

## 11. Asset Layer

使用经济学先验矩阵。

V2 不得用历史收益自动搜索最优权重，也不得让资产自身价格进入该资产 Fundamental Score。

## 12. Validation Layer

V2.5 才允许：

- forward return
- bucket analysis
- regime analysis
- rolling beta
- weight robustness

允许结论：模型历史预测能力弱或不稳定。

## 13. UI Layer

V3 使用 Streamlit。

不建立 FastAPI / React / Next.js。

## 14. Cloud Layer

V4 才开发。

云端同步：

```text
raw/
canonical/
config/
```

本地保留：

```text
*.duckdb
cache/
logs/
.venv/
```

每台 PC 独立 DuckDB。


---

# 多 LLM 窗口开发交互指南

## 1. 工作模式

后续采用：

> 同一个项目 + 同一个代码仓库 + 多个开发窗口分阶段接力

窗口不是项目记忆。真正的项目记忆由：

```text
代码
Git history
00_MASTER_SPEC.md
01_CURRENT_STATE.md
02_ARCHITECTURE.md
当前 Task Spec
```

承担。

## 2. 推荐窗口划分

| 窗口 | 范围 |
|---|---|
| 旧窗口 | V0 + V1 Freeze/Handoff |
| Window A | V1.2A + V1.2B |
| Window B | V1.3 + V1.5A |
| Window C | V1.5B + V1.5C |
| Window D | V1.6 + V2 |
| Window E | V2.5 |
| Window F | V3 |
| Window G | V4 |

## 3. 什么时候继续当前窗口

继续当前窗口：

- 仍是同一认知模块；
- 代码范围高度相关；
- bug/测试尚未闭环；
- 当前窗口上下文清楚。

例如 V1.2A + V1.2B 都属于 Data Acquisition，建议同一窗口。

## 4. 什么时候开新窗口

建议开新窗口：

1. 阶段已验收；
2. 即将进入新的 subsystem；
3. 当前窗口历史过长；
4. LLM 开始频繁顺手重构；
5. 已形成 Git checkpoint。

## 5. 现在第一步

先让旧窗口执行：

```text
docs/tasks/10_V1_FREEZE_HANDOFF.md
```

旧窗口只做：

- 完整测试
- README 校验
- CURRENT_STATE 更新
- Known Issues
- Git checkpoint

不继续开发 V1.2。

## 6. 新窗口第一条消息

直接发送：

```text
你接手的是一个已经开发到 V1 的现有项目。
不要重新初始化，不要重新设计。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md
5. docs/tasks/20_V1_2_DATA_ACQUISITION.md

然后：
- 查看 repository tree
- 运行 python -m pytest 建立 baseline
- 对照 CURRENT_STATE 验证实际代码状态
- 如文档与代码冲突，以代码和测试为事实，并先报告差异
- 只执行当前 Task Spec
```

## 7. 不要这样说

不要：

```text
我想做一个宏观量化系统，你重新帮我设计。
```

也不要：

```text
根据我们以前所有讨论继续。
```

新窗口应以仓库文档为准。

## 8. 合格的新窗口接手回复

至少应包含：

```text
已读取哪些文档
baseline pytest 结果
当前代码状态
计划修改哪些文件
明确不修改哪些 frozen components
```

如果它没有 baseline 就开始大规模改代码，回复：

```text
先停止新增修改。按 Task Spec 先运行完整 baseline 测试，并确认 CURRENT_STATE 与仓库实际状态是否一致。不要提前开发。
```

## 9. 开发中你主要盯 4 件事

### 范围扩张

回复：

```text
不要扩大范围。严格按当前 Task Spec 开发；未来版本只保留接口，不实现。
```

### 重写 V1

回复：

```text
V1 数据层当前视为 frozen。除非能证明现有接口阻塞当前任务，否则不要重写。优先通过 adapter 扩展。
```

### 网络测试不稳定

回复：

```text
网络 integration test 与 deterministic unit test 分离。第三方网络偶发失败不能导致核心 pytest 不稳定；解析逻辑使用保存 fixture 测试。
```

### Silent fallback

回复：

```text
禁止 silent fallback。任何 fallback、stale、missing、manual required 都必须进入结构化状态输出。
```

## 10. 每个窗口完成时：第一轮 Self Review

发送：

```text
现在不要继续开发下一版本。

请对本次任务做 self-review：
1. 对照 Task Spec 逐条列 acceptance criteria；
2. 每条标记 PASS/FAIL；
3. 运行完整 pytest；
4. 运行 Task Spec 规定的 smoke/integration command；
5. 列出本次修改文件；
6. 列出所有已知限制；
7. 检查是否实现了范围外功能；
8. 检查是否破坏 V1 frozen components。

如果有 FAIL，继续修复，不要结束任务。
```

## 11. 第二轮 Handoff Review

全部 PASS 后发送：

```text
任务验收通过后，请完成交接：

1. 更新 docs/01_CURRENT_STATE.md；
2. 更新 README 中必要的运行说明；
3. 写入本次版本完成状态；
4. 记录最新测试结果；
5. 记录 Known Issues；
6. 给出建议 Git commit message；
7. 给出建议 Git tag（如果是阶段 checkpoint）；
8. 明确下一任务的输入接口；
9. 不开始下一版本。

最终只输出交接报告。
```

## 12. 测试失败时

回复：

```text
当前版本尚未达到 Definition of Done。不要进入下一版本。定位失败测试根因，修复后重新运行完整 pytest，并重新给出 acceptance checklist。
```

## 13. 数据源失效时

回复：

```text
不要伪造成功结果。

请将该 series 标记为 FAILED / MANUAL_REQUIRED，并：
1. 保留 deterministic parser fixture test；
2. 记录失败原因；
3. 检查是否有符合优先级规则的 fallback；
4. 如果没有，保持系统继续更新其他 series。
```

## 14. LLM 提议增加新 Core Signal

先要求回答：

```text
这个指标代表什么新的独立经济机制？
与现有 15 Core Signals 是否重复？
不加入会损失什么？
能否只放 diagnostic/satellite？
增加多少维护成本？
```

默认不加入 Core。

## 15. LLM 提出 ML/HMM

回复：

```text
记录为 V5 research candidate，不进入当前版本。当前优先采用可解释经济机制和历史验证。
```

## 16. Git checkpoint 建议

```text
V1       v0.2-local-data-engine
V1.2     v0.3-multisource-acquisition
V1.5     v0.4-macro-engine
V2       v0.5-asset-compass
V2.5     v0.6-validation
V3       v1.0-local
```

## 17. 你本人真正需要维护的内容

你只需要关注：

- 是否批准改变产品需求；
- 是否批准新增 Core Signal；
- 测试是否 PASS；
- CURRENT_STATE 是否更新；
- Git checkpoint 是否形成；
- `manual_fetch_required.csv` 是否要求 Wind。

## 18. 最简循环

```text
旧窗口 Freeze/Handoff
→ Git checkpoint
→ 新窗口读 4 份文档 + 当前 Task
→ pytest baseline
→ Implement
→ Self Review
→ pytest
→ Handoff
→ CURRENT_STATE
→ Git checkpoint
→ 下一窗口
```
