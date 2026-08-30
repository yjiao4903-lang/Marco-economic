# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-30（v0.4d）  
**Current Version:** V2 Asset Compass（v0.5；V0–V1.6A 全部冻结）  
**当前阶段：** Fundamental Core **READY 12/15** + WARMUP 3（D2/D4 等用户 Wind 回填、
X2 等 FRED 网络恢复）；**Market Confirmation 6/6 real READY**（M1-M6 全部真实数据）；
**V2 Asset Compass 7/7 real READY**（资产层读取 factor 输出，无反向流）。
Regime = TRANSITION（growth −0.357 ↓，inflation −0.031 中性带）。Dashboard（V3）尚未开发。  
所有 `data/fixtures/` 下的数据均为 **synthetic 模拟数据**，不是真实市场数据，
且默认不进入生产计算。

## 1. 已完成

### V0 Foundation — DONE
- Python 项目骨架、YAML 配置、synthetic fixtures
- Excel/CSV importer、normalizer、validator、pytest 基础

### V1 Local Data Engine — DONE（frozen）
- Wind 手工导入、raw archive、SHA256 去重
- canonical Parquet（真源）、DuckDB 缓存、import manifest、质量检查、可重建

### V1.2 Multi-Source Acquisition — DONE（frozen，2026-08-29）
- `src/macro_compass/data_sources/`：统一 `DataSourceAdapter` 接口
  （`fetch(series_id, start_date=None, end_date=None) -> canonical DataFrame`）
- V1.2A providers：FRED、OECD(SDMX)、ChinaMoney、ChinaBond、AKShare(可选依赖)
- V1.2B providers：PBOC(LPR)、SAFE、NY Fed(SOFR)、Chicago Fed(NFCI/ANFCI)、Wind Manual
- `config/data_sources.yaml`：primary/fallback provider、provider_code、frequency、
  max_staleness_days、original_source、manual_instructions
- 增量更新引擎（`updater.py` + `scripts/update_sources.py`）：
  fetch_state 记录 last_observation_date / last_successful_fetch / last_provider /
  fetch_status；增量抓取带 45 天 revision overlap；`--backfill` 全量
- 状态输出：`data/local/data_status.csv`、`data/local/manual_fetch_required.csv`
  （OK / STALE / FAILED / FALLBACK_USED / MANUAL_REQUIRED）
- 失败隔离：单 provider/series 异常不影响其他序列；network 测试与确定性测试分离
  （`-m network` opt-in）

**真实验证结果（2026-08-29，本机网络）：**
- 真实抓取成功入库 8 条外部序列 / 4 个 provider：
  - OECD：CHN_CLI(410) CHN_CPI_INDEX(403) CHN_IND_PROD_INDEX(365)
    CHN_RETAIL_SALES_INDEX(581) CHN_EXPORT_YOY(413)
  - ChinaMoney：USD_CNY（中间价，daily）
  - NY Fed：US_SOFR（500）
  - PBOC：CN_LPR_1Y（最新公告）
- 真实失败/受限：FRED（本网络超时，ANFCI/DFII10/DTWEXBGS 进 manual list）、
  ChinaBond（页面 404，token 端点失效）、AKShare（未安装，CSI300 → MANUAL_REQUIRED）、
  Chicago Fed（下载 URL 需人工配置 provider option `url`）

### V1.3 Signal Registry + V1.5A Transform Engine — DONE（2026-08-29）
- `config/signals.yaml`：15 Core（G1–G5 / I1–I3 / D1–D4 / X1–X3）+ 6 Market（M1–M6）
  + 3 Structural（S1–S3，占位）。每条 Core 声明 mechanism / factor / inputs(role) /
  transforms / momentum_transform / combination(仅声明) / direction / neutral /
  level_weight + momentum_weight；Market/Structural 仅声明 layer + mechanism + inputs，
  不含打分配置（引擎属 V1.6）
- `src/macro_compass/signals/registry.py`：加载与校验 signals.yaml——必填字段按 layer
  分层校验、transform 类型必须在 V1.5A 白名单内、引用的 series_id 必须已在
  indicators.yaml 注册（否则报明确错误）；`assess_availability()` 按 canonical 实际
  数据输出 READY / PARTIAL / MISSING_INPUT / DECLARED
- `src/macro_compass/transforms/`（trend / smoothing / stats / pipeline）：ARCHITECTURE §7
  12 种白名单变换全部实现，纯函数（无网络、无 DB side effect、无隐式 forward fill；
  显式 `fill: {method: ffill, limit: N}` 是唯一受支持的填充，需逐步声明）
- `scripts/signal_status.py`：逐信号可用性报告 + 写缺失序列清单
  `data/local/missing_series.csv`（当前 20 条缺失）
- `scripts/transform_smoke.py`：对真实 canonical 序列跑声明的变换链并输出预览（只读）
- indicators.yaml 一次性迁移：`level_gap`→`neutral_gap`、`zscore`→`robust_zscore`；
  5 条序列的 factor 重映射到 MASTER SPEC 分类（见下）；新增 16 条 metadata-only
  序列注册（signals.yaml 引用但尚无数据/路由）

**当前可用性快照（2026-08-29）：** Core READY 3/15（G1/G3/G5），PARTIAL 2（I1、D3），
MISSING_INPUT 10。缺失序列共 20 条（G2/G4/I1-I3/D1-D4/X1-X3 及 M2/M4/M6/S1/S2 的输入），
完整清单见 `python scripts/signal_status.py` 输出与 `data/local/missing_series.csv`。
禁止为凑齐输入擅自新增 provider——补数走 V1.2 扩展窗口或 manual fetch。

