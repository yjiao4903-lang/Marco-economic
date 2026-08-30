# Personal Macro Asset Compass — 项目开发报告（供外部窗口评估）

- **报告日期**：2026-08-30
- **评估对象**：`Personal Macro Asset Compass`（本地宏观监控与大类资产指引系统）
- **代码基线**：`git rev-parse HEAD` = `0d583c6`（tag `v0.8-cloud-mirror`）
- **测试基线**：252 passed / 0 failed（`-m network` opt-in 10 deselected）
- **用途**：本报告为**外部评估窗口**提供自包含的项目全貌、验证路径与已知限制。
  所有结论可经报告中的命令与文件复现；未编造任何数字、来源或测试结果。

---

## 1. 评估导航（如何验证本报告）

仓库根目录：`D:\宏观监控体系`（Windows + Python 3.11+，`pip install -e .`）。

**建议按序执行的验证命令（只读/可重建）：**

```bash
cd D:\宏观监控体系
git log --oneline --decorate -20          # 版本里程碑（tag：v0.3→v0.8 + v1.0）
python -m pytest                           # 252 passed（确定性测试，-m network opt-in 另跑）
python -m pytest -m network                # 网络集成测试（FRED/eastmoney 环境 blocker 可能 skip）
python scripts/signal_status.py            # 15 Core + 6 Market + 3 Structural 可用性
python scripts/macro_report.py             # 宏观快照：信号/四因子/Regime
python scripts/market_report.py            # 市场确认层：Matrix + Divergence 五状态
python scripts/asset_report.py             # 7 资产 Score/View/1M/3M/贡献/确认/置信
python scripts/structural_report.py        # S1/S2/S3 结构风险诊断
python scripts/validation_report.py        # V2.5 历史验证：Coverage Matrix/五方法/LOMO/regime
python scripts/cloud_sync.py --dry-run     # V4 云同步清单（config/raw/canonical）
python -m streamlit run src/macro_compass/ui/app.py   # V3 本地 Dashboard（需先跑 4 个报告脚本）
```

**权威文档地图（事实来源）：**

| 文档 | 内容 |
|---|---|
| `docs/00_MASTER_SPEC.md` | 项目宪法：定位/最高优先级/15+6+3 信号/数据源原则/红线/版本顺序（含历次批准批注） |
| `docs/01_CURRENT_STATE.md` | 当前状态/每版本交接记录/Known Issues（每次验收后更新） |
| `docs/02_ARCHITECTURE.md` | 分层架构与各层约束（§4/§8/§9/§10/§11/§12/§13/§14） |
| `docs/03_LLM_INTERACTION_GUIDE.md` | 多窗口接力开发流程 |
| `docs/COORDINATOR_HANDOFF.md` | 协调员工作手册：角色/验收程序/待办队列/红线 |
| `docs/tasks/50,55,60,65,66,70,80.md` | 各版本任务书（含 Acceptance Criteria） |
| `docs/research/*.md` | 4 份外部只读调研档案（含协调员抽验批注） |
| `docs/review/*.md` | 给负责人的评审简报 |

---

## 2. 项目定位与设计原则

**定位**：个人使用、本地优先、低维护、可解释的宏观资产配置辅助系统。将主要宏观与市场
数据自动获取后压缩为少数彼此独立的机制信号，形成宏观状态，监测市场是否确认，输出大类
资产的**顺风/逆风指引**（非预期收益、非交易信号、非仓位建议）。

**明确非目标**：Wind/Bloomberg 仿品、高频量化、自动交易、个股选股、黑箱 AI 预测、
自动仓位组合优化器、新闻 NLP、云上计算（云只做数据镜像）。

**最高优先级**（MASTER SPEC §2）：
> 低人工维护成本 > 数据可追溯性 > 模型解释力 > 稳定性 > 功能丰富度 > 模型复杂度

