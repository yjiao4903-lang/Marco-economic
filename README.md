# Personal Macro Asset Compass

个人轻量化宏观监控与大类资产指引系统。本地优先，Wind 数据通过手工导出的 Excel/CSV 导入，
系统内部转换为统一 long format，最终将宏观状态映射为大类资产的方向性指引。

> 当前开发阶段：**V2.6 Structural Risk（v0.7）**（V0–V1.6A、V2、V2.5 全部冻结）。
> 数据层 27 条序列自动获取（OECD/FRED/Treasury/ChicagoFed/NYFed(H.10)/PBOC/NBS/
> ChinaMoney/ChinaBond/AKShare/Eastmoney + manual_series），append/replace_window/full_refresh
> 三种更新策略 + vintage 快照；production 计算默认隔离 synthetic 数据。
> Fundamental Core **READY 12/15** + WARMUP 3（D2/D4 等待 Wind 回填、X2 等 FRED 网络恢复）；
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
> **V2.6 Structural Risk（v0.7）已实现**（`python scripts/structural_report.py`）：
> S1 Credit-to-GDP Gap / S2 Debt Service Ratio 走 BIS 真实季频数据（WS_CREDIT_GAP Type C /
> WS_DSR，bulk CSV zip，`python scripts/update_sources.py --series CN_CREDIT_TO_GDP_GAP
> --series CN_DSR`），S3 Property Vulnerability 代理池待 B 包调研归档后落地（当前 NO_SIGNAL）；
> 诊断层输出 READY/WARMUP/MISSING_INPUT，无数据或最新值超时显式 NO_SIGNAL（禁止 synthetic）；
> **S 信号不进入 Asset Score**（源码级 + 行为级测试锁定）。
> Regime = TRANSITION。Dashboard（V3）尚未开发。
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

# 测试（network 集成测试默认跳过，-m network 单独运行）
python -m pytest
python -m pytest -m network
```

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
