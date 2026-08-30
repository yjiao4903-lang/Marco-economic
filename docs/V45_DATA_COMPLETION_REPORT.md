# V4.5 Data Completion Report（data completion + coverage matrix + 版本纪律）

> 生成：2026-08-30　|　任务书：`docs/tasks/85_V4_5_HISTORICAL_COMPLETION.md`
> 代码基线：`f4afe60`（README 当前 HEAD，offset tag `v0.8-cloud-mirror`）　|　测试基线：**252 passed / 0 failed**（本节运行确认）
> 本窗口**只做 Historical Completion（数据补全）**：不重写任何 frozen components，不改任何权重/阈值/信号声明，禁止 synthetic、禁止静默拼接。

## 1. 结论摘要

| 交付项 | 状态 |
|---|---|
| Wind D2/D4 historical backfill imported | **PENDING**（`wind_backfill_tsf.csv` 未到达） |
| D2 READY | 未达成（WARMUP，等文件） |
| D4 READY | 未达成（WARMUP，等文件） |
| Domestic >= 3/4 READY | **当前 2/4**（D1/D3 READY；D2/D4 WARMUP）——文件到达导入后转 4/4 |
| Historical Coverage Matrix complete | **DONE**（含 comparable start / source-transition / breakpoint） |
| X1 overlap check | **BLOCKED**（FRED 读取超时，如实；未 PASS 前不拼 FRED） |
| X2 history status explicit | **DONE（WARMUP + 显式 blocker）** |
| no silent fallback | **PASS** |
| no synthetic production | **PASS** |
| no model weight changes | **PASS**（git diff 对照 `v0.8-cloud-mirror` 无 config/model 改动） |
| full pytest PASS | **PASS（252 passed / 0 failed）** |

## 2. Task 0 — Baseline

```bash
python -m pytest  →  252 passed, 0 failed, 10 deselected（network opt-in）
```

起点信号状态（`python scripts/signal_status.py`）：Core **12/15 READY** + WARMUP 3（D2/D4/X2）、
Market **6/6 READY**、Structural **S1/S2 READY**（S3 MISSING_INPUT）。与 CURRENT_STATE §10 一致。
Domestic 当前 D1 READY / D2 WARMUP / D3 READY / D4 WARMUP（= 2/4）。

## 3. Task 1 / Task 2 — Wind D2/D4 回填（P0-1 / P0-3）

**前置未满足（P0-1）**：`wind_backfill_tsf.csv`（Total TSF Flow + Government Bond Financing Flow）
尚未由用户放入 `data/inbox/wind/`（该目录当前不存在）。按任务书约定，文件未到期间不阻塞
P0-2/P1，但 **D2/D4 READY 判定以文件导入为准**，不得用其他来源凑数。

文件到达后的既定步骤（导入链路由已就绪）：
1. 读取 Wind 导出真实列名，在 `config/wind_mapping.yaml` 补 `CN_TSF_TOTAL` /
   `CN_GOV_BOND_FINANCING` 两列映射（不预设不存在的列；wind_mapping.yaml 当前**尚无**这两列）；
2. `python scripts/import_wind.py <file>` → canonical（保留 source/source_file/import_time）；
3. **不覆盖 PBOC live route**（历史 = Wind 一次性回填，未来 = PBOC replace_window 自动更新）；
4. 若同一文件含 Total TSF Stock / Gov Bond Stock → D3 历史增强（Optional，不阻塞）。
5. 重跑 signal_status / signal_quality / macro_report → 目标 Domestic ≥3/4 READY。

现状：D2 `CN_TSF_TOTAL`(earliest 2026-04) / `CN_GOV_BOND_FINANCING`(earliest 2026-04) 仅存 PBOC
增量月度流（~5 期），WARMUP（最小历史未满）。D3 `CN_PRIVATE_TSF_YOY` 仅 2026-04 起，D3 READY
但 comparable history 很短。

## 4. Task 3 — Historical Coverage Matrix（P0-2）

产出：
- `data/historical_coverage_matrix.csv`（32 行，逐（信号, 输入序列）建档）
- `docs/HISTORICAL_COVERAGE_MATRIX.md`

