# Task — B 包调研归档 + S3 代理池落地（Window J3, Shadow 观察期开发窗口）

> 状态：**已起草（协调员，2026-08-30）**。前置：V4.6 验收 PASS（86 号任务书）、
> Shadow Operation 基建已交付（`docs/SHADOW_OPERATION_GUIDE.md`）、D2/D4 固定常数占位
> 已落地（Core 14/15）。
> 依据：`docs/00_MASTER_SPEC.md` §12/§15、`docs/tasks/65`（V2.6 第二阶段）、
> `docs/tasks/66`（B 包调研任务书）。

## 窗口定位

本窗口处于 **Shadow Operation 观察期（3–6 个月，非模型开发窗口）**。允许的工作边界：

- **允许**：B 包只读调研收尾并归档、S3 诊断层（structural layer）代理池落地、
  结构性诊断引擎扩展（S 信号**不进入 Asset Score**，隔离有测试锁定）、数据层补全。
- **禁止（观察期红线，沿用 SHADOW_OPERATION_GUIDE §1）**：
  ```text
  修改任何 Asset Score 权重 / beta / 阈值 / Core Signal / 因子 / Regime 参数
  删除或降级任何 Core Signal（LOMO 候选只登记，不执行）
  把 synthetic / 未验证来源并入生产计算
  用验证/观察结果实时调参
  ```
- S3 落地属于 **structural 诊断层**（中长期脆弱性监测，非短期资产指引），
  因此不触发观察期红线；但 S 信号必须保持**不进入 Asset Score**（源码级 + 行为级测试锁定）。

## 前置条件

1. **V4.6 Gate PASS**（86 号验收通过；`docs/V46_EMPIRICAL_VALIDATION.md` 在案）；
2. **Shadow 基建在案**：`scripts/shadow_metrics.py` + 指南 + 决策日志（2026-08-30 交付）；
3. **D2/D4 占位已 READY**（`WIND_PLACEHOLDER`，2026-08-30；真实 wind 文件后续覆盖）；
4. **B 包调研脚本已有实质产出**（`_scratch_b_research/`：BIS 稳定性、AKShare 国房景气
   326 行 1998–2025、东财 70 城房价 2026-07 最新、NBS 新闻稿/NIFD 杠杆率实测）——
   **未归档成 `docs/research/` 报告，未经协调员抽验**。

## 分阶段

### Task 0：基线复核
- `python -m pytest` 全绿（现 252+，D2/D4 占位后无回归）；
- 确认 `structural/engine.py` S3 现状 = `MISSING_INPUT → NO_SIGNAL`（显式，非 synthetic）；
- 记录 canonical as-of 快照（占位导入后）作为本窗口基线。

### Task 1：B 包调研收尾 + 归档（只读，外部窗口产出）
- 按 66 号任务书交付标准，把 `_scratch_b_research/` 实测整理成
  `docs/research/2026-08-30_bpack_structural_survey.md`：
  - BIS WS_*（S1/S2 输入）稳定性与更新行为（补 66 §A：发布日历/修订/bulk vs SDMX 路由）；
  - S3 代理池四类落地清单（66 §B）：
    1. 价格端：70 城新建/二手住宅价格指数（东财 `FIRST_COMHOUSE_SAME/SEQUENTIAL/BASE`，
       `SECOND_HOUSE_*`；BASE 仅 2022-12 起 84/187 填充——**口径务必注明**）；
    2. 景气/投资端：国房景气指数（AKShare `macro_china_real_estate`，1998–2025，最新 91.45）、
       开发投资/新开工/施工/竣工累计同比；
    3. 资金端：房地产开发企业本年到位资金累计同比（细分国内贷款/自筹/定金预收/按揭）——
       NBS 新闻稿解析或东财报表（实测 `RPT_ECONOMY_LOAN` 等**报表配置不存在**，逐条记录失败）；
    4. 杠杆端：居民部门杠杆率（NIFD/央行金稳局季度）、个人住房贷款余额同比/不良率。
  - 每项：Endpoint + VERIFIED/FAILED/不确定 + 历史起点 + 最新日期 + 更新滞后 +
    建议路由（自动源/Wind manual/不可得如实标注）；失败进 Failed Attempts Log。
- **协调员抽验**：抽 2–4 个关键端点数值复核后归档（§7.2 铁律）。

### Task 2：S3 代理池落地（structural 诊断层）
- 按归档清单确定代理组合与口径（价格/景气/资金/杠杆四类的可获取子集）；
- `config/indicators.yaml` + `config/data_sources.yaml` 注册新 series（若走自动源：
  AKShare/东财/NBS 解析，遵守 V1.2 契约；不可得则标 Wind manual，沿用
  `wind_manual.py` 的 MANUAL_REQUIRED 语义）；
- `config/signals.yaml` S3 补全 inputs/transforms（沿用 V1.5A 白名单；
  **需新增变换必须先扩展白名单并测试**）；
- `config/structural.yaml` S3 去除 `placeholder: true`，落地 percentile_window /
  trend_quarters / thresholds（声明先验，禁止拟合）；
- `structural/engine.py` 支持多输入代理池组合（当前仅取 `inputs[0]`），
  无数据/超时仍显式 `NO_SIGNAL`；
- **保持 S 信号不进 Asset Score**：不动 assets/ 任何配置；跑隔离测试证明无数据流。

### Task 3：报告入口 + 测试
- `scripts/structural_report.py` 输出 S1/S2/S3 状态与最新值（S3 转 READY/PARTIAL 后如实显示）；
- 新增确定性 fixture 测试（代理池解析/组合/无数据 NO_SIGNAL）+ network 测试 opt-in；
- 全量 pytest PASS。

### Task 4：文档与验收
- 更新 `docs/01_CURRENT_STATE.md` 与 README：S3 状态、代理池口径、无数据行为、
  与 Asset Score 隔离证明；
- 决策日志登记（若代理组合揭示方向问题，仅登记不执行）。

## Acceptance Criteria

1. B 包调研报告归档 `docs/research/` 并经协调员抽验（端点实测 + 失败逐条 + S3 落地清单）；
2. S3 代理池组合落地并注明口径（价格/景气/资金/杠杆四类 + 各子项路由）；
3. `structural_report.py` 输出 S1/S2/S3 状态与最新值；S3 不再 NO_SIGNAL（或如实
   PARTIAL/WARMUP，取决于数据可得性——**不强制 READY，不硬塞弱代理**）；
4. **S 信号不进入 Asset Score**（有测试证明无数据流）；
5. 完整 pytest PASS（V4.6 基线 + 新增）；网络测试 opt-in；
6. 观察期红线未触碰：`git diff` 中 `config/assets.yaml`、Core Signal 声明、阈值、
   Regime 零改动；
7. V1–V4.6 frozen components 未被重写。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 87 号 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 structural_report.py 并贴出输出（S1/S2/S3 状态与最新值）；
- 检查 S1/S2/S3 是否进入任何 Asset Score（grep 源码 + 行为测试）；
- 检查无数据时是否 NO_SIGNAL 且无 synthetic；
- 检查是否实现范围外功能；
- git diff 确认 assets.yaml / Core Signal / 阈值 / Regime 零改动；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README；决策日志登记代理组合相关发现。

建议 tag：

```text
v0.11-s3-property-pool
```

（下一阶段：视 Shadow 观察期进度与 Product Stable Review 结果决定 V5 方向。
当前观察期红线持续有效。）