### V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate — DONE（2026-08-30，Gate A/B）
- **新 provider / 端点替换**（全部先实测再入库，端点验证见 docs/research 调研档案 + 本窗口复测）：
  - `chicagofed`：直链 CSV（一份文件含 NFCI+ANFCI）→ X3 ANFCI（2748 期周度，READY real）
  - `nyfed` GSCPI：NY Fed 直链 CSV，update_policy=full_refresh + vintage 快照（347 期月度）
  - `chinabond`：旧 searchYc（404）→ pgxh/yzQuery 替换端点 → CN_GOV_YIELD_10Y 恢复自动更新
  - `chinamoney` DR007：prr-chrt.csv 静态文件（live，66 个交易日滚动）
  - `nbs`（新）：国家统计局新闻发布页解析（PMI 新订单/购进价格/房地产累计同比），离线 fixture 测试
  - `pbc` 扩展：OMO 交易公告（7 天逆回购利率）+ 月度金融统计数据报告
    （社融/政府债券净融资累计值经 `cumulative_to_monthly` 差分为月度流量，replace_window）
  - `akshare` 扩展：CN_PPI_YOY / CN_M2_YOY / CN_TSF_TOTAL 兜底、CN_DR007 历史（FDR007 定盘，
    分块抓取，仅作 backfill）
  - `manual_series`（新）：committed 官方步进序列（data/manual_series/，MANUAL 来源，非 synthetic），
    目前仅 CN_POLICY_RATE_7D 历史台阶（2024-01 起每日展开）
  - FRED timeout 45→90s 并在 updater 增加一次 5s 退避重试（FRED 本网络间歇可达）
- **update_policy**：append / replace_window / full_refresh 三模式落地
  （canonical_store 新增 replace_window/replace_series；GSCPI=full_refresh，PBOC 报告类=replace_window）；
  full_refresh 与可修订序列保留 raw vintage 快照（data/local/vintage/<series>/，含 asof_date/provider）
- **freshness metadata**：data_sources.yaml 每序列可声明 expected_release_lag_days 等（V1.5D as-of
  语义：release_date = observation_date + 声明滞后，快照不假设当天可知）
- **synthetic production isolation**：行级过滤（synthetic_guard，按 macro.yaml synthetic_markers 匹配
  source_file）；signal_status / macro_report 默认 allow_synthetic=false，测试才可 --allow-synthetic。
  效果：CN_CPI_YOY 等 synthetic 序列在 production 中显式 MISSING，不再被当真实数据
- **V1.5D（Gate B）**：
  - `WARMUP` 状态：READY 但最新分数因声明式最小历史（由链上 window/period 推导，**禁止缩窗**）未满
    而为 null → WARMUP；PARTIAL（缺序列）永不转为 WARMUP
  - `scripts/signal_quality.py`：15 core 逐信号 status/history/freshness/coverage/
    saturation_ratio_24m/60m（|score|≥0.95 占比，>40% 记 SCALE_SATURATED）/normalization/as-of 说明
  - Normalization review（§17.3 经济锚点，非收益拟合）：G4/G5 scale 由"小数"口径修正为 NBS/OECD
    实际"百分数"口径（G4 level 10、G5 level 15），G2 momentum 1.0→3.0（PMI gap 月差约 ±3pp）；
    修正后无信号长期贴 ±1 边界（sat24 全部 <13%）
  - composite completeness：breakdown 常显 available/required/coverage
- **真实抓取结果（2026-08-30）**：25 条路由序列 21 条 OK；当前 Core READY real 9/15，
  WARMUP 2（D2/D4），PARTIAL 1（D3），MISSING 3（I1/X1/X2）；Regime = TRANSITION
  （growth −0.409 down，inflation +0.125 neutral）

### V1.5E Pre-Market Stabilization（v0.4c）— DONE（2026-08-30）
- **P0-1 共享状态解析（架构修复）**：新增 `signals/status.py`
  （`resolve_signal_status` + `load_core_computations` 生产数据管线），
  signal_status / macro_report / signal_quality 三入口全部复用——
  D2/D4 在同一 as-of 下状态一致（WARMUP），禁止各自复制逻辑。
- **P0-2 I1 Consumer Inflation READY**：核心 CPI 不再依赖解读栏目——NBS 正式 CPI 发布页
  表格含「不包括食品和能源」行（endpoint 实测：2026-07 同比 0.9）；headline CPI 走
  AKShare `macro_china_cpi`（223 期）。引擎 fallback 语义精化：优先选**满足声明最小历史**的
  输入（core 10 期 < window 60 → 自动落到声明的 headline fallback；core 历史自然累积后
  自动切回），绝不静默把 headline 写进 core 序列（两个 series_id 严格分开）。
- **P0-3 X1 US 10Y Real Yield READY**：新增 `treasury.py`（U.S. Treasury Daily Par Real
  Yield Curve，官方 CSV，665 期 2023-2026 已入库）；路由 primary=treasury、fallback=fred
  （DFII10 定义同源：FRED 即 redistribution of Treasury curve）。
  **Overlap check（硬性验收项）**：`scripts/overlap_check.py` 已落地并 armed——但 FRED 本机
  网络 9 次尝试全部超时，check **BLOCKED** 如实输出；网络恢复后必须先 PASS（≥60 共同交易日、
  |diff|≤0.05）再允许 FRED 行并入该序列。
- **P0-4 X2 Broad USD WARMUP**：新增 `fedh10.py`（Fed H.10 周发布页 BROAD JAN06=100 行，
  只解析发布页、不建 DDP 长期架构）；primary 仍为 FRED，H.10 fallback 已实战触发一次
  （FALLBACK_USED 显式）。X2 5 期 < 250 → WARMUP；FRED 恢复后自动补全历史。
- **P1-6 D3 spike（time-box 内达成）**：PBOC 月度报告存量段含 AFRE 存量+同比、政府债券
  存量+同比 → `derive_private_tsf_yoy` 派生私人社融存量同比（验证值 5.63%，±0.1pp 精度
  已记录）；CN_PRIVATE_TSF_YOY 4 期入库 → **D3 READY**（Spike 结论：可形成稳定自动源）。
- **P1-7 政策利率持久化验证**：PBC OMO 活动公告已持续写入 canonical（replace_window 只
  覆盖抓取窗口，MANUAL 台阶历史保留）；新降息 → update_sources 自动持久化，人工维护 ≈ 0，
  台阶文件仅作历史 bootstrap/emergency fallback。
- **P1-8 G3 活源评估**：OECD IP/Retail 是**指数**（G3 声明链 yoy(12) 消费指数），NBS/东财
  只发布**增速**——切换需改 signals.yaml 输入声明（frozen，须负责人批准）。本轮落地
  OECD replace_window + release-lag 元数据（120 天 STALE 属实保留，不放宽阈值）；
  活源切换决策留待负责人。
