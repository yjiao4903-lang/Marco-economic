# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-29  
**Current Version:** V1.3 Signal Registry + V1.5A Transform Engine（V0/V1/V1.2 已冻结）  
**当前阶段：** V1.3 + V1.5A 已完成并通过验收，下一窗口进入 V1.5B/V1.5C（Window C，Macro Engine）。

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
   Transform（transforms/*，纯函数白名单）  ← V1.5A
   Signal Registry（signals/registry.py）  ← V1.3（仅注册+校验+可用性，无打分）
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
python -m pytest          # 100 passed（network 测试默认跳过）
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

## 6. 当前未开发

- Signal 打分 / Level+Momentum 组合 / composite 聚合（V1.5B，Window C）
- Macro Factor Engine：Growth / Inflation / Domestic Financial / Global Financial
  聚合、Breadth、Confidence、Regime（V1.5C，Window C）
- Market Confirmation / Structural Risk 引擎（V1.6；registry 中已占位）
- Asset Compass / Historical Validation / Streamlit Dashboard / Cloud Mirror

## 7. 下一任务

> V1.5B Signal Engine + V1.5C Macro Factor Engine（见 docs/tasks/40_V1_5B_V1_5C_MACRO_ENGINE.md）

## 8. 窗口交接记录（2026-08-29 V1.3+V1.5A）

```text
Last Test Result: PASS（python -m pytest，2026-08-29）
Last Test Count: 100 passed, 0 failed（baseline 50 + 新增 50：transforms 33 +
  signal registry 14 + 全局 3；另有 6 个 network 测试 opt-in 未计入）
Last Git Tag: v0.4a-signal-foundation
Known Issues: 见第 10 节
Modified Files: 新增 config/signals.yaml、src/macro_compass/signals/、
  src/macro_compass/transforms/、scripts/transform_smoke.py、
  scripts/signal_status.py、tests/test_transforms.py、tests/test_signal_registry.py；
  修改 config/indicators.yaml（迁移+补注册）、src/macro_compass/config.py（FACTORS 扩展
  +quarterly frequency）、src/macro_compass/paths.py（SIGNALS_YAML/MISSING_SERIES_CSV）、
  tests/test_ingestion.py（1 行断言随 level_gap→neutral_gap 迁移）、README
```

## 9. 每次窗口结束必须更新

- Current Version / Completed / Tests / Known Issues / Frozen Components / Next Task / Git

## 10. Known Issues（V1.3 结束时已知，不阻塞 V1.5B）

- V1.3 遗留数据缺口：15 个 Core Signal 中 10 个缺全部输入、2 个缺部分输入（见第 1 节）。
  X1/X2/X3（FRED 不可达、Chicago Fed URL 未配置）在 V1.2 已列 manual list，网络恢复后
  `python scripts/update_sources.py` 自动补上；其余（DR007/TSF/PPI/GSCPI/房地产销售等）
  需后续窗口扩展 provider 或走 Wind manual，V1.3 未新增任何数据源（任务禁止）。
- indicators.yaml factor 分类现状：Core 信号输入已统一到 MASTER SPEC 四因子；
  仅服务 Market Confirmation 的序列（CN_GOV_YIELD_10Y=rates、CN_CREDIT_SPREAD/
  CN_AAA_CREDIT_SPREAD=credit、USD_CNY=fx）保留 legacy 标签——MASTER SPEC 未对
  Market 层定义因子分类，V1.6 实现时再定。
- `config.py` 的 FREQUENCIES 新增 quarterly（仅 S1/S2 的 BIS 季频序列使用）；
  data_sources.yaml 的频率字段未放开 quarterly（这两条序列无 provider 路由）。
- signals.yaml 中 `combination`（D1/D2/D3 的 difference 等）目前仅是声明，真实组合
  逻辑由 V1.5B 实现；composite 的 contribution breakdown 也在 V1.5B。
- 测试污染工作区：tests/test_ingestion.py 在测试内调用 generate_fixtures.main()，
  每次跑 pytest 都会重写仓库内的 data/fixtures/wind_macro_sample.xlsx（内含时间戳），
  导致 git 工作区变脏。修复方案：测试改为生成到 tmp_path（生成逻辑已可复用
  build_fixture_frame）。V1.5B 窗口顺手修复，1 行级改动。
- V1.2 既有 Known Issues（FRED/ChinaBond/AKShare/Chicago Fed、check_quality 混频警告、
  ChinaMoney WAF 限流）继续有效，见 git 历史中 V1.2 交接记录。