**负责人确立的 4 个 GATE**（一切进展的评审标尺）：
Economic Coverage（关键机制有真实数据）/ Explainability（可回到 raw source）/
Empirical Value（历史上真有信息）/ Maintenance Cost（用户每月要动手几次）。

---

## 3. 系统架构（02_ARCHITECTURE.md）

```text
[External Sources]
      ↓
[Source Adapters]               data_sources/*（统一 DataSourceAdapter 接口）
      ↓
[Canonical Normalizer + Validator]
      ↓
[Canonical Parquet]             数据真源（macro/ 与 market/ 分区）
      ↓
[DuckDB Cache]                  可重建本地缓存（删除后 rebuild_db.py 重建）
      ├─────────────┐
      ↓             ↓
[Transform]      [Market Data]
  (V1.5A 白名单)   (V1.6A)
      ↓             ↓
[Signal Engine]  [Market Confirmation]     ← V1.5B / V1.6A
      ↓
[Macro Factor Engine]            factors.py + regime.py（V1.5C）
      ↓
[Asset Compass]                  assets/（V2，只读 factor + market 输出）
      ↓
[Validation]                     validation/（V2.5，只读验证）
[Structural Risk]                structural/（V2.6，诊断层）
      ↓
[Streamlit Dashboard]            ui/（V3，只读快照）
[Cloud Mirror]                   cloud/（V4，Git 后端同步）
```

**核心隔离约束（贯穿全系统，均有源码级 + 行为级测试锁定）**：
- **Fundamental ↔ Market 隔离**：市场价格只属于 Market Confirmation 层，**不得反向修改
  Fundamental Score**（MASTER SPEC §4）。
- **Asset → Factor → Signal → Raw Series → Provider 全链路可追溯**（MASTER SPEC §13）。
- **Structural Risk 不进入 Asset Score**（MASTER SPEC §7）。
- **AssetScore ≠ 预期收益 ≠ 交易信号 ≠ 仓位**。
- **禁止 silent fallback**：任何 fallback/stale/missing/manual-required 进入结构化状态输出。
- **禁止 synthetic 进 production**：synthetic_guard 行级过滤，报告默认 `allow_synthetic=false`。

---

## 4. 数据架构与数据源矩阵

### 4.1 数据契约

- **Canonical 最小契约**：`series_id / date / value / source / source_file / import_time`；
  扩展：series_name/unit/frequency/category/file_hash（provider 数据 file_hash 空，source=provider 大写）。
- **Parquet = 真源；DuckDB = 可重建缓存**。
- **三类更新策略**（V1.2C/D 落地）：`append` / `replace_window` / `full_refresh`
  （GSCPI/BIS 等可修订序列用 full_refresh + vintage 快照 `data/local/vintage/<series>/`）。
- **as-of/release-lag 语义**：release_date = observation_date + 声明的 expected_release_lag_days。
- **indicators.yaml 为 series 元数据唯一真源**；signals.yaml 只引用 series_id。

### 4.2 数据源与路由（P1→P4 优先级）

| Provider | 承担 | 关键序列 | 验证状态 |
|---|---|---|---|
| OECD (SDMX) | P1 | CLI / CPI / IP / Retail / Exports | ✅ 真实 |
| FRED | P1 | ANFCI 备用 / DTWEXBGS(X2) / DFII10(X1 备用) | ⚠️ 本机网络间歇超时 |
| U.S. Treasury | P1 | 10Y Real Yield（X1 primary） | ✅ 真实 |
| Chicago Fed | P1 | ANFCI（X3） | ✅ 真实 |
| NY Fed | P1 | GSCPI / SOFR | ✅ 真实（full_refresh + vintage） |
| PBOC | P2 | LPR / OMO 政策利率 / 社融/政府债券（月度报告派生） | ✅ 真实 |
| NBS | P2 | PMI 分项 / 核心 CPI / 房地产累计同比 | ✅ 真实 |
| ChinaMoney | P2 | USD/CNY 中间价 / DR007 | ✅ 真实（WAF 限流已退避） |
| ChinaBond | P2 | 10Y 国债 / AAA 信用利差（historyQuery 同源派生） | ✅ 真实 |
| AKShare | P3 访问层 | PPI/M2/CPI 兜底、NBS 增速、新浪指数/期货 | ✅（接口变更已封装） |
| Eastmoney | P3 | CSI300/HSI kline（push2his） | ⚠️ 本机代理间歇不可达（显式 FALLBACK_USED） |
| BIS | P1 | WS_CREDIT_GAP(Type C) / WS_DSR（S1/S2） | ✅ 真实（bulk CSV，quarterly） |
| Wind Manual | P4 | 补洞/回填/校验 | 按需人工导出 |

