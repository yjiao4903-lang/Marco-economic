# Personal Macro Asset Compass — CURRENT STATE

> 本文件是多 LLM 窗口交接的核心状态文件。每个开发窗口完成任务后必须更新。

**最后人工确认基线：** 2026-08-29  
**Current Version:** V1.2 Multi-Source Acquisition（V0/V1 已冻结）  
**当前阶段：** V1.2A + V1.2B 已完成并通过验收，下一窗口进入 V1.3。

## 1. 已完成

### V0 Foundation — DONE
- Python 项目骨架、YAML 配置、synthetic fixtures
- Excel/CSV importer、normalizer、validator、pytest 基础

### V1 Local Data Engine — DONE（frozen）
- Wind 手工导入、raw archive、SHA256 去重
- canonical Parquet（真源）、DuckDB 缓存、import manifest、质量检查、可重建

### V1.2 Multi-Source Acquisition — DONE（2026-08-29）
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
```

## 4. 当前 README 已定义命令

```bash
python scripts/generate_fixtures.py
python scripts/import_wind.py data/fixtures/wind_macro_sample.xlsx --dry-run
python scripts/import_wind.py data/fixtures/wind_macro_sample.csv
python scripts/rebuild_db.py
python scripts/check_quality.py
python scripts/update_sources.py [--dry-run | --series ID | --backfill]
python -m pytest          # 50 passed（network 测试默认跳过）
python -m pytest -m network
```

## 5. Frozen Components

- V1 全部冻结组件（Wind importer、normalizer/validator、raw archive、SHA256 去重、
  canonical Parquet、DuckDB 缓存、质量检查、synthetic fixtures、pytest 基础）——
  V1.2 未重写任何一项，仅扩展。
- V1.2 冻结（后续版本只扩展不重写）：
  - `data_sources/base.py` 错误契约（FetchError / ProviderUnavailable / ManualFetchRequired）
  - `data_sources/updater.py` 状态语义（OK/STALE/FAILED/FALLBACK_USED/MANUAL_REQUIRED）
  - `config/data_sources.yaml` schema（defaults/providers/series 三段）
  - canonical 元数据以 `indicators.yaml` 为唯一真源（updater 富化，adapter 不带 name/unit）

## 6. 当前未开发

- 15+6+3 Signal Registry（V1.3 下一窗口）
- Transform / Signal / Macro Factor Engine
- Market Confirmation / Structural Risk / Asset Compass
- Historical Validation / Streamlit Dashboard / Cloud Mirror

## 7. 下一任务

> V1.3 Signal Registry（见 docs/tasks/30_V1_3_V1_5A_SIGNAL_FOUNDATION.md）

## 8. 窗口交接记录（2026-08-29 V1.2）

```text
Last Test Result: PASS（python -m pytest，2026-08-29）
Last Test Count: 50 passed, 0 failed（另有 6 个 network 测试 opt-in：4 passed, 2 skipped）
Last Git Commit: 初始 checkpoint（单一提交包含 V0→V1.2 全部状态；git 于 V1.2 完成后才初始化，
  v0.2-local-data-engine 无法回溯创建，予以跳过并在本文件留档）
Last Git Tag: v0.3-multisource-acquisition
Known Issues: 见第 10 节
Modified Files Since Last Release: 新增 data_sources/ 子系统 + config/data_sources.yaml +
  scripts/update_sources.py + tests/data_sources/；paths.py、indicators.yaml、README、
  pyproject 为扩展性修改（详见 docs/tasks/20 的 Handoff 记录）
```

## 9. 每次窗口结束必须更新

- Current Version / Completed / Tests / Known Issues / Frozen Components / Next Task / Git

## 10. Known Issues（V1.2 结束时已知，不阻塞 V1.3）

- FRED 在当前网络环境不可达（fred.stlouisfed.org 读超时）；adapter 与解析测试完好，
  US_REAL_YIELD_10Y / USD_BROAD / ANFCI 暂依赖 manual list，网络恢复后
  `python scripts/update_sources.py` 自动补上。
- ChinaBond searchYc 端点已失效（页面 404、POST 返回空）；解析器有确定性 fixture 测试，
  CN_GOV_YIELD_10Y 暂走 Wind manual。
- AKShare 未安装（可选依赖）；安装 `pip install akshare` 后 CSI300 自动恢复更新。
- Chicago Fed 下载中心 URL 需人工确认后填入 data_sources.yaml providers.chicagofed
  options.url。
- check_quality 对「synthetic 月度 + 真实 daily 混合」的序列（USD_CNY、CSI300、
  CN_GOV_YIELD_10Y）报 frequency mismatch 警告；属 V1 fixtures 与真实数据并存的过渡
  现象，数据被真实数据完全覆盖后自然消失。
- ChinaMoney WAF：pageSize>50 会被 403 拒绝；adapter 已限制单页 50 并自动翻页；
  连续高频请求也可能触发临时 403（adapter 内置一次退避重试）。
