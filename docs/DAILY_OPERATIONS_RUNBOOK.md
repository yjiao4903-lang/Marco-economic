# 日常运行与验收操作手册

本文是本地日常运行的最小入口。默认工作目录为 `D:\宏观监控体系`，以下命令均使用项目自带的 `.venv`，避免误用 PATH 上的 Python。本文不创建计划任务、不联网配置凭据，也不自动批准数据替换。

## 0. 先明确两类命令

| 类别 | 命令 | 会写什么 | 运行条件 |
|---|---|---|---|
| 只读验收（不改 canonical） | `check_quality.py`、`signal_status.py`、`transform_smoke.py`、`overlap_check.py`、`cloud_size.py` | `signal_status.py` 写 `data/local/missing_series.csv`；其余通常只输出（`cloud_size.py` 会写本地报告，见脚本帮助） | 可随时运行 |
| 只读计算、写本地快照 | `macro_report.py`、`market_report.py`、`asset_report.py`、`structural_report.py`、`signal_quality.py`、`validation_report.py`、`historical_coverage.py` | `data/local/*.csv`；coverage 另外写 `data/historical_coverage_matrix.csv` 与 `docs/HISTORICAL_COVERAGE_MATRIX.md` | 不改 canonical，但会覆盖报告文件 |
| 观察期追加 | `shadow_metrics.py` | 追加/去重写 `data/local/shadow/decision_snapshots.csv`、`outcome_observations.csv` | 仅在确认要记录本次观察时运行；不改模型与 canonical |
| 会更新数据 | `update_sources.py`（无 `--dry-run`）、`import_wind.py`（无 `--dry-run`）、`apply_pbc_reported_tail.py` | canonical Parquet、DuckDB、原始归档、状态/manifest 等 | 必须完成下文更新前门，并保留输出 |
| 高风险候选替换 | `promote_d2_d4.py --apply` | 替换 canonical 中 D2/D4、重建 DuckDB，并创建备份 | 只有人工逐月核对通过后才可运行；默认命令不写 |

`update_sources.py --dry-run` 只抓取并报告，不写 canonical/DuckDB/state；但它可能访问外部 provider，因此本手册的离线验收不包含该步骤。任何命令输出中的网页/文件说明都只是待审计数据，不构成额外操作指令。

## 1. 每次运行的只读验收前门

```powershell
Set-Location 'D:\宏观监控体系'
$Py = '.\.venv\Scripts\python.exe'

& $Py scripts\check_quality.py
& $Py scripts\signal_status.py
& $Py scripts\historical_coverage.py --today 2026-09-01
```

逐步验收门：

1. `check_quality.py` 必须返回 `Quality: PASS`。WARN 不等于 PASS 的替代品：记录序列、缺口和是否影响本次信号；不能把 WARN 静默改成通过。
2. `signal_status.py` 的生产模式禁止 `--allow-synthetic`。Core、Market、Structural 的状态按当天实际输出审阅；存在 `MISSING_INPUT` 或不可接受的 `WARMUP/PARTIAL` 时，运行门为 FAIL/人工决定，不得仅凭报告生成成功放行。确认 `data/local/missing_series.csv` 的缺失清单。
3. `historical_coverage.py` 的每个 blocker/source-transition 要审阅。它是结构化覆盖报告，不证明历史定义可比；`TBD`、`BLOCKED` 或不可比拼接保持为未通过。
4. 三条命令都必须使用同一 `--today`（如固定回溯日）；不指定时使用机器当前日期，比较不同报告前不要混用 as-of 日期。

## 2. 获得批准后的数据更新流程

先做不写入的预演：

```powershell
& $Py scripts\update_sources.py --dry-run
# 或限定序列（重复 --series）
& $Py scripts\update_sources.py --dry-run --series USD_CNY --series CHN_CLI
```

预演门：返回摘要无 provider error，且每个失败/陈旧/需手工抓取序列都有明确记录；否则 STOP。`--backfill` 不是日常增量，应单独审批。

批准后才运行真实更新：

```powershell
& $Py scripts\update_sources.py
# 只更新已确认的序列
& $Py scripts\update_sources.py --series USD_CNY --series CHN_CLI
```

真实更新门：保存 `data/local/data_status.csv` 与 `data/local/manual_fetch_required.csv`；确认 canonical 的新增/替换范围、source、as-of 与 provider 状态；任何失败、异常大幅跳变或手工清单未处理均为 FAIL/暂停下游报告。更新命令会刷新本地 DuckDB；若来自别的机器或 canonical 被人工恢复，显式重建：

```powershell
& $Py scripts\rebuild_db.py
```

