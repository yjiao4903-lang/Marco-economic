# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-30（v0.4c）  
**Current Version:** V1.5E Pre-Market Stabilization（v0.4c；V0–V1.5D 全部冻结）  
**当前阶段：** Core **READY 12/15**（Growth 5/5、Inflation 3/3、Domestic 2/4、Global 2/3），
WARMUP 3（D2/D4 等用户 Wind 回填文件、X2 等 FRED 网络恢复——真实数据均已流入）。
Economic Coverage Gate（Growth 5/5 + Inflation 3/3 + Domestic ≥3/4 + Global 3/3）**未完全达成**：
Domestic 差 1（等待 wind_backfill_tsf.csv）、Global 差 1（X2 历史，FRED 网络阻塞）。
Regime = TRANSITION（growth -0.399 ↓，inflation -0.031 中性带）。
下一窗口进入 V1.6A Market Confirmation。

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
        ↓
   （Asset Mapping 属 V2，未开发）
```

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
python -m pytest          # 176 passed（network 测试默认跳过，-m network opt-in）
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

## 6. 当前未开发

- Market Confirmation / Structural Risk 引擎（V1.6；registry 中已占位）
- Asset Compass / Historical Validation / Streamlit Dashboard / Cloud Mirror

## 7. 下一任务

> V1.6A Market Confirmation（新窗口 Window D1，见 docs/tasks/50_V1_6A_MARKET_CONFIRMATION.md；
> R2 资产先验矩阵调研已完成并归档 docs/research/2026-08-30_R2_asset_prior_matrix.md）
>
> v0.4c 已交付（tag v0.4c-pre-market-stable，12/15 READY）。Economic Coverage Gate
> **有条件待完成**：D2/D4 等待用户上传 wind_backfill_tsf.csv（用户已确认数据可取得，
> 建议同时包含社融存量两列以加固 D3；数据链已就绪，导入即转 READY）、
> X2 等 FRED 网络恢复自动补全历史、X1 overlap check 已 armed 待 FRED 恢复后执行。
>
> **负责人已批准（2026-08-30）**：G3 活源切换（OECD→NBS 增速序列为 live，
> OECD 保留历史/兜底）——授权 Window D1 作为 G0 预置任务修改 frozen signals.yaml，
> 这是唯一被授权的 signals.yaml 变更。上述全部完成后冻结 Fundamental Core。

## 8. 窗口交接记录（2026-08-30 V1.5E / v0.4c）

```text
Last Test Result: PASS（python -m pytest，2026-08-30；另有 -m network opt-in 通过）
Last Test Count: 176 passed, 0 failed（163 基线 + 13：共享状态/Treasury与H.10解析/
  核心CPI表格/私人社融派生/fallback历史偏好/overlap比较）
Last Git Tag: v0.4c-pre-market-stable
Known Issues: 见第 10 节（Gate A 覆盖 9/15 未达 12/15，缺口与 blocker 分类）
Modified Files: 新增 data_sources/{treasury,fedh10}.py、signals/status.py、
  scripts/overlap_check.py、tests/test_v04c.py；修改 signals/engine.py（fallback
  历史偏好）、signals/__init__.py、scripts/{signal_status,macro_report,signal_quality}.py
  （统一走 load_core_computations）、data_sources/pbc.py（D3 派生）、
  config/data_sources.yaml（treasury/fed_h10/private_tsf 路由 + OECD/ANFCI
  replace_window + freshness）、config/macro.yaml（G4/G5/D3 scale 修正）、README
```

## 9. 每次窗口结束必须更新

- Current Version / Completed / Tests / Known Issues / Frozen Components / Next Task / Git

## 10. Known Issues（V1.2C/V1.5D 结束时已知）

### Economic Coverage Gate 缺口（12/15 READY vs 14/15 理想）
- D2/D4（WARMUP→READY 的最后一步）：**等待用户人工导出 `wind_backfill_tsf.csv`**
  （Total TSF Flow + Government Bond Financing Flow，≥60 个月）。导入数据链已就绪，
  文件就绪后一次导入即转 READY；未就绪期间保持 WARMUP（真实 PBOC 增量已按月流入），
  **禁止用其他来源凑数**（任务书协调员补充 3）。
- X2（WARMUP）：FRED DTWEXBGS **network blocker**（本窗口 9+ 次尝试全部超时）；
  H.10 fallback 已实战工作（当前周 5 期），FRED 恢复后 update 自动补全历史 → READY。
- X1 overlap check **BLOCKED**（同 FRED 网络）：`scripts/overlap_check.py` 已 armed，
  必须在 FRED 行并入 US_REAL_YIELD_10Y 前 PASS（≥60 共同交易日）；当前 canonical 中
  该序列只有 Treasury 单源，无混源风险。
- G3 活源切换（OECD→NBS 增速）需改 frozen signals.yaml 输入声明——**待负责人决策**；
  本轮已加 OECD replace_window + release-lag 元数据，STALE 如实保留。

### 其他

- 测试污染工作区（V1.3 遗留）：已修复（V1.5B/C 窗口），data/fixtures/ 保持只读。
- V1.2 既有 Known Issues（FRED 间歇超时、AKShare/代理间歇不可用、ChinaMoney WAF 限流、
  check_quality 混频警告）继续有效，见 git 历史 V1.2 交接记录；本轮 FRED timeout 45→90s
  + updater 一次重试已缓解但未根除。
- data/manual_series/CN_POLICY_RATE_7D.csv 仅作历史 bootstrap/emergency fallback；
  PBC OMO live 路由已验证自动持久化（v0.4c P1-7），新降息无需人工追加。
- AKShare 于本窗口已安装（1.18.94），P3 兜底路由已激活；其接口变更风险（如 repo_rate_hist
  仅支持 ≤2 个月区间、分块抓取）已封装在 adapter 内。
- 引擎输出契约新增 WARMUP 状态（V1.5D）；ARCHITECTURE §8 十列契约不变。