> 数据层路由序列约 **29 条**（含 BIS 2 条）；`data/manual_series/CN_POLICY_RATE_7D.csv`
> 仅作历史 bootstrap/emergency fallback（PBC OMO live 路由已验证自动持久化）。

---

## 5. 信号体系（固定模型，MASTER SPEC §3）

### 5.1 15 个 Core Fundamental Signals

- **Growth Pulse**：G1 China CLI / G2 PMI New Orders / G3 Hard Activity（NBS 工增+社零增速，
  G0 活源切换）/ G4 Property Demand / G5 Export Demand
- **Inflation Pulse**：I1 Core CPI（headline fallback）/ I2 PPI / I3 Cost Pressure（PMI 购进价+GSCPI）
- **Domestic Financial**：D1 Funding（DR007−Policy Rate）/ D2 Private Credit Impulse /
  D3 Excess Liquidity（M2 YoY − 私人社融 YoY）/ D4 Fiscal Support
- **Global Financial**：X1 US 10Y Real Yield / X2 Broad USD / X3 ANFCI

**状态语义**：READY / WARMUP / PARTIAL / MISSING_INPUT / DECLARED（V1.5D 增 WARMUP：
READY 但声明式最小历史未满 → 分数 null → WARMUP；PARTIAL 永不转 WARMUP）。

**当前可用性（2026-08-30 实测）**：**READY 12/15**（Growth 5/5、Inflation 3/3、
Domestic 2/4、Global 2/3）+ **WARMUP 3**（D2/D4 待 Wind 回填、X2 待 FRED 恢复）。

### 5.2 6 个 Market Confirmation Signals（6/6 real READY）

| Signal | 序列 | Provider | 历史起点 | 方向约定（config/market.yaml） |
|---|---|---|---|---|
| M1 CSI300 | CSI300 | eastmoney/akshare | 2002-01 | positive（涨=多） |
| M2 Hang Seng | HSI | eastmoney/akshare | 2013-08 | positive（价格指数非全收益） |
| M3 10Y Yield | CN_GOV_YIELD_10Y | chinabond | 2023-05 | negative（收益率下行=宽松/牛市，v1 声明） |
| M4 AAA Spread | CN_AAA_CREDIT_SPREAD | chinabond | 2007-12 | negative（利差走阔=信用恶化；中票AAA 3Y−国债 3Y） |
| M5 USD/CNY | USD_CNY | chinamoney | 2016-01 | negative（USDCNY 上行=贬值） |
| M6 Copper | COPPER_PRICE | akshare(LME 3M) | 2016-08 | positive（LME 无换月跳空，无需新增变换） |

**Divergence 五状态**：CONFIRMED_POSITIVE / CONFIRMED_NEGATIVE /
POSITIVE_MACRO_DIVERGENCE / NEGATIVE_MACRO_DIVERGENCE / MIXED；
输出四元组 macro_direction / market_direction / agreement / confidence（数据质量，非概率）；
**永不翻译成 BUY/SELL**。

**当前真实 divergence（2026-08-30）**：M5 USD/CNY CONFIRMED_POSITIVE、M6 铜
NEGATIVE_MACRO_DIVERGENCE（growth 下行但铜 6M +7.4% 处 100 分位）、M1-M4 MIXED。

