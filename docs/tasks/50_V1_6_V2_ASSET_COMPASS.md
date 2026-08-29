# Task — V1.6A Market Confirmation + V2 Asset Compass

> 状态：**占位文件，尚未撰写**。打开对应开发窗口之前，必须先补全本 Task Spec。

## 版本范围

V1.6A Market Confirmation（M1–M6 引擎）+ V2 Asset Compass（7 资产池先验矩阵与输出）。

**范围变更（负责人 2026-08-29 批准）**：原 V1.6 中的 Structural Risk（S1–S3）后移至
V2.6（见 65_V2_6_STRUCTURAL_RISK.md），不进入本任务。生产无真实数据时相关序列输出
NO_SIGNAL，禁止 synthetic 占位。

## 前置条件

- V1.2C + V1.5D（docs/tasks/45）已完成，tag `v0.4b-data-quality`；
- Core REAL-computable 覆盖达到 Gate A 目标（或剩余缺口已明确记录 blocker）。

## 撰写要求

参照既有任务书（20、45）的格式补全：

1. 窗口范围与窗口划分（可评估是否拆分为 D1=V1.6A、D2=V2 两个窗口）；
2. Market Confirmation 输出契约（trend / percentile / confirmation / divergence，
   与 Fundamental 隔离的硬约束）；
3. Asset 先验矩阵的经济学依据要求（每条映射需引用机制依据，可外包调研支撑）；
4. 逐条可判定的 Acceptance Criteria 与 smoke 命令；
5. Frozen Components 清单（含 V1.2C/V1.5D 新冻结项）；
6. 完成后需更新的文档与 Git checkpoint（建议 tag：v0.5-asset-compass）。

核心原则见 00_MASTER_SPEC.md：Market 不得反向修改 Fundamental Score；
Asset Score ≠ 预期收益 ≠ 交易信号；未经用户批准不得新增 Core Signal。