- **P2-9 饱和度评审完成**：signal_quality 新增 pre-clip 分布段（p50/p95/max/clip rate）。
  触发 Review：G4（67%）、G5（28%）、D3（100%）——按经济锚点修正 scale：G4 10→15、
  G5 15→20、D3 2→4（macro.yaml 显式 + 注释含 before/after；不涉及资产收益、不改因子权重）。
  修正后 clip rate：G4 11%、G5 21%、D3 0%，全部退出 REVIEW。
- **P1-5 D2/D4 Wind 回填**：依赖用户导出 `wind_backfill_tsf.csv`——**文件未就绪，等待状态**
  （数据链已就绪：PBOC 增量 replace_window 正常，导入回填文件后 D2/D4 立即 WARMUP→READY）。

### V1.6A Market Confirmation（v0.4d）— DONE（2026-08-30，Window D1，已由协调员验收）

**G0：G3 活源切换（负责人 2026-08-30 批准的唯一 signals.yaml 变更）**
- `signals.yaml` G3 inputs 改为声明优先级序列：CN_IND_PROD_YOY（NBS 工业增加值当月同比，
  preferred）→ CN_RETAIL_SALES_YOY（NBS 社零当月同比，preferred）→ CHN_IND_PROD_INDEX /
  CHN_RETAIL_SALES_INDEX（OECD 指数，保留为 fallback，未删除）；`combination: fallback`、
  transforms 由 yoy(12) 改为 level（NBS 序列本身即增速），momentum delta(3) 不变，
  direction/neutral/weights 不变。
- 切换的实证依据：OECD SDMX 工业生产指数存在**基期重编台阶**（2026-05 附近 yoy(12) 给出
  −19.9% 的伪值，而 NBS 官方同比为 +4.5~5.3%）。
- **G3 score 对照（同参照月 2026-05）**：切换前（OECD 指数链）level −0.104 / score **−0.076**；
  切换后（NBS 增速链）level +4.5% / score **+0.078**。最新值（2026-07，NBS）：score +0.133。
  growth 因子 −0.399 → −0.357，Regime 保持 TRANSITION。快照存
  `data/local/g3_before_switch.csv` / `g3_after_switch.csv`。
- macro.yaml G3 scale {level 0.20→20.0, momentum 0.10→10.0}：**纯单位换算（分数→百分数，
  ×100），非重新拟合**，与 G4/G5 的"百分数口径"先例一致。
- 新序列注册：indicators.yaml + data_sources.yaml 增 CN_IND_PROD_YOY / CN_RETAIL_SALES_YOY
  （primary akshare→东财 RPT_ECONOMY_INDUS_GROW / RPT_ECONOMY_TOTAL_RETAIL，
  original_source=NBS；各约 190 期历史入库）。regression test 锁定新声明与引擎优先级语义
  （tests/test_v05a.py::test_g0_*）。

**第一阶段：Market Data Readiness — 6/6 real READY（门槛 ≥5/6 PASS）**

| Market Signal | Provider (primary/fallback) | History 起点 | Frequency | Freshness | READY |
|---|---|---|---|---|---|
| M1 CSI300 | eastmoney push2his(1.000300) / akshare-sina(sh000300) | 2002-01-04 | daily | 2d ok | READY（primary 因本机代理 blocker 走 fallback，FALLBACK_USED 显式） |
| M2 Hang Seng Index | eastmoney push2his(100.HSI) / akshare-sina(HSI) | 2013-08-20 | daily | 2d ok | READY（价格指数非全收益，已声明） |
| M3 China 10Y Yield | chinabond yzQuery / wind_manual | 2023-05-17 | daily | 3d ok | READY（端点仅存 2023-08 起数据，已加深 initial 回填窗口） |
| M4 AAA Credit Spread | chinabond historyQuery / wind_manual | 2007-12-21 | daily | 2d ok | READY（同源派生：中债中票AAA 3Y − 国债 3Y；2026-08-28=0.4157 与调研档案锚点一致） |
| M5 USD/CNY | chinamoney 中间价 / wind_manual | 2016-01-04 | daily | 2d ok | READY（按年分段回填，CcprHisNew 单次跨度≤1年） |
| M6 Copper (LME 3M) | akshare(新浪外盘 CAD) / - | 2016-08-30 | daily | 2d ok | READY（选型理由见下） |

- **M6 选型决策（任务书授权 D1 决定）**：LME 3M 铜（连续 3 个月远期报价，**无主力换月跳空**，
  冻结 transform 白名单直接可用）。SHFE CU0 被否：换月跳空需比例复权 = 新增变换，
  违反本窗口"不新增变换"约束；CCIDX 被否：官网端点未在档案中落地验证且公开历史仅 4 年。
  已声明局限：美元净价（内嵌汇率，M5/X2 覆盖美元维度）、伦敦日历、发布滞后 1 天。
- 新 provider `eastmoney.py`：push2his kline adapter，**显式绕过环境代理**（trust_env=False
  等价物），失败一律 FetchError → updater 走 akshare-sina fallback 并显式标 FALLBACK_USED，
  禁止静默失败（本机 push2his 被代理拦截，与调研档案一致）。
- M4 为 adapter 内同源派生序列（先例：pbc.py derive_private_tsf_yoy）；
  CN_AAA_CREDIT_SPREAD 元数据更正为 daily/percent（fixture 的 AA+产业旧口径未沿用）。

**第二、三阶段：市场信号计算 + Divergence 引擎**
- `config/market.yaml`（新）：逐信号方向约定（M1/M2 positive，M3 negative=收益率下行=
  宽松/牛市方向 v1 声明、M4 negative=利差走阔、M5 negative=USDCNY 上行=人民币贬值、
  M6 positive）、度量基（pct_change / delta in pp）、窗口（1M=21/3M=63/6M=126 obs、
  percentile=250）、6M 方向阈值、macro_reference 因子映射、macro_score 阈值 0.10。
  全部数值为声明先验，加载时显式校验（缺 direction 即报错，禁止隐式假设）。