### 5.3 3 个 Structural Risk Signals（诊断层，不进 Asset Score）

- **S1 Credit-to-GDP Gap**：BIS WS_CREDIT_GAP Type C，CN/P，季度，1995-Q4 起。
  实测最新 2025-Q4 = **−7.688%** → READY，诊断 BELOW_TREND（40 季分位 0.275）。
- **S2 Debt Service Ratio**：BIS WS_DSR，CN/P，季度，1999-Q1 起。
  实测最新 2025-Q4 = **18.8%** → READY，诊断 ELEVATED（40 季分位 **0.950**）。
- **S3 Property Vulnerability**：代理池待 B 包调研（66 号）→ 当前 **NO_SIGNAL**（显式，
  不 synthetic、不硬编码未验证路由）。

---

## 6. 版本交付全景（V0 → V4）

### 6.1 里程碑与 tag

| 版本 | 范围 | 交付摘要 | Tag | 测试 |
|---|---|---|---|---|
| V0 | 基础骨架 | Python 项目、YAML 配置、synthetic fixtures、Excel/CSV importer | —（git 晚初始化已留档） | 基线 |
| V1 | 本地数据引擎 | Wind 手工导入、raw archive、SHA256 去重、canonical Parquet、DuckDB、质量检查 | v0.3（含 V1.2 初始） | — |
| V1.2 | 多源获取 | 统一 Adapter 接口、P1-P3 provider、增量更新引擎、状态输出、失败隔离 | | |
| V1.3+V1.5A | 信号注册+变换 | signals.yaml 15+6+3 声明、12 种变换白名单（纯函数） | v0.4a | |
| V1.5B+C | 信号+宏观引擎 | 十列契约、score 映射、四因子+Breadth+Confidence、Regime | v0.4-macro-engine | 163 |
| V1.2C+V1.5D | 覆盖加固+质量门 | 新端点替换、三策略+vintage、synthetic 隔离、WARMUP、饱和度评审 | v0.4b | |
| V1.5E | 数据稳定 | 共享状态解析、I1/X1 READY、X2 H.10 fallback、D3 派生、G3 活源评估 | v0.4c | 176 |
| **V1.6A** | **市场确认层** | G0（G3 活源切换）、6/6 Market READY、market 引擎、Divergence 五状态、隔离测试 | **v0.4d** | **192** |
| **V2** | **资产罗盘** | assets.yaml（R2 转写 5 规则）、AssetScore=Σβ×factor、8 字段契约、asset_report | **v0.5** | **205** |
| **V2.5** | **历史验证** | Coverage Matrix、五方法、LOMO（Leave-One-Mechanism-Out）、两条 regime 待检验项 | **v0.6** | **216** |
| **V2.6** | **结构风险** | BIS provider（S1/S2 真实）、structural 引擎、NO_SIGNAL、隔离测试 | **v0.7** | **235** |
| **V3** | **本地 Dashboard** | Streamlit 四面板只读 + 全链路下钻、loader 快照、红线词汇扫描 | **v1.0-local** | **244** |
| **V4** | **云镜像** | Git 后端 config/raw/canonical 同步、本地缓存/凭证拦截、6 态状态机、CONFLICT 处理 | **v0.8** | **252** |

> 注：V1.6A 的 D1 窗口曾自打 `v0.5-market-confirmation`，协调员按手册 §8 第 10 步重命名为
> `v0.4d-market-confirmation`（v0.5 预留给 V2 Asset Compass）——决策记录在案。

### 6.2 关键实现细节

**信号引擎（V1.5B）**：`score = level_weight×level_score + momentum_weight×momentum_score`；
组合语义 single/fallback（声明顺序即优先级，含历史偏好）/difference/average，composite 必附
contribution breakdown；score 映射 basis→[−1,1]（rolling_percentile / robust_zscore / scale），
direction:negative 取反，score>0 恒表示机制改善。**无黑箱**。

