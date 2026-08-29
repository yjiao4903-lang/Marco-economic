# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-30  
**Current Version:** V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate（V0/V1/V1.2/V1.3/V1.5A/V1.5B/V1.5C 已冻结）  
**当前阶段：** 两个数据质量 Gate 完成。Core REAL-computable 9/15（Growth 5/5、Inflation 2/3、
Domestic 1/4、Global 1/3），Regime 首次输出真实状态（TRANSITION）。Gate A 覆盖目标 12/15 **未达成**，
缺口全部为如实记录的 blocker（见 §10），未用 synthetic/缩窗/放宽阈值补水分。
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
python scripts/signal_status.py
python scripts/transform_smoke.py [--signal ID | --series ID | --rows N]
python scripts/macro_report.py [--today YYYY-MM-DD]   # V1.5C 宏观快照（验收主入口）
python scripts/signal_quality.py                      # V1.5D 信号质量诊断（saturation/warmup）
python -m pytest          # 163 passed（network 测试默认跳过，-m network opt-in）
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

> V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate（Gate A/B，原 Window C 继续，
> 见 docs/tasks/45_V1_2C_V1_5D_DATA_QUALITY_GATES.md）
>
> 路线图变更（项目负责人 2026-08-29 批准）：V1.6+V2 暂缓，先补真实数据覆盖与信号质量；
> 完成后进入 V1.6A Market Confirmation → V2 Asset Compass，Structural Risk 后移为 V2.6。

## 8. 窗口交接记录（2026-08-29 V1.5B+V1.5C）

```text
Last Test Result: PASS（python -m pytest，2026-08-30；另有 -m network opt-in 通过）
Last Test Count: 163 passed, 0 failed（137 基线 + 26：cumulative/parsers/manual/policy/
  isolation/WARMUP/saturation）
Last Git Tag: v0.4b-data-quality
Known Issues: 见第 10 节（Gate A 覆盖 9/15 未达 12/15，缺口与 blocker 分类）
Modified Files: 新增 src/macro_compass/data_sources/{cumulative,nbs,manual_series}.py、
  src/macro_compass/synthetic_guard.py、scripts/signal_quality.py、
  data/manual_series/CN_POLICY_RATE_7D.csv、tests/test_data_quality_gates.py；
  修改 data_sources/（chicagofed/nyfed/chinamoney/chinabond/pbc/akshare/registry/updater）、
  storage/canonical_store.py（replace_window/replace_series）、
  signals/engine.py（WARMUP）、config/data_sources.yaml（全量路由重写）、
  config/macro.yaml（scale 修正）、scripts/{macro_report,signal_status}.py、
  tests/data_sources/conftest.py、test_parsers.py、paths.py、README
```

## 9. 每次窗口结束必须更新

- Current Version / Completed / Tests / Known Issues / Frozen Components / Next Task / Git

## 10. Known Issues（V1.2C/V1.5D 结束时已知）

### Gate A 覆盖缺口（9/15 vs 12/15 目标，blocker 分类如实记录）
- X1/X2（US_REAL_YIELD_10Y / USD_BROAD）：**network blocker**——FRED 在本机网络间歇可达
  （本窗口曾一次成功，其余全部 read timeout，curl 同样失败；endpoint 本身已验证正确）。
  网络恢复后 `python scripts/update_sources.py` 自动补齐，代码无需改动。
- D2/D4（TSF/政府债券融资）：**history warmup**——数据链已打通（PBOC 月度金融统计数据报告，
  累计差分为月度流量，replace_window），但报告列表页仅静态暴露最近 ~4 个月（更早月份的
  列表页为 JS 渲染），yoy(12) 需 13 期 → 每月随报告累积，约 9 个月后自动转 READY。
  累计差分的历史回填需后续扩展（gov.cn 镜像或 manual 档案），本轮未做。
- D3：**source blocker**——CN_PRIVATE_TSF_YOY 无自动源（派生需社融存量与政府债券存量
  月度历史，存量表 JS 渲染不可爬）；保持 PARTIAL + null score。
- I1：**source blocker（弱）**——核心 CPI 同比只出现在 NBS「数据解读」栏目，标题含作者名
  不稳定；NBS 发布页路由已配置，出现可解析文章即自动入库；当前 MISSING（synthetic
  fallback 已被 production 隔离，属预期行为）。
- CSI300：**environment blocker**——本机代理对 eastmoney push2 间歇不可用（V1.2 既有问题，
  market 层非本轮 Gate 范围）。

### 其他

- 测试污染工作区（V1.3 遗留）：已修复（V1.5B/C 窗口），data/fixtures/ 保持只读。
- V1.2 既有 Known Issues（FRED 间歇超时、AKShare/代理间歇不可用、ChinaMoney WAF 限流、
  check_quality 混频警告）继续有效，见 git 历史 V1.2 交接记录；本轮 FRED timeout 45→90s
  + updater 一次重试已缓解但未根除。
- data/manual_series/CN_POLICY_RATE_7D.csv 为人工转录的官方利率台阶（MANUAL 来源），
  PBOC OMO 路由为 primary 会持续以真实公告覆盖近 20 个交易日；台阶文件的后续维护
  （新降息时追加台阶）是已知人工维护点。
- AKShare 于本窗口已安装（1.18.94），P3 兜底路由已激活；其接口变更风险（如 repo_rate_hist
  仅支持 ≤2 个月区间、分块抓取）已封装在 adapter 内。
- 引擎输出契约新增 WARMUP 状态（V1.5D）；ARCHITECTURE §8 十列契约不变。
