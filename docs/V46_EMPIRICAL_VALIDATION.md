# V4.6 Empirical Validation Round 2（实证验证第二轮）

> 生成：2026-08-30　|　任务书：`docs/tasks/86_V4_6_EMPIRICAL_VALIDATION_R2.md`（Window J2）
> 代码基线：延续 V4.5 冻结面（`config/`、`src/` 仅新增 validation/verdict.py 只读模块 + regime_checks M3 检查；无模型权重/阈值/信号改动）　|　测试基线：见 §9（全量 pytest 0 failed）
> 本窗口**只做实证验证**：不新增模型能力、不用验证结果调参、不改任何 frozen components、
> 不强行正面结论。LOMO/M3/Gold/Credit 只形成研究结果或候选，**不自动改模型**。

## 1. 结论摘要

| 维度 | 结果 |
|---|---|
| 可比历史窗口 | 四因子资产分数仍 ~21 个月末（domestic_financial 自 2024-12 起）；**wind 回填未到，历史未实质补齐**（如实） |
| 五大方法 | 主导 NO_EFFECT_OR_WEAK（部分覆盖分数，探索性）；CN_CREDIT 3m 方向反转（见 §4） |
| LOMO 候选 | `growth:G3`（低增量候选，**不降级**） |
| M3 regime 检查 | **INSUFFICIENT_SAMPLE**（yield 序列 2023-05 起，yield-down 月仅 11 个；研究性结论未定） |
| Gold real-yield decoupling | **DATA_BLOCKED**（无 2022 前真实黄金/实际利率历史） |
| Credit funding sensitivity | **INSUFFICIENT_SAMPLE**（D1 历史太短，n=19） |
| 逐资产 Verdict | 7 资产 6 类结论如实输出（含 NO_EFFECT_OR_WEAK / MIXED / INSUFFICIENT_SAMPLE，见 §3） |
| 验证是否可复现 | 是（`python scripts/validation_report.py` 一步重跑，输出至 `data/local/validation_*.csv`） |

**一句话结论**：在当前（wind 回填未到的）历史长度下，既有 Asset Compass 的**方向性信息价值既未被证实、也未被证伪**——样本远低于负责人最低门槛（2012/2015 至今）。任何"有效/无效"的强判定都不成立；`growth:G3` 仍为低增量候选，但**必须等历史补齐后再次验证才可决策**。

## 2. 验证样本（Task 0/1）

- **as-of 冻结**：2026-08-30 canonical 快照；`allow_synthetic=False` 恒闭（synthetic 永不进验证样本）。
- **PIT 面板重建**：沿用 `validation/history.py` 既有重建逻辑——月度月末网格截断冻结 signal frames，经冻结 `compute_factor` 逐点重算四因子分数；资产分数按冻结 prior beta 与 L1 归一。
- **样本规模**：`factor_panel` 2006-01-31 → 2026-08-31（growth/inflation/global 全程可分）；**domestic_financial 自 2024-12-30 起**，因此完整四因子资产分数窗口仍仅 ~21 个月末。
- **前向收益**：每资产 canonical 市场代理（价格/收益率/利差/黄金），1M/3M 前向。
- **样本门槛**：`MIN_N_FOR_DIRECTIONAL=60`（月度）——不足即 INSUFFICIENT_SAMPLE，绝不凑数。

## 3. 逐资产 Verdict（Task 10）

> 判定标准：**不以收益率为成功标准**——验证的是"宏观状态 + 资产顺风/逆风的**方向分离**与**单调性/稳定性**"。Verdict 允许 6 类：SUPPORTED / WEAKLY_SUPPORTED / MIXED / NO_EFFECT_OR_WEAK / INSUFFICIENT_SAMPLE / DATA_BLOCKED。

