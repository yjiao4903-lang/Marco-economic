# Task — V4 Cloud Mirror（Window I）

> 状态：**已补全（协调员，2026-08-30）**。V3 交付后开窗。
> 素材来源：02_ARCHITECTURE §14（Cloud Layer）、00_MASTER_SPEC §14（云同步 V4 后置）、
> 02_ARCHITECTURE §1（后续可能多 PC）。

## 窗口范围

只做 **云端镜像同步**：把数据与配置镜像到云端，支持多 PC。
**不做**：云上计算、云上 Dashboard、多用户鉴权、实时推送、
把 DuckDB 或本地缓存上传云端。

**硬约束（02_ARCHITECTURE §14）**：

```text
云端同步：raw/ canonical/ config/
本地保留：*.duckdb cache/ logs/ .venv/
每台 PC 独立 DuckDB
```

## 前置条件

1. **V3 PASS**（本地 Dashboard 稳定，tag `v1.0-local`）；
2. 明确用户选择的云后端（Git 私有仓库 / 对象存储 / 其他——本任务书不预设实现，
   开窗时与负责人确认）。

## 范围要点

- 同步对象：`raw/`（原始文件归档）、`canonical/`（Parquet 真源）、`config/`（配置）；
- **不**同步：`*.duckdb`（可重建缓存）、`cache/`、`logs/`、`.venv/`、`data/local/` 运行产物；
- 每台 PC 独立重建 DuckDB（`scripts/rebuild_db.py` 已有）；
- 冲突语义：canonical 为 append-only + 可修订序列 vintage 快照（V1.2C/D 既有语义），
  云端合并须遵守此约束，不得覆盖本地已归档的 raw 原件；
- 同步失败 → 显式状态（沿用 V1.2 状态机），禁止 silent fallback；
- 安全：不上传任何本地凭证/密钥（.gitignore 校验）。

## Acceptance Criteria

1. 同步范围严格为 raw/canonical/config，本地缓存类文件不上传（实测 + .gitignore 校验）；
2. 多 PC 拉取后可用 `rebuild_db.py` 完全重建本地 DuckDB 且校验一致；
3. canonical append-only 与 vintage 快照语义在同步合并中保持；
4. 同步失败有显式状态；无凭证上传；
5. 完整 pytest PASS（V3 基线 + 新增）；
6. V1–V3 frozen components 未被重写。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V4 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 实际跑一次同步并检查同步清单（raw/canonical/config vs 本地缓存）；
- 检查是否有 duckdb/cache/logs/.venv 被上传（gitignore/实测）；
- 检查凭证是否被排除；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README：同步命令、后端选择、多 PC 重建流程。