- `src/macro_compass/market/`（config.py + engine.py）：纯函数市场引擎，复用 transforms
  白名单（apply_chain + rolling_percentile），**未新增任何变换**。输出四元组
  macro_direction（参照因子分数均值过阈值）/ market_direction（6M 趋势过阈值且 3M 不反向；
  1M 与 oriented percentile 仅作报告上下文，从不静默覆盖趋势判定）/ agreement / confidence
  （coverage=历史/窗口、freshness=staleness 预算、source_quality=来源分级——数据质量描述，
  非预测概率）。五状态：CONFIRMED_POSITIVE / CONFIRMED_NEGATIVE /
  POSITIVE_MACRO_DIVERGENCE / NEGATIVE_MACRO_DIVERGENCE / MIXED（命名 = 以未被市场确认的
  宏观方向命名；任一侧中性 → MIXED）。
- **隔离（ARCHITECTURE §10）**：市场层只读 factor 输出；无任何 Fundamental 模块 import
  market 包（源码级测试锁定）+ 行为级测试（计算市场层后 core 计算帧逐位不变）。
- 报告入口 `scripts/market_report.py`：Market Data Matrix + 六信号 1M/3M/6M/percentile +
  divergence 快照；写 `data/local/market_confirmation.csv`。signal_status 的市场层状态改由
  市场引擎解析（READY/WARMUP/MISSING_INPUT，不再显示 DECLARED 占位）。
- macro.yaml confidence.source_quality 增 EASTMONEY: 0.7（聚合商层级，与 AKShare 同级）。
- 当前真实 divergence 快照（2026-08-30）：M5 USD/CNY **CONFIRMED_POSITIVE**（国内金融条件
  宽松 + 人民币走强相互确认）；M6 铜 **NEGATIVE_MACRO_DIVERGENCE**（growth 下行但铜价
  6M +7.4% 处 250 日 100 分位——市场未确认基本面走弱）；M1-M4 MIXED（宏观中性或市场无方向）。


### V2 Asset Compass（v0.5）— DONE（2026-08-30，Window E）

**前置 Gate**：① Economic Coverage Gate 负责人豁免开放（不阻塞）；② V1.6A PASS；③ R2 先验矩阵
调研归档 `docs/research/2026-08-30_R2_asset_prior_matrix.md`。

**资产层交付**：
- `config/assets.yaml`：7 资产池 × 15 Core Signal 先验矩阵转写。头部注释逐条执行 R2→config 5 条
  硬约束（broker 胜率仅支撑 tier、超额流动性按系统 D3 定义、符号约定显式、ambiguous 权重 0、
  两条 V2.5 待检验项声明）。因子 beta = 该因子各信号(sign×tier-weight)带符号之和；tier_weights
  {HIGH 1.0/MEDIUM 0.6/LOW 0.3} 为声明先验（非拟合、非 broker 数值）。派生 beta 已由
  `tests/test_asset_compass.py::test_config_derives_expected_betas` 锁定为回归测试。
- `src/macro_compass/assets/{config,engine}.py`：纯函数引擎。**AssetScore = Σ(βnormalized ×
  factor.score)**，βnormalized 按资产 Σ|β| L1 归一化 → score∈[−1,1]，与因子量纲对齐。
  View=顺风/逆风/中性（阈值 0.15），无任何 BUY/SELL/仓位字样。输出契约 8 字段齐备
  （Score/View/1M/3M change/Factor contribution/Signal contribution/Market confirmation/
  Confidence）；1M/3M change 通过只读复用冻结 `macro.factors.compute_factor` 在
  today−30d/−90d 截断帧重建因子分数，一次预计算供 7 资产共享。
- **全链路可追溯**：Asset→Factor→Signal→series→provider 完整保留在每个输出上。
- **隔离证明**（源码级 + 行为级测试，同 V1.6A 范式）：
  `tests/test_asset_compass.py::test_engine_never_imports_market_and_no_weight_search` 断言
  assets 包不 import market 且无 fit/optimize/lstsq 等权重搜索；行为级测试断言计算资产层后
  factor 结果与输入计算帧逐位不变；`test_market_confirmation_is_parallel_not_scored` 断言
  市场确认并列展示且不影响 Asset Score。
- **ambiguous 项权重 0**（R2 规则 4）：CN_CREDIT G1/G2/G3 与 D2、CN_GOV_BOND I3、GOLD D2，
  由测试锁定；引擎内 signal 分摊仅在资产激活（非零权重）信号之间进行，ambiguous 信号贡献恒 0。
- `scripts/asset_report.py`：7 资产 Score/View/1M/3M/逐因子与逐信号贡献/确认/置信快照，
  写 `data/local/asset_scores.csv`；同 as-of 可与 macro_report/market_report 对齐。
- **当前真实快照（2026-08-30）**：7 资产全部 READY，评分均处 中性 区间（|score|<0.15）：
  GOLD +0.139（最高，domestic 流动性 + growth 下行支撑）、CN_GOV_BOND +0.097、CNY −0.094、
  HK_EQUITY −0.091、INDUSTRIAL_COMMODITY −0.086、CN_EQUITY −0.080、CN_CREDIT −0.058。
  Market confirmation 并列：M6 商品 NEGATIVE_MACRO_DIVERGENCE、CNY CONFIRMED_POSITIVE、
  M1-M4 MIXED、GOLD 无对应市场信号（n/a）。

**R2 转写对照**（config 头部注释 + 本行对照）：每资产每信号 sign/tier 均标注 R2 §出处；
与 R2 摘要矩阵一致，唯一口径调整是按 R2 规则 2/批注 3 明确"超额流动性"以系统 D3 为准。

**V2.5 待检验项（本窗口声明，不在资产层"修平"）**：
1. 黄金对美债 10Y 实际利率 2022-2024 脱钩（央行购金）——GOLD X1 已标 `v25_pending`；
2. 信用债对资金面高敏感（理财赎回负反馈）——CN_CREDIT D1 已标 `v25_pending`；
3. ambiguous 零权单元格（CN_CREDIT G1-G3/D2、CN_GOV_BOND I3、GOLD D2）留待 V2.5
   leave-one-check 检验是否应赋符号。


### V2.5 Historical Validation（v0.6）— DONE（2026-08-30，Window F，60 号任务书）