脚本：`python scripts/historical_coverage.py`（新，只读，复用 signals.status 生产管线 +
market/structural 引擎 + resolve_signal_status，未改任何 frozen）。

每个 Core/Market/Structural 信号记录：signal_id / series_id / earliest_observation /
comparable_history_start / minimum_validation_start / current_source / historical_source /
frequency / revision_risk / breakpoints / status / blocker。

关键 comparable-history 事实（如实）：
- **Domestic 是短板**：D1 需 DR007[2017]+政策利率[2024] 双腿 → comparable start 2024-12；
  D3 precious 仅 2026-04；**2012–present 目标未达**（这正是 V4.6 再验证要依赖回填的原因）。
- **global/others 充足**：CHN_CLI 1992、PMI 2025-10（short）、G3 NBS 2008、property 2025-09、
  export 1992、CPI 2008、PPI 2006、GSCPI 1997（HIGH 修订风险）、credit gap 1995、DSR 1999 ——
  大部分达到 2012–present。
- 目标纪律：**绝不为 2012 起强行拼接不可比数据**；comparable_history_start = PIT 首次可计分日，
  由其决定，不伪造连续序列（见 Task 4）。

## 5. Task 4 — Source-Transition 纪律（P0）

`scripts/historical_coverage.py` 内嵌 `SOURCE_TRANSITIONS` 声明映射，为每个可能 history+live
拼接的序列记录：canonical_definition / historical_source / live_source / transition_date /
overlap / unit / frequency / notes / breakpoint。要点：

- **CN_TSF_TOTAL / CN_GOV_BOND_FINANCING**：Wind(PENDING) vs PBOC replace_window——
  定义同源（PBOC 月度流），导入后**必须先与 live leg 做 overlap 校验再合并**，未校验不拼接；
- **US_REAL_YIELD_10Y**：Treasury(primary) vs FRED DFII10(fallback)——DFII10 本就是 Treasury
  curve 的重分发，定义同源，但 **合并点火门 = overlap_check PASS（≥60 共同日）**，当前 BLOCKED，
  canonical 中**尚无 FRED 行**（历史仅 Treasury 2024 起）；
- **USD_BROAD**：FRED DTWEXBGS(primary, 网络 BLOCKED) vs H.10(fallback)——同定义，X2 WARMUP，
  无 synthetic 拼接；
- **CN_POLICY_RATE_7D**：MANUAL 台阶 bootstrap(↓) + PBC OMO live——同一官方公告，可比性成立；
- **G3**：OECD 指数 vs NBS 增速——**单位不同（index vs %）非数值连续**，只作 fallback，
  绝不把指数与增速数字拼接。

规则：定义不可比 → 宁可缩短 comparable history，不造假连续序列。

## 6. Task 5 — X1 Overlap Check（P0-4）

```bash
python scripts/overlap_check.py --series US_REAL_YIELD_10Y --left treasury --right fred --min-days 60
[UNAVAILABLE] fred: HTTP request failed ... 读取超时
OVERLAP CHECK: BLOCKED - both sources are required. ... rerun when the failing source is reachable.
```

**结果：BLOCKED（FRED DFII10 读取超时，网络 blocker）**。按任务书最低规则
（common trading days ≥60、|diff|≤0.05），**未 PASS 之前禁止把 FRED 历史并入 canonical X1**。
当前 canonical X1 仅 Treasury 2024 起，完全无 FRED 行——无拼接发生。如实 BLOCKED，不设 silent
fallback。FRED 网络恢复后重跑本检查，PASS 前持续保持现状。

## 7. Task 6 — X2 历史状态显式化（P0-5）

- 路由：primary=FRED `DTWEXBGS`，fallback=Fed H.10（`BROAD`）。
- 现状：`USD_BROAD` canonical earliest 2026-08-17（仅 H.10 fallback 周数据），**5 期 < 250 → WARMUP**。
- 历史 blocker（显式）：FRED 网络不可达 → 无法自动补全 DTWEXBGS 长历史；**禁止 silent fallback**
  （H.10 只有近期周，不冒充长历史；无 synthetic）。
