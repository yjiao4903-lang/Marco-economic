# Personal Macro Asset Compass

个人轻量化宏观监控与大类资产指引系统。本地优先，Wind 数据通过手工导出的 Excel/CSV 导入，
系统内部转换为统一 long format，最终将宏观状态映射为大类资产的方向性指引。

> 当前开发阶段：**Shadow Operation（v0.11-s3-property-pool）**，进入 3–6 个月观察期；
> V4.6 已完成，Window J3 的 S3 诊断层补全已冻结。观察期不是模型开发窗口。
> **D2/D4 当前状态（2026-09-01）**：生产替换已落地：2018-01..2026-03 使用 Wind 历史，
> 2026-04 起保留 PBC 生产尾部；**release gate = conditionally accepted**，采用公开累计报告差分的
> **10 bn_cny 分辨率感知门**。该接受仅适用于公开累计报告差分，不表示高精度同口径已证实；严格
> live-PBC 原始解析验收门独立保留。
> 生产 ID、下游路由和候选序列均保留，已生成回滚备份并重建 DuckDB。以下占位内容为历史记录：
> **固定常数占位（2026-08-30，负责人指令）**：wind 数据后补空置期间，以
> `data/inbox/wind/wind_backfill_tsf_placeholder.csv`（固定常数，source=`WIND_PLACEHOLDER`）
> 补齐 2018-01..2026-03 历史，D2/D4 由 WARMUP → **READY**（Core 14/15）。占位**显式标记、
> 不覆盖真实 PBOC 观测（2026-04 起保留 PBC source）**、可被后续 `wind_backfill_tsf.csv`
> 导入按 (date) 覆盖；占位段 yoy=0（中性），2026-04 起分数为真实数据驱动（边界 yoy 突变
> 属占位基准近似，如实登记）。**不伪装真实、不改模型、无静默拼接**（asset trace 中
> D2/D4 的 source 明确显示历史占位来源）。
> V4.5 只做数据补全：新增 `scripts/historical_coverage.py`（Historical Coverage Matrix 32 行 + 
> `docs/HISTORICAL_COVERAGE_MATRIX.md`，含 source-transition 元数据）、`scripts/cloud_size.py`
>（Cloud size monitor，`data/local/cloud_size_report.csv`）、`docs/RELEASE_VERSION_POLICY.md`
>（Product Milestone vs Git Tag + 建议 `v0.9-data-completion`）。D2/D4 现为占位驱动 READY
>（Domestic 4/4）；X1 overlap check 仍按独立门管理，X2 已 READY。V4.5/J3 的历史状态仅作
> 交付演进记录，当前状态以本段及 `docs/01_CURRENT_STATE.md` 为准。
> 交付报告 `docs/V45_DATA_COMPLETION_REPORT.md`。
> **Window J3 B 包归档 + S3 代理池（2026-08-30，已冻结为 v0.11-s3-property-pool）**：
> B 包调研已归档 `docs/research/2026-08-30_bpack_structural_survey.md`；S3 四类代理池
> （景气/杠杆/价格/资金）落地为**等权重 percentile 合成**，景气（AKShare 国房景气 326 行）与
> 杠杆（AKShare/NIFD 居民杠杆 80 行）**真实入库**；四类代理当前 **READY（4/4）**；价格/资金 Wind manual/
> 不可得，无数据如实 `NO_SIGNAL`/PARTIAL（无 synthetic、无硬塞弱代理）；S 信号不进入 Asset Score
> （assets/ 零改动）。当前各代理的脆弱性方向尚未逐项统一，S3 诊断解释保持 **PROVISIONAL / NOT
> ACCEPTED**，修正方向映射并回归前只代表工程接线完成。
> **V4.6 Empirical Validation Round 2（产品里程碑；纳入 v0.11，未单独创建 v0.10 Git tag）已实现**：
> 逐资产 Empirical Verdict（6 类如实输出：GOLD **SUPPORTED**（探索性）、WEAKLY_SUPPORTED 港股/工业商品、
> MIXED 信用债 3m 方向反转、NO_EFFECT_OR_WEAK A股/利率债/CNY）+ M3 regime-dependent 检查 +
> Gold decoupling / Credit funding 专项；LOMO 候选 growth:G3（**不降级**）；五方法+权重鲁棒
> （0.978–0.999）。结论（如实）：**既不证实、也不证伪** 方向信息价值（样本仍 ~21 个月，
> wind 回填未到，属后补空置）；异象仅登记不改模型。Gold real-yield decoupling 仍因 pre-2022
> 实际利率历史缺失而 DATA_BLOCKED。交付报告 `docs/V46_EMPIRICAL_VALIDATION.md`。
> **Shadow Operation 基建（2026-08-30 交付）**：观察期（3–6 个月，非开发窗口）只读监控——
> `scripts/shadow_metrics.py`（每月末方向一致性命中率，输出 `data/local/shadow/`）、
> `docs/SHADOW_OPERATION_GUIDE.md`（运营指南）、`docs/shadow/decision_journal.md`（决策
> 日志，预置 V4.6 五条待决项 DJ-001..005）。观察期内不修改任何模型；一切改动力议进日志，
> Product Stable Review 统一裁定。
> 数据层 27 条序列自动获取（OECD/FRED/Treasury/ChicagoFed/NYFed(H.10)/PBOC/NBS/
> ChinaMoney/ChinaBond/AKShare/Eastmoney + manual_series），append/replace_window/full_refresh
> 三种更新策略 + vintage 快照；production 计算默认隔离 synthetic 数据。
> Fundamental Core **READY 15/15**（D2/D4 已生产落地，release gate conditionally accepted；X2 已 READY）；
> **Market Confirmation 6/6 real READY**（M1-M6 全部真实数据）；
> **V2 Asset Compass 7/7 real READY**（`python scripts/asset_report.py` 输出 7 资产
> Score/View/1M/3M/逐因子与逐信号贡献/市场确认/置信快照；资产层只读 factor+market 输出，
> 无反向流；View 仅顺风/逆风/中性，无买卖/仓位字样）。
> **V2.5 Historical Validation（v0.6）已实现**（`python scripts/validation_report.py`）：
> Historical Coverage Matrix（15 Core 全量建档）+ 五方法验证（forward returns / score bucket /
> regime / rolling beta / weight robustness）+ LOMO 信息增量检验 + 两条 R2 regime 待检验项。
> 验证结论（如实）：**样本不足以作定论** —— 四因子完整资产分数量纲仅约 2024-12 起，低于负责人
> 最低样本（2012/2015–present）；五方法在部分覆盖率下以 NO_EFFECT_OR_WEAK 为主（探索性）；
> 黄金实际利率脱钩 DATA_BLOCKED（无真实 2022 前历史）、信用债资金面敏感 INSUFFICIENT_SAMPLE；
> LOMO 早见 growth:G3 为低增量候选（仅建议，未降级）。回填清单见
> `python scripts/validation_report.py` 输出 / `data/local/validation_backfill_gaps.csv`。
> **V2.6 Structural Risk（v0.7 / +v0.11-s3-property-pool）已实现**（`python scripts/structural_report.py`）：
> S1 Credit-to-GDP Gap / S2 Debt Service Ratio 走 BIS 真实季频数据（WS_CREDIT_GAP Type C /
> WS_DSR，bulk CSV zip，`python scripts/update_sources.py --series CN_CREDIT_TO_GDP_GAP
> --series CN_DSR`）；**S3 Property Vulnerability 代理池已落地**（四类=景气/杠杆/价格/资金，
> 等权重 percentile 合成；景气 AKShare `CN_REAL_ESTATE_CLIMATE`、杠杆 AKShare
> `CN_HOUSEHOLD_LEVERAGE` 真实入库 → **PARTIAL 2/4**；价格/资金 Wind manual/不可得）；
> 诊断层输出 READY/WARMUP/PARTIAL/MISSING_INPUT，无数据或最新值超时显式 NO_SIGNAL（禁止
> synthetic）；**S 信号不进入 Asset Score**（源码级 + 行为级测试锁定）。
> Regime = TRANSITION。
> **V3 Local Dashboard（v1.0-local）已实现**（Streamlit，本地只读）：四面板（宏观总览 /
> 市场确认 / 资产指引 / 结构风险）+ 全链路可追溯下钻（Asset→Factor→Signal→Raw Series→
> Provider）。UI 只读快照（读报告产出的 data/local/*.csv，不触发更新/不重算）；as-of 同天
> 对齐（synthetic 不显示为真实）；无买卖/仓位字样；无鉴权/多用户/云功能。
> **V4 Cloud Mirror（v0.8）已实现**（Git 私有仓库后端：`python scripts/cloud_sync.py`）：
> 同步 `config/` + `data/raw/` + `data/canonical/` 到私有远程，多 PC 共享一份真源；本地
> 保留 `*.duckdb` / `data/local/` / `logs/` / `.venv/`；每台 PC 拉取后用 `rebuild_db.py`
> 完全重建本地 DuckDB；raw 追加式不同文件合并零冲突、canonical 并发改写显式 CONFLICT、
> 失败显式状态、无凭证上传、无 silent fallback。真实远程 URL 由用户配置后执行。
> 所有 `data/fixtures/` 下的数据均为 **synthetic 模拟数据**，不是真实市场数据，且默认不进入生产计算。

## 目录结构

```text
config/        YAML 配置（指标注册表、Wind 字段映射等）
data/
  inbox/wind/  待导入的 Wind 导出文件（放入此处）
  raw/wind/    已导入原始文件归档（程序不覆盖）
  canonical/   Parquet 标准层（可迁移数据真源）
  local/       DuckDB 本地分析缓存（可随时删除重建）
  fixtures/    synthetic 测试数据
src/macro_compass/  核心代码
scripts/       命令行入口
tests/         pytest
docs/          项目文档（多 LLM 窗口协作开发包）
  00_MASTER_SPEC.md           项目宪法：定位、15+6+3 信号、数据源与模型原则
  01_CURRENT_STATE.md         当前状态（每窗口结束必须更新）
  02_ARCHITECTURE.md          分层架构与各层约束
  03_LLM_INTERACTION_GUIDE.md 多窗口接力开发交互指南
  tasks/                      各版本 Task Spec（10 为 V1 冻结交接，20 为 V1.2，
                              30–80 为后续版本占位，开窗口前须补全）
```

## 开发流程（多 LLM 窗口接力）

每个开发窗口的最简循环：

```text
新窗口读 README + docs/00 + 01 + 02 + 当前 Task Spec
→ pytest baseline → Implement → Self Review → pytest
→ Handoff（更新 01_CURRENT_STATE.md + README）→ Git checkpoint → 下一窗口
```

具体规则见 `docs/03_LLM_INTERACTION_GUIDE.md`。

## 环境

- Python 3.11+（Windows 本地）
- 安装：`pip install -e .`（开发模式）

## 常用命令

```bash
# 生成 synthetic 测试数据（V0 fixtures）
python scripts/generate_fixtures.py

# 解析并校验一个 Excel/CSV（不写库）
python scripts/import_wind.py data/fixtures/wind_macro_sample.xlsx --dry-run

# 正式导入：归档原件 -> canonical parquet -> DuckDB
python scripts/import_wind.py data/fixtures/wind_macro_sample.csv

# 从 canonical 完全重建 DuckDB（删除 data/local/macro.duckdb 后可恢复）
python scripts/rebuild_db.py

# 数据质量检查
python scripts/check_quality.py

# 多源自动更新（公共数据源 -> canonical -> DuckDB，生成状态报告）
# 每序列可配置 update_policy: append / replace_window / full_refresh（GSCPI 等可修订
# 序列使用 full_refresh 并保留 vintage 快照）
python scripts/update_sources.py                 # 增量更新全部序列
python scripts/update_sources.py --dry-run       # 只抓取并报告，不写库
python scripts/update_sources.py --series USD_CNY --series CHN_CLI
python scripts/update_sources.py --backfill      # 忽略状态，抓全历史

# V1.3 信号注册状态：逐信号输入可用性 + 缺失序列清单
python scripts/signal_status.py                  # 写 data/local/missing_series.csv

# V1.5A 变换引擎 smoke：对一条真实 canonical 序列跑声明的变换链（只读）
python scripts/transform_smoke.py                # G1 链跑 CHN_CLI
python scripts/transform_smoke.py --signal I1 --rows 10

# V1.5C 宏观快照：15 个 core signal + 四因子 + Regime 一次输出（验收主入口）
python scripts/macro_report.py                   # 最新快照，写 data/local/signal_scores.csv
python scripts/macro_report.py --today 2026-08-01

# V1.5D 信号质量诊断：status / saturation / warmup / as-of 说明
python scripts/signal_quality.py                 # 写 data/local/signal_quality.csv

# v0.4c 双源重叠检验（切换序列 primary 前的硬性验收门）
python scripts/overlap_check.py --series US_REAL_YIELD_10Y --left treasury --right fred

# V1.6A 市场确认层快照：Market Data Matrix + 六信号 1M/3M/6M/percentile + divergence
python scripts/market_report.py                  # 写 data/local/market_confirmation.csv
python scripts/market_report.py --today 2026-08-01

# V2 Asset Compass 快照：7 资产 Score/View/1M/3M + 逐因子/逐信号贡献 + 市场确认 + 置信
python scripts/asset_report.py                   # 写 data/local/asset_scores.csv
python scripts/asset_report.py --today 2026-08-01

# V2.5 Historical Validation：Coverage Matrix + 五方法 + LOMO + 两条 regime 检验
python scripts/validation_report.py              # 写 data/local/validation_*.csv
python scripts/validation_report.py --today 2026-08-01

# V2.6 Structural Risk 快照：S1/S2/S3 诊断状态 + 最新值 + NO_SIGNAL 语义
python scripts/structural_report.py              # 写 data/local/structural_risk.csv
python scripts/structural_report.py --today 2026-08-01
python scripts/update_sources.py --series CN_CREDIT_TO_GDP_GAP --series CN_DSR  # BIS 季频入库

# V3 Local Dashboard（Streamlit，本地只读四面板 + 全链路可追溯下钻）
# 先跑四个报告（同一 --today 以保持 as-of 同天对齐），再启动：
python scripts/macro_report.py && python scripts/market_report.py \
  && python scripts/asset_report.py && python scripts/structural_report.py
python -m streamlit run src/macro_compass/ui/app.py   # 打开 http://localhost:8501

# 测试（network 集成测试默认跳过，-m network 单独运行）
python -m pytest
python -m pytest -m network

# V4 Cloud Mirror：把 config/ + data/raw/ + data/canonical/ 同步到 Git 私有远程
# （*.duckdb / data/local/ / logs/ / .venv/ 永不上传；失败显式状态，无 silent fallback）
python scripts/cloud_sync.py --dry-run   # 只打印待同步清单，不写/不传
python scripts/cloud_sync.py             # 推送：verify -> add -> commit -> pull(merge) -> push
python scripts/cloud_sync.py --pull      # 多 PC 拉取最新 config/raw/canonical
git remote add origin <your-private-repo-url>   # 首次配置真实远程（用户自行执行）

# V4.5 Historical Completion（数据补全，只读）
python scripts/historical_coverage.py    # Coverage Matrix：data/historical_coverage_matrix.csv
                                         #   + docs/HISTORICAL_COVERAGE_MATRIX.md（含 source-transition）
python scripts/cloud_size.py             # Cloud size monitor：data/local/cloud_size_report.csv
# 文档：docs/RELEASE_VERSION_POLICY.md（Milestone vs Tag）、docs/V45_DATA_COMPLETION_REPORT.md
```

## 多 PC 同步 / 重建流程（V4 Cloud Mirror）

后端选择（2026-08-30 与负责人确认）：**Git 私有仓库**。真实远程 URL 由用户配置，未预设实现。

```text
PC-A（数据机）
  更新/导入后 → python scripts/cloud_sync.py --dry-run   # 校验清单（12 项：config/raw/canonical）
             → python scripts/cloud_sync.py               # 提交并推送 config/raw/canonical
PC-B（新机器）
  git clone <your-private-repo-url>  ← 拉到 config/raw/canonical
  python scripts/rebuild_db.py        ← 从 canonical 完全重建本地 DuckDB（每 PC 独立）
  （后续更新） python scripts/cloud_sync.py --pull && python scripts/rebuild_db.py
```

同步合并语义（与数据层一致）：

- `data/raw/wind/` 为**追加式**：时间戳命名的原件从不覆盖；不同 PC 新增不同文件 → Git
  树合并零冲突，另一端 pull 后全部在列（不丢不覆盖）。
- `data/canonical/` 承载合并后的真源；两台 PC 并发改写同一 parquet → Git 二进制冲突
  → `cloud_sync` **显式 CONFLICT**（不静默覆盖），需人工解决后重跑。
- vintage 快照（GSCPI/BIS 等可修订序列）在 `data/local/vintage/`，属每 PC 本地，不上传，
  由 canonical 重建。
- 任何 git 失败（无 git / identity 缺失 / push 被拒 / 网络）→ 显式失败状态 + 非零退出码，
  无 silent fallback；凭证类/本地缓存类文件在清单校验阶段即被拒绝（双保险于 .gitignore）。

## 数据契约（canonical long format）

| 字段 | 类型 | 说明 |
|---|---|---|
| series_id | string | 系统内部唯一指标 ID |
| date | date | 数据观察日期 |
| value | float | 数值 |
| source | string | WIND / MANUAL / OTHER |
| source_file | string | 原始文件名 |
| import_time | datetime | 导入时间 |

推荐字段：`series_name`、`unit`、`frequency`、`category`（macro/market）、`file_hash`。

## 核心原则

- 原始文件 append-only，sha256 去重，同一文件不会重复写数据。
- Parquet 是真源，DuckDB 是缓存，删除后可用 `rebuild_db.py` 完全重建。
- 所有指标、映射、阈值配置化，不硬编码。
- Asset Score = 当前宏观环境对该资产的顺风/逆风程度，≠ 预期收益 ≠ 交易信号 ≠ 仓位建议（V2 已实现）