**宏观因子（V1.5C）**：factor score = 配置加权（默认等权）；Breadth = 支持当前方向的机制数；
Confidence = coverage/freshness/source_quality 三分量等权（**数据质量描述，非预测概率**）；
Regime 判定顺序：NO_SIGNAL → LOW_CONFIDENCE → TRANSITION → 四象限 → MIXED。
当前 **Regime = TRANSITION**（growth −0.357 ↓，inflation −0.031 中性带）。

**市场确认（V1.6A）**：1M/3M/6M 移动（pct_change/delta）+ oriented rolling percentile（250）；
市场方向仅由 6M 趋势过阈值 + 3M 不反向判定，1M/percentile 仅作上下文；阈值全配置化。

**资产罗盘（V2）**：`config/assets.yaml` = R2 先验矩阵转写。**转写 5 条硬约束**：
① 券商胜率/相关系数只支撑 importance tier，不作权重数值依据；
② "超额流动性"以系统 D3 定义为准（M2 YoY − 私人社融 YoY，非 R2 的 M2−名义GDP）；
③ 符号约定写入 config（利率债/信用债 +=价格涨/收益率下行；CNY +=升值）；
④ `ambiguous` 项权重强制 0 并标注（CN_CREDIT G1-G3/D2、CN_GOV_BOND I3、GOLD D2 等）；
⑤ 黄金实际利率脱钩 + 信用债资金面高敏感 → 标 `v25_pending` 供 V2.5 检验。
`AssetScore = Σ β_normalized × factor_score`（β 来自 R2 先验区间，L1 归一化到 [−1,1]，
**禁止历史收益搜索权重**）；Market confirmation 为并列字段不入评分。
当前 7 资产全 READY，均中性区间（|score|<0.15）。

**历史验证（V2.5）**：PIT 面板重建（按日期截断帧 + 冻结 compute_factor）；五方法
（forward returns / score bucket / regime / rolling beta / weight robustness）纯函数、
verdict 含 adequate/INSUFFICIENT_SAMPLE 诚实默认；LOMO 逐机制剔除测 factor stability +
asset stability + forward-separation delta（样本不足或机制计分占比<50% 一律不判候选）。
**结论如实**：四因子完整资产分数量纲仅约 21 个月（domestic_financial 因子 2024-12 起才有
D1 可计分），远低于负责人最低样本（2012/2015–present）——五方法以探索性
NO_EFFECT_OR_WEAK 为主；LOMO 早见 growth:G3 为低增量候选（**仅建议，未降级**）；
黄金脱钩 DATA_BLOCKED（无真实 2022 前历史）、信用债资金面敏感 INSUFFICIENT_SAMPLE。

**结构风险（V2.6）**：复用 V1.5A 白名单（level/delta/rolling_percentile），V1.5D 状态 +
stale 标记；无数据/最新季频超预算 → 报告层显式 NO_SIGNAL。

**UI（V3）**：`ui/loader.py` 只读快照加载器（不 import 引擎、不触发更新/重算）；
`ui/app.py` Streamlit 四面板（宏观总览/市场确认/资产指引/结构风险）+ 资产
Asset→Factor→Signal→Raw Series→Provider 下钻；as-of 同天对齐校验（same_day_alignment）、
synthetic 泄漏检测（synthetic_rows）、红线词汇扫描（forbidden_words）均为纯函数并有测试。

**云镜像（V4）**：Git 后端同步 `config/ + data/raw/ + data/canonical/`；本地保留
`*.duckdb / data/local / logs / .venv / cache`；`verify_manifest` 双重拦截本地缓存与凭证
（SECRET_BLOCKED）；6 态状态机（SYNC_OK / NO_CHANGES / DRY_RUN / CONFLICT / SECRET_BLOCKED /
FAILED）；canonical 并发写 → 显式 CONFLICT 不静默覆盖；raw append-only 合并零冲突；
pull 后提示 rebuild_db.py 重建。实测 dry-run 清单 12 项严格在范围、blocked=[]。

