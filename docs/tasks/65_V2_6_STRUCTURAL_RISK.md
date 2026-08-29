# Task — V2.6 Structural Risk

> 状态：**占位文件，尚未撰写**。打开对应开发窗口之前，必须先补全本 Task Spec。

## 版本范围

V2.6 Structural Risk（S1 Credit-to-GDP Gap / S2 Debt Service Ratio / S3 Property
Vulnerability 引擎）。

## 背景与约束（负责人 2026-08-29 批准）

- Structural Risk 从原 V1.6 后移至此处：它不进入短期 Asset Score，
  不应因 BIS 季频数据阻塞 V2；
- 生产环境无真实数据时输出 `NO_SIGNAL`，**禁止 synthetic 占位**；
- 输入为 BIS 季频序列（当前无 provider 路由；config.py 已预留 quarterly frequency），
  需新增 provider 或 Wind manual 路线，属于 V1.2 范围的 provider 增量；
- 输出为诊断性质（中长期的脆弱性监测），与 V2.5 历史验证相互独立。

## 撰写要求

参照既有任务书（20、45）的格式补全：

1. S1–S3 的详细定义、输入序列、BIS 数据源调研（可外包只读调研窗口）；
2. Transform/引擎实现（复用 V1.5A 白名单，需新增的变换须先扩展白名单并测试）；
3. 逐条 Acceptance Criteria 与 smoke 命令；
4. Frozen Components 清单；
5. 完成后需更新的文档与 Git checkpoint。

核心原则见 00_MASTER_SPEC.md：Structural Risk 不进入短期 Asset Score。
