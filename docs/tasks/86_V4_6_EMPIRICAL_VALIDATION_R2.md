# Task — V4.6 Empirical Validation Round 2（Window J2）

> 状态：**已起草（协调员，2026-08-30）**。素材来源：负责人需求文档
> `Personal_Macro_Asset_Compass_V4.5-V4.6_数据补全与经验验证开发需求_V1.0.md`（2026-08-30）。
> **前置：V4.5 Gate 通过后才可开窗**（85 号任务书验收 PASS）。

## 窗口范围

只做 **Empirical Validation Round 2**：利用 V4.5 补齐后的可比历史，重新验证现有
Asset Compass 是否具有稳定、可解释的信息价值。**不新增任何模型能力**。

**严格禁止**（需求 §4 + §3 引言）：
```text
用验证结果直接搜索/修改权重 / 根据 forward return 搜索 asset beta /
网格搜索 score threshold / 优化 regime 参数 / 新增 Signal / 自动调参 /
强行让所有资产都有正面结论
```

**不重写**：任何 V1–V4.5 frozen components。

## 前置条件

1. **V4.5 Gate PASS**（85 号验收通过，D2/D4/Domestic 覆盖、Coverage Matrix、
   source-transition 元数据在案）；
2. 验证用 comparable historical window 已由 V4.5 确立（不再只依赖约 21 个月完整分数量纲）。

## 分阶段（需求 §11 执行顺序）

- **Task 0**：Freeze V4.5 数据（记录 canonical 快照 as-of，验证基准确立）；
- **Task 1**：Rebuild PIT historical panel（沿用 validation/ 既有重建逻辑，用补齐后历史）；
- **Task 2–7**：重新执行并输出——Forward Returns / Score Buckets / Regime Analysis /
  Rolling Beta / Weight Robustness / LOMO（Leave-One-Mechanism-Out）；
- **Task 8**：**M3 regime-dependent validation**（研究性分组：yield down + growth
  improving vs yield down + growth deteriorating；**本轮只验证，不改规则**）；
- **Task 9**：**Gold real-yield decoupling**（若历史足够：长期稳定 / regime-dependent /
  近年弱化；禁止因单一阶段失效改 beta）+ **CN Credit liquidity sensitivity**
  （Domestic Financial 对信用债方向的增量信息；只验证不调权重）；
- **Task 10**：Empirical verdict（每资产 Verdict）；
- **Task 11**：V4.6 验收（见下）。

## 核心验证标准（需求 §3.1，不以高收益为成功标准）

系统验证的是：宏观状态 + 资产顺风/逆风。**不是** Sharpe / 年化收益 / 胜率。
而是：

```text
Directional Separation     正/负 AssetScore 的未来表现方向差异
Score Bucket Monotonicity  High/Neutral/Low 桶是否大体对应更有利环境（不要求严格单调，
                           但不能系统性反向）
Stability                  按时间/regime/rolling window（禁止按结果挑有利区间）
Incremental Information    LOMO：识别维护成本高但增量信息弱的 Signal
Maintenance-adjusted Value 维护成本维度
```

**LOMO 判定**（需求 §3.5）：`维护成本高 + 删除后 Factor/AssetScore 几乎不变 +
forward separation 不恶化` → 只标记 **Core → Diagnostic Candidate**，**不能自动删
Signal**。`growth:G3` 已有低增量迹象，但必须等历史补齐后再次验证，现阶段不降级。

## Acceptance Gate（需求 §3.10，逐条）

```text
[ ] 历史长度达到现实可取得的最大可比范围
[ ] 主要资产不再只依赖约 21 个月完整分数
[ ] 验证不使用未来收益调参
[ ] 所有验证结果可复现
[ ] 弱结果如实输出（Verdict 允许 SUPPORTED / WEAKLY_SUPPORTED / MIXED /
    NO_EFFECT_OR_WEAK / INSUFFICIENT_SAMPLE / DATA_BLOCKED，禁止强行正面）
[ ] LOMO 只形成候选，不自动改模型
[ ] M3 / GOLD / Credit pending 项有结果或明确 blocker
[ ] full pytest PASS（0 failed，network opt-in）
```

## 交付物（需求 §12 + §3.9）

```text
docs/V46_EMPIRICAL_VALIDATION.md   # 每资产至少：Asset / Historical Window / Coverage /
                                   # Directional Separation / Bucket Result / Regime
                                   # Stability / Rolling Beta / Weight Robustness /
                                   # LOMO Result / Known Breakpoints / Confidence / Verdict
data/validation/ 更新结果
更新 docs/01_CURRENT_STATE.md
```

若验证发现明显问题：**只记录为新 ADR / Research Task**（Validation Finding → New ADR →
独立评估 → 用户批准 → 模型版本升级），本窗口不直接改模型。

## 回归要求（需求 §13）

每阶段运行 `python -m pytest`（0 failed）；并运行 signal_status / macro_report /
market_report / asset_report / structural_report / validation_report 确保同 as-of 自洽。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V4.6 Task Spec：
- 逐条列 Acceptance Gate PASS/FAIL；
- 运行完整 pytest（应 0 failed）；
- 运行 validation_report.py 并贴出补齐历史后的完整输出；
- 检查是否用验证结果改过任何权重/beta/阈值（git diff 对照 V4.5 checkpoint）；
- 检查 LOMO 是否只形成候选、未自动删 Signal；
- 检查 M3/Gold/Credit 三项是否有结果或明确 blocker；
- 检查 Verdict 是否如实（存在 INSUFFICIENT_SAMPLE / DATA_BLOCKED / NO_EFFECT_OR_WEAK 为正常）；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README：V46_EMPIRICAL_VALIDATION.md 结论、
LOMO 候选（不降级）、M3/Gold/Credit 检验结果、下一阶段建议。

建议 tag：`v0.10-empirical-validation`（最终以 RELEASE_VERSION_POLICY.md 为准）。

（下一阶段：**Shadow Operation** 3–6 个月——操作观察阶段，非开发窗口；需求 §5 的
Decision Journal / Shadow Metrics / SHADOW_OPERATION_GUIDE.md 在 V4.6 交付后另行启动。
完成 V4.6 后 **STOP**，不自动进入更多功能开发。）