- 恢复后：update_sources 自动补全历史 → X2 自动转 READY（明确记录为"FRED 恢复后自动"）。
- Covered in `data/historical_coverage_matrix.csv`（USD_BROAD 行 blocker + historical_source）与
  `docs/HISTORICAL_COVERAGE_MATRIX.md`。

## 8. Task 7 — Cloud Mirror Size Monitor（P1）

新脚本 `python scripts/cloud_size.py`（只读，复用 `cloud.sync.build_manifest`），输出
`data/local/cloud_size_report.csv`（本地监控产物，不上传）。统计：repo pack+loose 总字节 /
new_bytes_this_sync（未提交在同步范围内的工作树字节）/ config / raw / canonical / vintage
各自文件数与字节。未迁移 Git LFS / OneDrive / 对象存储。

首次实测（2026-08-30）：repo 对象库约 1.32 MB；scope 最新合计 ~390 KB（12 文件：
config 8 / raw 2 / canonical 2）；vintage 5（本地）；uncommitted 0。

## 9. Task 8 — Release Version Policy（P1）

`docs/RELEASE_VERSION_POLICY.md`：
- 区分 **Product Milestone**（MASTER SPEC §15，功能/验证里程碑）与 **Git Release Tag**
  （可回滚/可审计快照，一旦打标**永不重写**）；
- 命名 `v<MAJOR>.<MINOR>[-suffix]`；define **Semantic Stable Tag** 判定（Gate 全 PASS +
  文档更新 + 干净 commit）；
- 登记历史 tag 快照；建议本窗口冻结 **`v0.9-data-completion`**（不覆盖既有 v0.8/v1.0）。

## 10. 修改文件与验收对照

| 类型 | 文件 | 说明 |
|---|---|---|
| 新增（只读脚本） | `scripts/historical_coverage.py` | Task 3/4：Coverage Matrix + source-transition |
| 新增（输出） | `data/historical_coverage_matrix.csv` | 32 行矩阵（参与 git，属于同步真源?否——数据层，随 raw/canonical 语义为本地；按需提交） |
| 新增（文档） | `docs/HISTORICAL_COVERAGE_MATRIX.md` | 人类可读矩阵 + transition 说明 |
| 新增（脚本） | `scripts/cloud_size.py` | Task 7：size monitor |
| 新增（文档） | `docs/RELEASE_VERSION_POLICY.md` | Task 8：版本纪律 |
| 新增（交付报告） | `docs/V45_DATA_COMPLETION_REPORT.md` | 本文件 |

**frozen 检查**：`config/*`（signals/data_sources/macro/market/assets/structural/indicators）、
`src/macro_compass/` 下所有引擎 module、`scripts/` 下既有报告脚本——**零改动**。
`git diff v0.8-cloud-mirror..HEAD` 仅涉及新增文档/脚本与拟议提交内容，无任何权重/阈值/信号声明变更。
新增脚本不 import 被断言禁用的包（assets 不 import market 等约束保持），纯报告/只读。

## 11. Known Issues / 未决（如实）

- D2/D4、Domestic ≥3/4：**PENDING Wind 文件**（非本窗口可解除，阻塞于用户上传）。文件一到即可
  按 §3 步骤转 READY，无需改代码（wind_mapping 已规划，待补列名）。
- X1 overlap / X2 历史 / S3 代理池 / FRED 网络：维持 BLOCKED / WARMUP / NO_SIGNAL，属环境/外部
  调研项，诚实标注，不替代、不静默。
- 交付的 `data/historical_coverage_matrix.csv` 是分析产物：是否纳入 git 同步范围由负责人/协调员
  依 Cloud 政策决定（建议与文档一起提交，属审计性元数据，非 raw/canonical 数据真源）。

## 12. 建议 tag

按 `docs/RELEASE_VERSION_POLICY.md` → 建议 **`v0.9-data-completion`**（annotated，指向干净 commit，
不覆盖 v0.8-cloud-mirror / v1.0-local）。最终由协调员验收后打标。
下一窗口：V4.6 Empirical Validation Round 2（须 V4.5 Gate 通过，见 `docs/tasks/86_...`）。