**只读验证层交付**（全部与生产计算隔离；未重写任何 V1–V2 frozen 组件，验收见 §8 Window F）：
- 新增 `src/macro_compass/validation/` 包：
  - `history.py`：PIT 历史重建。所有声明 transform 均为后向滚动（无中心化），因此按日期
    截断信号帧再经冻结 `macro.factors.compute_factor` 聚合 = 该日期的真实 PIT 因子分数
    （与 V2 自身 1M/3M change 同法）。月频网格上重建 growth/inflation/domestic/global
    因子分数面板 → 按声明 prior beta 的 L1 归一化重建 7 资产分数（同 `assets.engine` 公式）。
    因子覆盖率（当日被计分的非零 β 权重占比）逐日保留，供判读"早期只有部分因子"。
  - `coverage.py`：**Historical Coverage Matrix**（15 Core 全量建档）——各信号输入序列的
    earliest observation / provider / update_policy / revision_risk（full_refresh=HIGH、
    replace_window=MEDIUM、append=LOW，含声明覆盖修正）+ 已声明 breakpoints（OECD
    基期重编、X1 Treasury/FRED 切换前置、G3 NBS 口径切换、G4 累计口径、M4 派生 AAA 3Y
    利差、D3 派生精度、D1 政策利率阶梯序列）+ 每条信号的 minimum_validation_start=PIT
    首次可计分日。外加 **backfill 缺口评估**（Wind 一次性回填候选清单，标注仍缺月份）。
  - `methods.py`：**五方法**（forward returns / score bucket / regime analysis / rolling
    beta / weight robustness）。纯函数、逐资产逐 horizon（1M/3M）输出 verdict
    （statistic / n / adequate / conclusion）。前瞻收益用 canonical 市场序列代理：
    CSI300/HSI/铜为价格收益、USD/CNY 取负、10Y CGB 收益=−ModDur×Δyield（声明 8y）、
    AAA 信用债=−ModDur×Δspread（声明 3.5y，弱代理）——**均为显式近似，非拼接、非 synthetic**。
  - `lomo.py`：**Leave-One-Mechanism-Out**（逐因子逐机制剔除，重算因子/资产分数，测
    factor stability + min asset stability + max forward-separation delta）。候选门控为
    纯函数 `lomo_candidate`：样本不足（n<60）或机制自身计分日期占比 <50%（刚接入）或
    因子不稳定或分离度移动 >0.05 一律不判候选——**杜绝把样本不充分误当"有效/无效"结论**。
  - `regime_checks.py`：两条 R2 待检验项专门检验（见 §10 结论）。
  - `report.py` / `scripts/validation_report.py`：输出总览 + 落盘 `data/local/validation_*.csv`。
  测试：`tests/test_validation.py`（11 个，纯函数 on synthetic，无网络、不污染 canonical）。

**关键发现（如实，结论=样本不足，非"有效/无效"）**：
- **四因子完整资产分数量纲仅约 21 个月（~2024-12 起）**：growth/inflation/global 因子虽有
  2006+ 长历史，但 **domestic_financial 因子直到 2024-12 才有 D1 可计分**（D1 差分子需
  DR007[2017]+ 政策利率[2024] 双腿齐备），导致 2015–2024 的资产分数缺 domestic 腿
  （覆盖率 ~0.65–0.86）。远低于负责人最低样本（2012/2015–present）。
- **五方法**：在部分覆盖率下以 NO_EFFECT_OR_WEAK 为主（47/63 达 n≥60 的样本条，但
  属探索性）；唯一 borderline 反向 CN_CREDIT 3m rho≈−0.17。weight_robustness 全部
  WEIGHT_ROBUST（~0.98–0.99，prior 权重对方案扰动稳健）。
- **LOMO**：早见 **growth:G3（硬活动）** 为唯一低增量候选（因子稳定 0.97、分离度移动 0.044）。
  **仅建议，未降级**；G2/G4/X2（刚接入）与 D2/D4（样本不足）已正确排除出候选。
- **回归检验**：黄金实际利率脱钩 **DATA_BLOCKED**（real canonical 无 GOLD 现货——现有
  GOLD 36 行为 synthetic 已隔离；且 X1 仅 2024 起，故 2022 断点不可观测 → 加入回填）；
  信用债资金面敏感 **INSUFFICIENT_SAMPLE**（D1 历史仅 ~19 对齐样本）。


### V1.5B Signal Engine + V1.5C Macro Factor Engine — DONE（2026-08-29，Window C）
- `src/macro_compass/signals/engine.py`（V1.5B）：纯函数信号计算。读 registry 声明 +
  canonical 输入序列，输出 ARCHITECTURE §8 十列契约
  （signal_id/date/level/level_score/momentum/momentum_score/score/freshness/coverage/status）。
  score = level_weight×level_score + momentum_weight×momentum_score（权重来自
  signals.yaml，缺分量时按现有权重重归一，不静默补 0）。
- 组合语义（均可解释，单一输入/single、优先级 fallback、difference 先减后变换、
  多输入 average 逐输入过链后等权平均）：composite 必附 contribution breakdown——
  average 为可加分数点（Σ=score），difference 为原始复合值的符号化占比（±系数/|legs|和）。
- score 映射（basis→[-1,1]）无黑箱：rolling_percentile → 2×(basis−neutral)；
  robust_zscore → clip(±3)/3（macro.yaml zscore_clip）；其余 basis → basis/scale
  （scale 逐信号声明在 macro.yaml score_mapping.scales，先验手定、非数据拟合）；
  direction: negative 信号分数取反，score>0 恒表示机制改善。
- `src/macro_compass/macro/`（V1.5C）：factors.py 只读 Signal 输出（无 raw series 路径，
  有源码级测试守护）——factor score = 配置权重加权（macro.yaml factor_weights，默认等权）、
  Breadth=支持当前方向的机制数（非序列条数，breadth_min_score 门槛）、
  Confidence=coverage/freshness/source_quality 三分量等权（来源分级读
  data_sources.yaml 路由的 max_staleness_days + macro.yaml source_quality 分级）；
  regime.py 仅由 growth×inflation 两轴驱动，判定顺序 NO_SIGNAL → LOW_CONFIDENCE
  → TRANSITION → 四象限 → MIXED（breadth 不足），阈值全在 macro.yaml regime 段。