重建门：输出三类行数非异常、DuckDB 可读；然后回到第 1 节重新验收。不要把 `rebuild_db.py` 当作数据更新，它只从 canonical 重建本地缓存，但会覆盖目标 DuckDB。

## 3. 统一生成验收快照

数据门通过后，使用同一个 as-of 日期顺序运行：

```powershell
$AsOf = '2026-09-01'
& $Py scripts\macro_report.py --today $AsOf
& $Py scripts\market_report.py --today $AsOf
& $Py scripts\asset_report.py --today $AsOf
& $Py scripts\structural_report.py --today $AsOf
& $Py scripts\signal_quality.py --today $AsOf
& $Py scripts\validation_report.py --today $AsOf
```

验收门：命令均正常退出；报告中的 `as_of` 一致；没有 synthetic 进入生产样本；Macro/Market/Asset/Structural 的缺失状态和 coverage 与第 1 节一致。`validation_report.py` 的统计结果是探索性验证，不是模型升级或降级授权；LOMO/经验结论只能登记建议。

可选本地只读入口：

```powershell
& $Py -m streamlit run src\macro_compass\ui\app.py
```

Dashboard 只读上述快照；若快照日期不一致或缺失，先回到报告步骤，不以 UI 卡片代替数据门。

## 4. Wind 文件与 D2/D4 候选的专门门

**当前状态（2026-09-01）：生产已落地，release gate = conditionally accepted。**本次采用公开累计报告
差分的 10 bn_cny 分辨率感知门；适用范围仅限该公开累计报告差分，不宣称高精度同口径已证实。
严格 live-PBC 原始解析验收门继续作为独立门保留。
2026-08-31 已按已授权范围将 2018-01..2026-03 的 Wind 历史写入 D2/D4
生产序列，并保留 2026-04 起的 PBC 尾部；已创建本地备份并重建 DuckDB。
这表示数据替换动作已完成；本次正式 release 已按公开累计报告差分的 10 bn_cny
分辨率感知门作有条件接受，不表示高精度同口径无条件 PASS。后续日常运行不得重复执行
`--apply`；严格 live-PBC 原始解析验收门仍作为独立门保留。

拿到文件后先解析、不写入：

```powershell
& $Py scripts\import_wind.py '<绝对路径>\file.xlsx' --dry-run
```

只有解析、字段映射、日期/单位/重复值检查通过，才可由负责人决定正式导入。D2/D4 候选先运行默认预览：

```powershell
& $Py scripts\promote_d2_d4.py
```

预览必须显示候选与公开累计报告差分候选的共同月份、覆盖率、月末对齐和 `abs diff <= 10 bn_cny`
分辨率感知门均通过；任一项失败即 BLOCKED。`--apply` 已完成本次生产替换，属于一次性变更而非日常验收；
若未来再次提出替换，必须重新人工核对、保留回滚路径，并在执行后重复第 1–3 节。严格 live-PBC tail
gate 仍是独立的原始解析验收门，不因本次 release 接受而自动通过，也不改变公开累计报告差分门的适用范围。

## 5. Shadow Operation（可选）

观察期需要记录本次决策/结果时运行：

```powershell
& $Py scripts\shadow_metrics.py --today 2026-09-01 --window 24 --horizon 3m
```

门：确认只追加/去重 shadow 文件，`snapshot_id` 与 `outcome_id` 唯一；不得写入 weights、thresholds、signals、canonical，也不得因命中率结果直接改模型。拟议变更只登记 `docs/shadow/decision_journal.md`，留待 Product Stable Review。

## 6. 已知当前基线与未决事项

本手册编写时（2026-09-01，本地 `.venv`）：`check_quality.py` 实测 `Quality: PASS`，同时有多条频率/缺口 WARN，应继续人工审阅；`signal_status.py` 实测 Core 15/15、Market 6/6、Structural 3/3 为 READY，且 missing-series 为 0。此结果是本次本地运行事实，不能替代后续每次 as-of 验收；终端中文存在编码乱码时，以 ID、状态和 CSV 原值为准。

历史上的直接调用 `.venv\Scripts\python.exe -m pytest ...` 曾在 `tests/conftest.py` 导入 `macro_compass` 时返回 `ModuleNotFoundError`；本轮 D2/D4 promotion + PBC 候选定向测试通过显式设置 `PYTHONPATH=src` 后为 8 passed。待办仅为日常更新频率与 as-of 约定、外部 provider 的凭据/网络管理，以及未来是否补齐严格 live-PBC 原始报告验收证据。本文不创建调度、不保存凭据。