| Asset | 名称 | Verdict | n | mean_rho | 覆盖 | 置信度 | 关键依据 |
|---|---|---|---|---|---|---|---|
| CN_EQUITY | A股 | **NO_EFFECT_OR_WEAK** | 246 | -0.052 | 0.81 | low-medium | 方向 rho 1m=-0.04/3m=-0.07，桶差与 regime 差均 ~0；权重鲁棒 0.993 |
| HK_EQUITY | 港股 | **WEAKLY_SUPPORTED** | 246 | +0.106 | 0.83 | low-medium | rho 1m=+0.11/3m=+0.10（方向与先验一致，但 \|rho\|≤0.15）；桶差+；权重鲁棒 0.995 |
| CN_GOV_BOND | 利率债 | **NO_EFFECT_OR_WEAK** | 246 | -0.115 | 0.80 | low-medium | rho 1m=-0.09/3m=-0.14（负向但未达 0.15 条）；桶差 ~0 |
| CN_CREDIT | 信用债 | **MIXED（方向反转）** | 246 | -0.156 | 0.65 | low-medium | rho 1m=-0.14/3m=-0.17（材料级负向，**与声明先验反向**）；桶差负 |
| GOLD | 黄金 | **INSUFFICIENT_SAMPLE** | 0 | — | 0.86 | low | 无前向收益面板（canonical 黄金现货缺失）→ 无法验证 |
| INDUSTRIAL_COMMODITY | 工业商品 | **WEAKLY_SUPPORTED** | 246 | +0.143 | 0.83 | low-medium | rho 1m=+0.14/3m=+0.15（接近材料级，方向一致）；桶差 3m=+0.029；权重鲁棒 0.999 |
| CNY | 人民币汇率 | **NO_EFFECT_OR_WEAK** | 246 | -0.062 | 0.81 | low-medium | rho 1m=-0.13/3m=+0.01（跨 horizon 符号不一致，净效应弱） |

**读法（诚实声明）**：
1. **没有任何资产达到 SUPPORTED**——当前样本只能支撑 WEAKLY_SUPPORTED（港股、工业商品）与各类弱/反转/不足结论。
2. **CN_CREDIT 3m 方向反转**是唯一材料级异象（rho=-0.17），提示信用债机制可能存在未捕获的负反馈（见 V2.5 已登记 v25_pending 的 wealth-product redemption / D1 funding 双刃），**但样本过短，仅登记、不调权重**。
3. GOLD 因现货序列缺失，**任何结论都是 DATA_BLOCKED / INSUFFICIENT_SAMPLE**，不推断。

## 4. 五大方法（Task 2–7，`validation_methods.csv`）

- **Forward Returns**（方向分离）：主导 \|rho\|≤0.15；CN_CREDIT 3m -0.17（反转）、CN_GOV_BOND 3m -0.14（弱负）为最大两档。
- **Score Buckets**（单调性）：各资产 high−low 前向收益差均接近 0 或弱负——**未出现系统性反向**，但也未形成稳健单调桶。
- **Regime Analysis**（G+ 减 G− 前向均值差）：CN_EQUITY 3m -0.024（弱负），其余 ~0。
- **Rolling Beta**（稳定性）：多数资产 rolling rho 均值 \|rho\|≤0.15、std 0.19–0.25——**时间不稳定性高**，与样本过短一致。
- **Weight Robustness**（先验权重敏感）：7 资产 mean_scheme_corr 0.978–0.999——**对 tier 权重方案高度鲁棒**（这是本轮唯一一致的正面信号）。

## 5. LOMO（信息增量，Task 2–7 之一）

| Factor | Mechanism | factor_stab | min_asset_stab | max_sep_delta | candidate |
|---|---|---|---|---|---|
| growth | G1 | 0.867 | 0.896 | 0.097 | False |
| growth | G2 | 0.998 | 0.996 | 0.008 | False |
| growth | **G3** | 0.972 | 0.964 | 0.044 | **True** |

- `growth:G3`（Hard Activity Composite）满足"低增量候选"判定（高稳定性 + 低分离变化），与 V2.5 结论一致。
- **按任务书纪律：只标记 Core → Diagnostic 候选，不自动删 Signal、不降级**。且须在 wind/PMI 历史补齐后**再次验证**（当前 G3 已 READY，但其历史优势主要来自早段，需确认补齐后仍成立）。
- 其余机制（含刚接入的 G2/G4/X2、样本不足的 D2/D4）均未被标为候选。

## 6. M3 regime-dependent validation（Task 8，RESEARCH ONLY）

- **检查**：`m3_regime_dependent`（新增，`regime_checks.py`）——将 yield-down 月（3M 收益率下降，market.yaml M3 move_3m 口径）按 PIT growth 符号分组，比较利率债 3M 前向收益。
- **结果**：**INSUFFICIENT_SAMPLE**（yield-down 月仅 11 个：growth>0 组 n=6 均 +1.00%，growth≤0 组 n=5 均 -0.07%，spread=+1.07%）。
- **解读**：方向性与"宽松非衰退"假设一致，但 n 远低于 60 门槛——**本轮只验证、不改规则**；待 M3 yield 历史更长（或 Wind 回填更早收益率）后重检。

## 7. Gold / Credit 专项（Task 9）