- `scripts/macro_report.py`：人工验收主入口，一次输出 15 core signal 快照
  （status/provenance/score/level/momentum/freshness/coverage/breakdown/missing）、
  四 factor（score+breadth+confidence 分解+逐 signal 追溯 Factor→Signal→series→source）、
  regime 及判定依据；写快照 CSV `data/local/signal_scores.csv`。
  synthetic 与 real 可区分：canonical 行 source_file 命中 macro.yaml
  synthetic_markers（wind_macro_sample）即标 SYNTHETIC，混合为 MIXED。
- 顺手修复 Known Issue：tests/test_ingestion.py 改为生成 fixture 到 tmp_path
  （generate_fixtures.main() 新增可选 output_dir 参数），跑 pytest 不再弄脏工作区。
- 当前真实数据快照（2026-08-29）：growth score −0.118（G1/G3/G5，breadth 1），
  inflation/domestic/global 无可计算信号 → REGIME: NO_SIGNAL；I1/D3 为 PARTIAL
  但不可计算（I1 fallback 数据 36 月 < percentile 窗口 60；D3 difference 缺一条腿），
  均显式 null score。数据为 real（OECD）+ synthetic（WIND fixture）混合状态，报告中已标注。

## 2. Canonical 最小契约

```text
series_id / date / value / source / source_file / import_time
```
扩展字段：series_name, unit, frequency, category, file_hash（provider 数据 file_hash 为空，
source 记为 provider 大写，如 OECD / NYFED / PBC / CHINAMONEY）。

## 3. 当前架构

```text
[Source Adapters (data_sources/*)]  [Wind Manual Importer]
        ↓                               ↓
   Canonical Parquet（真源，macro/market 分区）
        ↓
   DuckDB（可重建缓存）+ fetch_state.json + status CSVs
        ↓
   Transform（transforms/*，纯函数白名单）  ← V1.5A frozen
   Signal Registry（signals/registry.py）  ← V1.3 frozen
   Signal Engine（signals/engine.py）      ← V1.5B
        ↓  （只读 Signal 输出，禁止跳回 raw series）
   Macro Factor Engine（macro/factors.py + regime.py）  ← V1.5C
        ↓  （factor 输出，只读）
   Market Confirmation（market/config.py + market/engine.py）  ← V1.6A
        ↓
   （Asset Mapping 属 V2，未开发）
```

市场层隔离：`market/*` 只读 canonical 市场序列与 factor 输出；Fundamental 模块
不 import market 包（测试锁定），市场结果永不反向修改任何 Fundamental Score。

## 4. 当前 README 已定义命令

```bash
python scripts/generate_fixtures.py
python scripts/import_wind.py data/fixtures/wind_macro_sample.xlsx --dry-run
python scripts/import_wind.py data/fixtures/wind_macro_sample.csv
python scripts/rebuild_db.py
python scripts/check_quality.py
python scripts/update_sources.py [--dry-run | --series ID | --backfill]
python scripts/overlap_check.py --series S --left P1 --right P2   # 双源重叠检验
python scripts/signal_status.py
python scripts/transform_smoke.py [--signal ID | --series ID | --rows N]
python scripts/macro_report.py [--today YYYY-MM-DD]   # V1.5C 宏观快照（验收主入口）
python scripts/signal_quality.py                      # V1.5D 信号质量诊断（saturation/warmup）
python scripts/market_report.py [--today YYYY-MM-DD]  # V1.6A 市场确认层快照（Matrix+divergence）
python -m pytest          # 192 passed（network 测试默认跳过，-m network opt-in）
python -m pytest -m network
```

## 5. Frozen Components

- V1 全部冻结组件（Wind importer、normalizer/validator、raw archive、SHA256 去重、
  canonical Parquet、DuckDB 缓存、质量检查、synthetic fixtures、pytest 基础）——
  V1.2/V1.3 均未重写，仅扩展。
- V1.2 冻结（后续版本只扩展不重写）：
  - `data_sources/base.py` 错误契约（FetchError / ProviderUnavailable / ManualFetchRequired）
  - `data_sources/updater.py` 状态语义（OK/STALE/FAILED/FALLBACK_USED/MANUAL_REQUIRED）
  - `config/data_sources.yaml` schema（defaults/providers/series 三段）
  - canonical 元数据以 `indicators.yaml` 为唯一真源（updater 富化，adapter 不带 name/unit）
- V1.3/V1.5A 冻结（Window C 只扩展不重写）：
  - `config/signals.yaml` 的 15+6+3 信号声明与字段语义（mechanism/factor/inputs/
    transforms/neutral/weights）；新增 Core Signal 须证明新经济机制
  - `transforms/` 的 12 种白名单与纯函数契约（pipeline 的 `fill` 显式语义）
  - `signals/registry.py` 的校验规则与 READY/PARTIAL/MISSING_INPUT/DECLARED 状态语义
  - indicators.yaml 为 series 元数据唯一真源；signals.yaml 只引用 series_id
- V1.5B/V1.5C 冻结（Window D 只扩展不重写）：
  - `signals/engine.py` 的输出契约（ARCHITECTURE §8 十列）与 score 映射规则
    （percentile/zscore/scale 三类规则 + direction 取反；scale 数值可调，规则本身不改）
  - 组合语义：single / fallback（preferred→fallback 声明顺序）/ difference（先减后变换）/
    average（逐输入过链后等权平均）及 contribution breakdown 口径
  - `macro/factors.py` 只读 Signal 输出的硬约束与 Breadth/Confidence 语义
    （Confidence 是数据质量描述，不是预测概率）
  - `macro/regime.py` 判定顺序（NO_SIGNAL → LOW_CONFIDENCE → TRANSITION → 象限 → MIXED）
  - `config/macro.yaml` schema（score_mapping/factor_weights/confidence/regime/
    synthetic_markers 五段）；数值是先验，调整不改结构

- V1.6A 冻结（后续版本只扩展不重写）：
  - `config/signals.yaml` 的 G3 新声明（NBS 增速 live + OECD fallback、
    combination: fallback、level 链）——此为负责人授权的唯一 signals.yaml 变更
  - `config/market.yaml` schema（signals 段五键 + thresholds.macro_score）；
    方向约定/窗口/阈值是声明先验，加载时显式校验
  - `market/engine.py` 的度量口径（1M/3M/6M=21/63/126 obs、percentile=250、
    direction-adjusted、oriented percentile）与五状态命名规则
    （以未被确认的宏观方向命名 divergence；任一侧中性 → MIXED）
  - 市场层单向隔离：`market/*` 只读 factor 输出；Fundamental 不得 import market；
    Divergence 永不翻译成买卖信号
  - M4 利差口径：中债中票AAA 3Y − 国债 3Y（historyQuery 同源派生）；
    M6 口径：LME 3M 铜（无换月跳空）；改变口径须负责人批准