---

## 7. 测试与质量保障

- **测试演进**：163（V1.5C）→ 176（v0.4c）→ 192（V1.6A）→ 205（V2）→ 216（V2.5）→
  235（V2.6）→ 244（V3）→ **252（V4）**，全程 0 failed。
- **network 测试 opt-in**：`-m network` 单独运行；确定性解析用保存 fixture 测试；
  第三方网络偶发失败不破坏核心 pytest（FRED / eastmoney push2his 为已知环境 blocker，
  如实 skip / FALLBACK_USED）。
- **隔离测试范式**（每层都带）：源码级（包不 import 下层/对等层 + 无权重搜索命令）+
  行为级（计算后输入帧逐位不变）。
- **synthetic 隔离**：production 计算默认隔离 synthetic（`allow_synthetic=false`）；
  signal_status/macro_report 可区分 real/synthetic/MIXED。

---

## 8. 验收记录与红线

每个版本均按任务书逐条 Acceptance Criteria 验收（V1.6A 11 条 / V2 11 条 / V2.5 10 条 /
V2.6 8 条 / V3 7 条 / V4 6 条），并有协调员验收批注记录于 `docs/01_CURRENT_STATE.md` §8。

**红线清单（任何时候不违反，验收时逐条核对）**：
1. 测试不全绿 = 退回；2. signals.yaml 越权变更 = 退回（唯一例外：V1.6A G3 活源切换，
   负责人 2026-08-30 批准）；3. 存在反向数据流 = 退回；4. synthetic 进 production = 退回；
5. silent fallback = 退回；6. 无 blocker 分类的 coverage 声明 = 退回；
7. 未经批准不新增 Core Signal / 不跳版本 / 不改冻结组件。

**关键决策记录（负责人批准）**：
- 2026-08-29：插入 V1.2C+V1.5D 双 Gate；Structural Risk 后移 V2.6；
- 2026-08-30：v0.4c 方案（Gate A/B 验收、插入 V1.5E、V1.6A 独立成窗、V2 前置 R2、
  V2 后立即 V2.5 不做 UI、synthetic fixture 永久保留、4 GATE 管理框架）；
- 2026-08-30：G3 活源切换（授权 D1 改 signals.yaml 仅限 G3）；
- 2026-08-30：**Economic Coverage Gate 豁免开放**（wind_backfill_tsf.csv、X2 FRED、
  B 包调研标记后补，不阻塞 V2 及之后开发）。

---

## 9. 已知问题与局限（如实）

### 9.1 数据覆盖（Economic Coverage Gate 未完全达成）

- **D2/D4（WARMUP）**：等待用户人工导出 `wind_backfill_tsf.csv`（Total TSF Flow +
  Government Bond Financing Flow，≥60 个月）。导入链已就绪（PBOC 增量按月流入），
  **但 `config/wind_mapping.yaml` 尚缺社融/政府债券列映射**——文件到达后需先按导出列名
  补映射再走 import_wind.py（协调员 2026-08-30 核实并记录）。禁止其他来源凑数。
- **X2（WARMUP）**：FRED DTWEXBGS 本机网络超时（H.10 fallback 已实战工作）；FRED 恢复后
  update 自动补全历史。
- **X1 overlap check BLOCKED**：`scripts/overlap_check.py` 已 armed，FRED 行并入
  US_REAL_YIELD_10Y 前必须先 PASS（≥60 共同交易日、|diff|≤0.05）。当前该序列仅 Treasury 单源。
- **S3（NO_SIGNAL）**：房地产脆弱性代理池待 B 包调研（66 号）落地。

### 9.2 模型/口径局限

- **M3 方向约定局限（v1 声明）**：收益率下行=宽松/牛市方向；若下行源于增长恶化预期而非
  宽松，语义失真——报告同时展示 raw basis 与 oriented percentile。