### 7.1 Gold real-yield decoupling（GOLD_X1）
- **DATA_BLOCKED**：canonical 无 2022 前的真实黄金现货与 US_REAL_YIELD_10Y 历史，**decoupling 断点不可观测**。
- 这是**回填发现**（feed backfill list），不是负面结论。

### 7.2 CN Credit funding sensitivity（CREDIT_D1）
- **INSUFFICIENT_SAMPLE**：对齐样本仅 n=19（D1 需 DR007 + 政策利率历史，政策利率 canonical 仅 2024 起）。
- 观察值：spearman(creditFwd,Funding)=-0.15、spearman(creditScore,Funding)=+0.92（分数侧强相关、前向侧弱）——**不构成可判读结论**，待 D1 历史补齐后重检。

## 8. 未改动项与纪律确认

- **无权重/beta/阈值改动**：git diff 对照 V4.5 checkpoint，`config/` 零改动；`src/` 仅新增只读验证代码。
- **无 synthetic、无 silent fallback**：验证样本 `allow_synthetic=False` 恒闭。
- **未用未来收益调参**：一切方法均为纯函数，读取冻结输出，无搜索循环。
- **弱结果如实输出**：Verdict 表含 NO_EFFECT_OR_WEAK / MIXED / INSUFFICIENT_SAMPLE / DATA_BLOCKED，无强行正面。
- **LOMO 只形成候选**：growth:G3 仅标记，未删除/降级任何 Signal。

## 9. 验收对照（86 号任务书 Acceptance Gate）

```text
[x] 历史长度达到现实可取得的最大可比范围   → PASS（=当前数据可得上限 ~21 个月；wind 回填未到属后补，不计为窗口失败）
[x] 主要资产不再只依赖约 21 个月完整分数   → NOT MET（如实：wind 未到，仍 ~21 个月；已在 §1/§2 显式声明，作为后补阻塞项）
[x] 验证不使用未来收益调参                 → PASS
[x] 所有验证结果可复现                     → PASS（validation_report.py 一步重跑）
[x] 弱结果如实输出                         → PASS（Verdict 6 类含非正面结论）
[x] LOMO 只形成候选，不自动改模型          → PASS（growth:G3 candidate=True，未降级）
[x] M3 / GOLD / CREDIT pending 项有结果或明确 blocker → PASS（M3=INSUFFICIENT_SAMPLE、GOLD=DATA_BLOCKED、CREDIT=INSUFFICIENT_SAMPLE，均为明确结论或 blocker）
[x] full pytest PASS（0 failed，network opt-in）→ PASS（见下方）
```

**P0-2 / P1 全部推进项完成**；唯一未达项（"不再依赖 21 个月"）依赖 wind 回填，已按负责人指令登记为**后补空置**，不阻塞。

## 10. 结论与下一步

1. **当前判定：既不证实、也不证伪** Asset Compass 的方向信息价值。这不是失败——在历史补齐前本就不可判，如实输出即本轮目标。
2. **一致的正面信号**：权重鲁棒性（0.98–0.999）与方向一致性（港股/工业商品为正、利率债/CNY 弱负）至少与机制声明不自相矛盾。
3. **异象登记（不处理）**：CN_CREDIT 3m 方向反转 → 建议新 ADR / Research Task 单独评估（涉及 D1 funding 双刃机制），本窗口不改模型。
4. **LOMO 候选**：growth:G3 → 待 Wind/PMI 历史补齐后重验，届时由负责人决定是否降级。
5. **后续（未开始，待 Wind 回填）**：补 wind_backfill_tsf.csv → D2/D4 READY → 重跑本报告 → 检验 M3/Gold/Credit 是否可从 blocker 转结论。
6. **阶段终点**：V4.6 交付后进入 **Shadow Operation**（3–6 个月观察期，非开发窗口）。**STOP，不自动进入更多功能开发。**

## 11. 修改文件清单

| 文件 | 变更 |
|---|---|
| `src/macro_compass/validation/regime_checks.py` | 新增 `m3_regime_dependent`（Task 8 研究性检查），纳入 `run_all` |
| `src/macro_compass/validation/verdict.py` | **新增**逐资产 Verdict 只读汇总模块（Task 10） |
| `scripts/validation_report.py` | 接入 verdict 生成 + 输出 `validation_verdicts.csv`，结论段补 M3 |
| `tests/test_validation.py` | 新增 M3 检查两个测试 |
| `docs/V46_EMPIRICAL_VALIDATION.md` | 本文档（本窗口主交付物） |
| `data/local/validation_verdicts.csv` | 新增输出（另含既有 validation_*.csv 刷新） |
