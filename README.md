# Personal Macro Asset Compass

个人轻量化宏观监控与大类资产指引系统。本地优先，Wind 数据通过手工导出的 Excel/CSV 导入，
系统内部转换为统一 long format，最终将宏观状态映射为大类资产的方向性指引。

> 当前开发阶段：**V1.2C Data Coverage Hardening + V1.5D Signal Quality Gate**（截至 V1.5C 全部冻结）。
> 数据层 25 条序列自动获取（OECD/FRED/ChicagoFed/NYFed/PBOC/NBS/ChinaMoney/ChinaBond/AKShare），
> 支持三种更新策略（append / replace_window / full_refresh）与 vintage 快照；
> 信号引擎 + 宏观因子引擎已就绪，production 计算默认隔离 synthetic 数据。
> 当前 Core REAL-computable 9/15（Growth 5/5、Inflation 2/3、Domestic 1/4、Global 1/3），
> Regime 首次输出真实状态；缺口为如实记录的 network/source/history-warmup blocker。
> 资产评分（V2）、Dashboard（V3）尚未开发。
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
- Asset Score ≠ 预期收益 ≠ 交易信号（后续版本）。