- **M6 口径**：LME 3M 为美元净价（内嵌汇率）+ 伦敦日历（发布滞后 1 天、跨日历不对齐）。
- **G3 OECD fallback 条目为"声明保留"**：指数与 NBS 增速单位不同，正常运行永不触发；
  若 NBS 双腿完全无数据才可能被选，届时需负责人重新决策口径。
- **Divergence / Asset 阈值未经历史检验**：为声明先验（V2.5 才允许回测）。
- **V2.5 样本不足**：完整资产分数量纲约 21 个月；黄金脱钩/信用债资金面两条 regime 检验
  均受历史长度限制（DATA_BLOCKED / INSUFFICIENT_SAMPLE）。

### 9.3 环境/运维

- FRED 间歇超时、AKShare/代理间歇不可用、ChinaMoney WAF 限流、check_quality 混频警告；
- eastmoney push2hi 本机被代理拦截（M1/M2 primary 走 FALLBACK_USED）；
- V4 真实远程 URL 需用户配置 `git remote` 后首次 push/pull；
- 环境事实：Windows + Git Bash；Python 3.11+；本机代理是 FRED 超时与 eastmoney push2
  失败的共同嫌疑（生产请求建议 trust_env=False 按域名分流）。

---

## 10. 后补项与待办队列（Owner 标注）

| 事项 | Owner | 状态 |
|---|---|---|
| `wind_backfill_tsf.csv` 上传（附列名，供补 wind_mapping.yaml 映射） | 用户 | 已确认可取得，待上传 |
| 文件到达后：补映射 → 导入 → D2/D4 转 READY；若含存量列，D3 历史加固 | 协调员 | 导入链就绪（含映射缺口记录） |
| FRED 网络恢复：update 补 X2 历史；X1 overlap check PASS 后才允许 FRED 行并入 | 协调员/提醒用户 | X2=WARMUP、X1 overlap BLOCKED |
| B 包外部调研（66 号）：BIS WS_* 稳定性 + S3 代理池可获取性 | 派发外部窗口 → 协调员抽验归档 | 任务书已打包，待派发 |
| B 包归档后：S3 落地 + 复核 S1/S2 update_policy/max_staleness（provisional） | 协调员 | 待 B 包 |

---

## 11. 给外部评估窗口的建议核查点

1. **可追溯性抽查**：任取一个资产（如 CN_EQUITY），从 asset_report 的 Signal 贡献逐级
   上溯到 Factor → Signal → series → provider（config/assets.yaml 与 data_sources.yaml）。
2. **隔离抽查**：`grep -ri structural` 于 `src/macro_compass/assets/`（应为空）；
   `grep -ri "market"` 于 `src/macro_compass/macro/`（应为空，仅状态解析层例外）。
3. **红线词汇**：`python scripts/asset_report.py` / `market_report.py` 输出中不应有
   BUY/SELL/仓位；`src/macro_compass/assets/` 中不应有 fit/optimize/lstsq/polyfit。
4. **synthetic 隔离**：signal_status 默认输出不含 synthetic 序列；GOLD 36 行为 synthetic
   已隔离（不显示为真实）。
5. **数据锚点**：S1=−7.688、S2=18.8 与 BIS 档案实测一致；M4 利差 0.4157 与调研档案一致；
   M6 铜价与新浪外盘 CAD 一致。
6. **可重建性**：删除 `data/local/` 后 `python scripts/rebuild_db.py` 可从 canonical 完全重建。
7. **报告自洽**：`macro_report / market_report / asset_report / structural_report /
   validation_report` 五入口输出与 CURRENT_STATE 描述一致（同 as-of 2026-08-30）。

---

*本报告所有数字、状态、tag、测试计数均来自当前仓库可复现的执行结果；不确定或受限项
已如实标注（DATA_BLOCKED / INSUFFICIENT_SAMPLE / 环境 blocker / 后补）。*
