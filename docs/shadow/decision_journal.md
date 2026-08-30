# Decision Journal（决策日志）

> 生效：2026-08-30（Shadow Operation 基建，86 号任务书）。
> 纪律：**观察期内只登记、不执行**。任何"应改模型"的拟议在此记录，由 Product Stable
> Review（3–6 月后）统一评估、负责人批准后在**新窗口**执行。

## 1. 记录规则

- 每条 = 一个可独立评估的拟议改动；
- 必须含：证据（数据出处）、建议动作、评估状态；
- 状态：`PROPOSED`（已登记）→ `PENDING_REVIEW`（待评审）→ `ACCEPTED` / `REJECTED` /
  `SUPERSEDED`（由 Product Stable Review / 负责人裁定）；
- 严禁在状态非 `ACCEPTED` 且未开新窗口时改任何 frozen 组件。

## 2. 预置待决项（V4.6 移交，2026-08-30）

### DJ-001 CN_CREDIT 3m 方向反转（材料级，与声明先验反向）
- 证据：V4.6 五方法 rho 1m=-0.14 / 3m=-0.17（`data/local/validation_verdicts.csv`；
  `docs/V46_EMPIRICAL_VALIDATION.md` §3）；V2.5 已登记 v25_pending（财富管理产品
  赎回负反馈 / D1 funding 双刃）。
- 建议动作：**待样本充足后单独评估**信用债机制（D1 资金面对信用债方向的增量信息），
  可能的方向：新增/修订 CREDIT 相关信号路由或 alpha 处理；不排除保留现况。
- 评估状态：`PENDING_REVIEW`。前置：D1 历史补齐（Wind 回填）→ 重跑
  validation_report → CREDIT_D1 从 INSUFFICIENT_SAMPLE 转结论。

### DJ-002 growth:G3（Hard Activity Composite）Core → Diagnostic 候选
- 证据：V2.5 与 V4.6 两轮 LOMO 均 candidate=True（高稳定性 + 低分离变化；
  `validation_lomo.csv`）。
- 建议动作：**若历史补齐后二次验证仍成立**，由负责人决定是否 Core → Diagnostic
  （不自动删除）。
- 评估状态：`PENDING_REVIEW`。前置：wind/PMI 历史补齐后重验。

### DJ-003 M3 regime 条件化（yield-down × growth）
- 证据：`m3_regime_dependent`：yield-down 月 growth>0 组 n=6 均 +1.00%，growth≤0 组
  n=5 均 -0.07%，spread +1.07%——方向与"宽松非衰退"一致，但 INSUFFICIENT_SAMPLE。
- 建议动作：**仅当历史更长后重检**；若成立，可考虑在 M3 判读中显式标注 regime 条件
  （不改方向约定）。本轮不改规则。
- 评估状态：`PENDING_REVIEW`。

### DJ-004 GOLD real-yield decoupling（2022 断点）
- 证据：DATA_BLOCKED（canonical 无 pre-2022 真实黄金/实际利率历史，断点不可观测）。
- 建议动作：pre-2022 数据到位后重检 GOLD_X1；若脱钩确认，评估黄金 beta 或另立
  central-bank buying 机制（**禁止因单一阶段失效改 beta**）。
- 评估状态：`PENDING_REVIEW`。

### DJ-005 S3 房地产脆弱性代理池（B 包调研）
- 证据：**2026-08-30 已归档**（`docs/research/2026-08-30_bpack_structural_survey.md`，
  经实测）并已按 87 号任务书落地：S3 四类代理池（景气/杠杆/价格/资金）等权重 percentile
  合成；景气（AKShare 国房景气）与杠杆（AKShare/NIFD 居民杠杆）真实入库 → **PARTIAL 2/4**；
  价格/资金 Wind manual/不可得，无数据如实输出。无未验证硬编码路由、无 synthetic。
- 建议动作：**已完成（本任务书授权窗口内落地）**。价格/资金在 Wind 文件或 NBS 解析器到位后
  由数据层自动转 READY（无需改 START/方向约定）。
- 评估状态：`SUPERSEDED`（由 87 号任务书落地接收；组合口径见 DJ-006 登记复核）。

### DJ-006 S3 代理池数据健康与组合口径（B 包落地观察，登记不执行）
- 证据（全部实测 2026-08-30）：
  1. **国房景气两独立源（AKShare + 东财 RPT_INDUSTRY_INDEX）均截止 2025-12**——疑 NBS 停发或
     该指标停更；`CN_REAL_ESTATE_CLIMATE` max_staleness 已按观测节奏设 520d，避免假 stale。
  2. **AKShare/NIFD 居民杠杆端点截止 2024-12**（~20 个月滞后）；max_staleness=730d 覆盖该
     access-layer 滞后；NIFD 官方季度更新更及时，但因端点/工作量大未接。
  3. **S3 为四代理等权重 percentile 合成**（percentile_window=20、thresholds 0.80/0.50 为
     声明先验）——非拟合；若后续 Product Stable Review 认为应改权重或窗口，属**声明先验变更**，
     改前须重验。
  4. **价格端仅走 Wind manual**（东财 per-city + BASE 定基 2022-12 起 84/187 填充、残缺），
     全国价格代理需先定城市聚合口径。
- 建议动作：**仅登记，不执行**。① 观察期结束后核实国房景气是否停发（NBS 官网 + 下季度
  是否有新值）；② 若有 NIFD 更权威更及时端点，评估接入成本后在**新窗口**落地；③ 城市价格
  聚合口径由负责人决定；④ 组合权重/窗口为非拟合声明先验，未经历史检验（与 S1/S2 同类）。
- 评估状态：`PROPOSED`。

## 3. 状态变更记录

| 日期 | 条目 | 变更 | 裁定人 |
|---|---|---|---|
| 2026-08-30 | DJ-001..005 | PROPOSED → PENDING_REVIEW（V4.6 移交登记） | 协调员（负责人复核） |
| 2026-08-30 | DJ-005 | PENDING_REVIEW → SUPERSEDED（87 号任务书已落地 S3 代理池） | 开发 Agent（87 授权） |
| 2026-08-30 | DJ-006 | 新增 PROPOSED（S3 代理池数据健康 + 组合口径观察） | 开发 Agent（87 落地） |

## 4. 结束

Product Stable Review 时逐条给出最终裁定并在此登记；未决项转交下一阶段任务书。