- V2 Asset Compass 冻结（后续只扩展不重写）：
  - `config/assets.yaml` 的 7 资产 × 15 信号先验矩阵（sign/tier/tier_weights/beta_range/
    market_signal/defaults）——R2 转写与 5 条硬约束；改符号/权重须负责人批
  - `assets/engine.py` 的计分口径：AssetScore = Σ βnormalized × factor.score（只读 factor/
    market 输出）、β L1 归一化到 [−1,1]、View=顺风/逆风/中性、1M/3M change 截断重建、
    市场确认为并列观察（不入评分）、Confidence 三分量数据质量语义
  - 资产层单向隔离：只读 macro/market 输出，无任何 Asset→Factor/Market 反向流；
    不 import market 包；不改 freeze 的 V1–V1.6A

## 6. 当前未开发

- Structural Risk 引擎（V2.6；registry 中已占位）
- Streamlit Dashboard（V3）/ Cloud Mirror（V4）

## 7. 下一任务

> **V2.6 Structural Risk（下一窗口，65 号任务书 + 66 号数据调研已就绪）**：V2.5 已完成，
> 按负责人路线 V2→V2.5→**V2.6 Structural Risk**→V3。B 包调研档案已归档
> `docs/research/2026-08-30_data_layer_round2_validation.md` / 66 号任务书。
>
> **V2.5 前置回填待办（登入 backfill gaps，不阻塞 V2.6，但决定 V2.5 再验证质量）**：
> wind_backfill_tsf.csv（D2/D4）、PMI 新订单/购进价格、核心 CPI、房地产历史、政策利率历史、
> USD_BROAD、real 黄金现货 + 2022 前 10Y 实际利率（供 GOLD 脱钩检验）——均走既有
> Wind manual import 链，无新爬虫。
>
> **V2.5 交付对接（已完成 · 本窗口）**：60 号任务书 10 条 Acceptance Criteria 见 §8
> Window F 自查与结论。
>
> **协调职责延续（2026-08-30 起）**：工作手册见 **docs/COORDINATOR_HANDOFF.md**
> （含验收程序、待办队列、后续任务书素材与红线清单）。

## 8. 窗口交接记录（2026-08-30 V1.6A / v0.4d，Window D1）

```text
Last Test Result: PASS（python -m pytest，2026-08-30；-m network opt-in 6 passed 2 skipped，
  skip 为 FRED 与 eastmoney push2his 两个已知环境 blocker 的如实行为）
Last Test Count: 192 passed, 0 failed（176 基线 + 16：G0 声明/优先级/scale 锁定 3 +
  eastmoney/spread 解析器 4 + 市场约定/WARMUP/五状态/confidence/隔离 8 + 更新后的
  registry 可用性断言 1）
Last Git Tag: v0.4d-market-confirmation（协调员将 D1 窗口自打的 v0.5 重命名——v0.5 预留给 V2 Asset Compass，见 COORDINATOR_HANDOFF §8 第 10 步）
Known Issues: 见第 10 节
Modified Files: 新增 src/macro_compass/market/{__init__,config,engine}.py、
  data_sources/eastmoney.py、scripts/market_report.py、tests/test_v05a.py、
  config/market.yaml；修改 data_sources/{akshare_source,chinabond,chinamoney}.py
  （新浪指数/外盘路由、historyQuery 利差、按年分段回填）、signals/status.py
  （market 层状态解析，向后兼容）、scripts/signal_status.py、paths.py、
  config/signals.yaml（仅 G3）、config/indicators.yaml（+2 NBS 序列、M4 元数据更正）、
  config/data_sources.yaml（eastmoney provider + 市场序列路由 + chinabond/初始窗口）、
  config/macro.yaml（G3 scale 单位换算、EASTMONEY 评级）、
  tests/test_signal_registry.py（G3 可用性断言随授权变更更新）、README
```

### 窗口交接记录（2026-08-30 V2 Asset Compass / v0.5，Window E）

```text
Last Test Result: PASS（python -m pytest，2026-08-30）
Last Test Count: 205 passed, 0 failed（192 基线 + 13：V2 资产层 config/引擎/隔离/转写 13）
Last Git Tag: v0.5-asset-compass（协调员验收通过后打标，2026-08-30）
Known Issues: 见第 10 节（V2 新增局限见下）
Frozen 检查：V1/V1.2/V1.3/V1.5/V0.4c/V1.6A frozen components 未被重写（仅 paths.py 增 2 行常量）
Modified Files: 新增 config/assets.yaml、src/macro_compass/assets/{__init__,config,engine}.py、
  scripts/asset_report.py、tests/test_asset_compass.py；修改 src/macro_compass/paths.py、
  docs/01_CURRENT_STATE.md、README.md

协调员验收（2026-08-30）：55 号任务书 11 条 Acceptance Criteria 全部 PASS；
6 条红线全绿（测试全过、无越权、无反向流、无 synthetic 进 production、无 silent
fallback、Known Issues 有 blocker 分类）。tag v0.5-asset-compass 已打。
```

## 9. 每次窗口结束必须更新

- Current Version / Completed / Tests / Known Issues / Frozen Components / Next Task / Git

## 10. Known Issues（V1.6A 结束时已知）

### Economic Coverage Gate（Fundamental Core）

- D2/D4（WARMUP→READY 的最后一步）：**等待用户人工导出 `wind_backfill_tsf.csv`**
  （Total TSF Flow + Government Bond Financing Flow，≥60 个月）。文件就绪后一次导入
  即转 READY；未就绪期间保持 WARMUP（真实 PBOC 增量已按月流入），
  **禁止用其他来源凑数**。
  **协调员核实（2026-08-30）**：v0.4c"导入链已就绪"仅指 PBOC 增量路由；
  `config/wind_mapping.yaml` **尚无社融/政府债券列映射**（CN_TSF_TOTAL /
  CN_GOV_BOND_FINANCING 在 indicators.yaml 与 data_sources.yaml 均已注册，
  但 Wind 导出列名未映射）——文件到达后需先按用户导出列名补 wind_mapping.yaml
  再走 import_wind.py，否则导入会因无映射被拒。
