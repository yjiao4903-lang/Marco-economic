# Task — V4.5 Historical Completion（Window J1）

> 状态：**已起草（协调员，2026-08-30）**。素材来源：负责人需求文档
> `Personal_Macro_Asset_Compass_V4.5-V4.6_数据补全与经验验证开发需求_V1.0.md`（2026-08-30，
> 已批准并入路线，见 00_MASTER_SPEC §15）。
> 代码基线：`0d583c6`（tag v0.8-cloud-mirror）；测试基线：252 passed / 0 failed。

## 窗口范围

只做 **Historical Completion（数据补全）**：正式偿还 Economic Coverage Gate waiver
留下的 Model/Data Debt，使 V2.5/V4.6 拥有真正可比的验证历史。

**唯一目标**：补齐现有模型真实历史，使经验验证第一次拥有足够样本。

**严格禁止**（需求 §2 引言 + §4 模型冻结纪律）：
```text
新增 Core Signal / 修改 Signal 权重 / 修改 Factor 权重 / 修改 Asset beta /
根据未来收益调参 / 网格搜索阈值 / 优化 regime 参数 / 新 UI / ML / 自动仓位 / 自动交易
```

**不重写**：任何 V1–V4 frozen components（见 CURRENT_STATE §5）。

## 前置条件

1. **用户提供 `wind_backfill_tsf.csv`**（P0-1 硬前置；Total TSF Flow + Government Bond
   Financing Flow，优先 2010-01 至今、最低 2015-01 至今）。文件未到期间可并行推进
   P0-2/P1 项（Coverage Matrix、source-transition 元数据、Cloud size monitor、
   RELEASE_VERSION_POLICY），但 **D2/D4 READY 判定以文件导入为准**。
2. FRED 网络（X1 overlap / X2 补历史）：恢复则执行；未恢复则如实 BLOCKED，不阻塞
   V4.5 主体（需求 §2.6：X2 不阻塞，只要 Global 生产可用 + 历史 blocker 明确）。

## 分阶段（需求 §10 执行顺序）

- **Task 0**：Baseline / git / pytest（应 252 passed）→ 记录起点；
- **Task 1（P0-1）**：Wind 文件到达后——读取真实列名 → 补 `config/wind_mapping.yaml`
  （不预设不存在的列）→ `import_wind.py` → 写 canonical（保留 source/source_file/
  import_time）→ **不覆盖 PBOC live route**（历史=Wind one-time backfill，未来=PBOC
  automatic update）。若 Wind 可同时导出 Total TSF Stock / Gov Bond Stock → D3 历史增强
  （Optional，不阻塞主线）；
- **Task 2（P0-3）**：导入后重跑 signal_status / signal_quality / macro_report →
  **目标 Domestic ≥3/4 READY**（D1 READY、D2 READY、D3 READY/PARTIAL、D4 READY）；
- **Task 3（P0-2）**：产出 **Historical Coverage Matrix**（`docs/HISTORICAL_COVERAGE_MATRIX.md`
  + `data/historical_coverage_matrix.csv`）。每个 Core/Market Signal 至少记录：
  signal_id / series_id / earliest_observation / comparable_history_start /
  current_source / historical_source / frequency / revision_risk / breakpoints /
  minimum_validation_start / status / blocker。目标 2012–present（最低优先 2015–present），
  **绝不为日期目标强行拼接不可比数据**；
- **Task 4（P0 纪律）**：任何 history+live 拼接必须记录 source transition 元数据：
  canonical definition / historical source / live source / transition date / overlap
  period / max abs diff / median abs diff / missing dates / unit / frequency /
  methodology notes / breakpoint。**定义不可比 → 宁可缩短 comparable history，不造假连续序列**；
- **Task 5（P0-4）**：执行 `scripts/overlap_check.py`（Treasury vs FRED DFII10）。
  最低规则：common trading days ≥60、|diff|≤0.05；输出 max_abs_diff / median_abs_diff /
  missing_dates / overlap_start / overlap_end。**未 PASS 禁止把 FRED 历史并入 canonical X1**；
  若 FRED 不可达 → 如实 BLOCKED；
- **Task 6（P0-5）**：X2 历史状态显式化（FRED 恢复后自动补历史；保持显式 fallback，
  禁止 silent fallback；历史 blocker 明确记录）；
- **Task 7（P1）**：Cloud Mirror size monitor——新增简单统计（repo_size /
  new_bytes_this_sync / raw_file_count / canonical_file_count / vintage_file_count）；
  不迁移 Git LFS / OneDrive / 对象存储；
- **Task 8（P1）**：新增 `docs/RELEASE_VERSION_POLICY.md`——区分 Product Milestone vs
  Git Release Tag，冻结当前工程完成状态为语义明确的 stable tag（不重写历史 tag）；
- **Task 9**：V4.5 验收（见下）。

**S3（P1，不阻塞）**：有稳定、经济意义明确的代理 → 落地；没有 → 保持 NO_SIGNAL。
禁止为了 3/3 完整度硬塞弱代理/synthetic/脆弱网页抓取（B 包调研若已归档则按 66 号执行）。

## Acceptance Gate（需求 §2.10，逐条）

> 验收注记（2026-08-30，负责人指令）：wind 文件未到达，前 4 条文件相关项按
> **「后补空置」** 验收（不阻塞 V4.6；用户后续上传后按 Task 1/2 导入即闭合）。
> 其余 9 条全部 PASS（Coverage Matrix DONE、X1 BLOCKED 如实、X2 显式、无静默 fallback、
> 无 synthetic、无模型权重改动、pytest 252 PASS）。

```text
[x] Wind D2/D4 historical backfill imported（文件到达前提下）→ 后补空置
[x] D2 READY → 后补空置（WARMUP）
[x] D4 READY → 后补空置（WARMUP）
[x] Domestic >=3/4 READY → 后补空置（当前 2/4）
[x] Historical Coverage Matrix complete（含 comparable-history start / source-transition
    metadata）
[x] X1 overlap check completed or explicitly BLOCKED
[x] X2 history status explicit
[x] no silent fallback
[x] no synthetic production
[x] no model weight changes（任何 Signal/Factor/Asset beta/阈值均未改）
[x] full pytest PASS（0 failed，network opt-in）
```

理想：14/15 Core READY；但更重要是**关键机制历史可比性**。

## 交付物（需求 §12）

```text
docs/HISTORICAL_COVERAGE_MATRIX.md
data/historical_coverage_matrix.csv
docs/V45_DATA_COMPLETION_REPORT.md   # 含 source-transition 对照、D2/D4 状态、X1/X2 状态、回填记录
更新 docs/01_CURRENT_STATE.md（§8 交接记录 + Known Issues）
```

## 回归要求（需求 §13）

每阶段运行 `python -m pytest`（0 failed）；并运行 signal_status / macro_report /
market_report / asset_report / structural_report / validation_report，确保同一 as-of 输出自洽。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V4.5 Task Spec：
- 逐条列 Acceptance Gate PASS/FAIL；
- 运行完整 pytest（应 252+ 且 0 failed）；
- 运行 signal_status/macro_report 确认 D2/D4/Domestic 状态；
- 检查 Historical Coverage Matrix 是否对每个 Core/Market Signal 建档且 comparable
  start / breakpoint / source-transition 齐全；
- 检查是否有任何权重/阈值/信号声明被改（git diff 对照 v0.8-cloud-mirror）；
- 检查 X1 overlap 是否 PASS 或如实 BLOCKED（未 PASS 禁止拼 FRED）；
- 检查是否存在静默拼接/伪造连续历史；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README：D2/D4/Domestic 覆盖、Coverage Matrix、
source-transition 对照、X1/X2 状态、回填记录、Cloud size monitor、版本策略。

建议 tag：由 `docs/RELEASE_VERSION_POLICY.md`（Task 8 产出）定义后确认；
候选 `v0.9-data-completion`（不覆盖既有 v0.8/v1.0，最终以版本策略为准）。

（下一阶段：**V4.6 Empirical Validation Round 2**——须 V4.5 Gate 通过后开窗，见 86 号任务书。）