- X2（WARMUP）：FRED DTWEXBGS **network blocker**；H.10 fallback 已实战工作，
  FRED 恢复后 update 自动补全历史 → READY。
- X1 overlap check **BLOCKED**（同 FRED 网络）：`scripts/overlap_check.py` 已 armed，
  必须在 FRED 行并入 US_REAL_YIELD_10Y 前 PASS（≥60 共同交易日）。

### V1.6A 市场层遗留与限制（如实记录）

- **G3 OECD fallback 条目为"声明保留"性质**：OECD 指数序列与 NBS 增速序列单位不同
  （指数 vs 百分比），G3 现声明链（level）只匹配 NBS 增速；两个 OECD 条目仅当 NBS 双腿
  完全无数据时才会被 fallback 选中（届时 level 基底不是增速，需负责人重新决策口径），
  正常运行永不触发。
- **M1/M2 primary（东财 push2his）在本机被代理拦截**：每次 update 均走 akshare-sina
  fallback 并显式标 FALLBACK_USED（非静默）；代理恢复后 primary 自动生效。
- **M3 历史起点 2023-05**：chinabond yzQuery 端点本身只存 2023-08 起数据（本轮已验证），
  非抓取缺陷；如需 2006 起的 10Y 历史，可后续改走 historyQuery（同源已验证），须负责人批准。
- **M6 口径局限**：LME 3M 为美元净价（内嵌汇率）且伦敦日历（发布滞后 1 天、节假日与
  中国日历不对齐——各市场信号各自按自身交易日计算，不做跨日历对齐）；铜价与 X2 美元
  因子存在机械负相关，解读时注意。
- **M3 方向约定局限（v1 声明）**：收益率下行=宽松/牛市方向；收益率下行若源于增长恶化
  预期而非宽松，方向语义会失真——报告同时展示 raw basis 与 oriented percentile 以便
  人工判读。
- **ChinaMoney WAF 限流**：本轮实测 CcprHisNew 与 ClsYldCurvHis 均存在突发 403；
  parity 回填已按年分段+休眠，日常增量窗口小、风险可控。
- **Divergence 阈值未经历史检验**：market.yaml 的 trend_6m/macro_score 阈值是声明先验
  （V2.5 Historical Validation 才允许回测），当前只保证语义可解释、可追溯。

### V2 Asset Compass 局限与未决项（2026-08-30，如实记录）

- **因子 score 为宏观层整体值**：资产 Score = Σ β_normalized × factor.score，factor.score 由
  该因子全部 Core Signal（宏观权重）算出；资产的 signal 级贡献按"激活信号集"重分 apportion，
  因此 CN_CREDIT 等将部分 growth 信号标为 ambiguous（权重 0）的资产，其 growth 贡献会被
  摊到剩余激活信号（G4/G5）上——语义上"该因子增长贡献归因于 G4/G5"，非 G1-G3 传导，已注释。
- **1M/3M change 依赖 frame 历史长度**：通过截断帧重建因子分数；若信号历史不足
  （WARMUP 如 D2/D4/X2），其因子在该 horizon 分数为 None，change 相应缺失。
- **View 全为中性**：当前真实宏观环境（Regime TRANSITION）下 7 资产 |score|<0.15 全部中性；
  属当前环境的如实输出，非缺陷；阈值 0.15 为声明先验，V2.5 前不改。
- **市场确认非 1:1**：GOLD 无对应 M 信号，market_signal=null（n/a）；其余按 8 字段并列展示。
- **V2.5 待检验**（见第 1 节 V2 小节 + config/assets.yaml `v25_pending`）：黄金实际利率脱钩、
  信用债资金面高敏感、ambiguous 零权单元格是否应赋符号。

### V2.5 Historical Validation 局限与限制（2026-08-30，如实记录）

- **样本核心限制**：四因子完整资产分数量纲仅约 21 个月（~2024-12 起，D1 历史不足）。
  growth/inflation/global 虽有 2006+ 历史，但 2015–2024 资产分数缺 domestic 腿——五方法
  在部分覆盖率上的"NO_EFFECT_OR_WEAK"**非强证伪**，属探索性。
- **前瞻收益均为代理，非资产真实收益**：股票/铜=价差收益、债券=−ModDur×Δyield（8y）、
  AAA 信用=−ModDur×Δspread（3.5y，弱代理）、GOLD 仅 synthetic（无真实现货）。
- **黄金脱钩 DATA_BLOCKED**：real canonical 无 GOLD 现货、X1 仅 2024 起，2022 断点不可观测
  → 须回填 pre-2022 gold + 10Y 实际利率后才能再验证。
- **信用债资金面敏感 INSUFFICIENT_SAMPLE**：D1 对齐样本 ~19，样本不足判断。
- **LOMO candidate=growth:G3 仅为建议**：未经负责人批准，任何 Core 均未降级；G2/G4/X2
  （刚接入）、D2/D4（样本不足）已排除出候选，勿过度解读为"有效"。
- **结论边界**：本窗口的"（暂时）不能验证"是数据覆盖问题的如实结果，不是模型能力的否定；
  也不代表 60 样本线是统计保证，all 结论均为工程/探索级判断而非统计显著性。

### 其他（沿袭）

- 测试污染工作区（V1.3 遗留）：已修复（V1.5B/C 窗口），data/fixtures/ 保持只读。
- V1.2 既有 Known Issues（FRED 间歇超时、AKShare/代理间歇不可用、ChinaMoney WAF 限流、
  check_quality 混频警告）继续有效，见 git 历史 V1.2 交接记录。
- data/manual_series/CN_POLICY_RATE_7D.csv 仅作历史 bootstrap/emergency fallback；
  PBC OMO live 路由已验证自动持久化（v0.4c P1-7）。
- AKShare 1.18.94；其接口变更风险（如 repo_rate_hist 仅支持 ≤2 个月区间）已封装在 adapter 内。
- 引擎输出契约 WARMUP 状态（V1.5D）；ARCHITECTURE §8 十列契约不变。
