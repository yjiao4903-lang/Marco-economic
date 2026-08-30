# Shadow Operation Guide（影子运行指南）

> 生效：2026-08-30（V4.6 Empirical Validation Round 2 交付后按 86 号任务书另行启动）。
> 依据：`docs/00_MASTER_SPEC.md` §15 路线图——V4.6 → **Shadow Operation**（3–6 个月观察，
> 非开发窗口）→ Product Stable Review → V5 Optional Research。
> 状态：**Shadow Operation 基建已交付（指南 + 决策日志 + shadow_metrics 只读监控）**；
> 观察期自负责人启动之日起算 3–6 个月。

## 1. 目的与边界

Shadow Operation 的目标不是开发新功能，而是在**不修改任何模型**的前提下，收集
Asset Compass 在真实环境中的**样本外方向性证据**，为后续 Product Stable Review 提供
可复核材料。

**严格禁止（观察期内）**：

```text
修改任何 权重 / beta / 阈值 / Signal / 因子 / Regime 参数
用观察结果实时调参（无论"更好"还是"更差"）
删除或降级任何 Core Signal（LOMO 候选只登记，不执行）
把 synthetic / 未验证来源并入生产计算
```

一切"应该改模型"的想法 → 只写入 `docs/shadow/decision_journal.md`，由 Product Stable
Review 统一评估，负责人批准后才在**新窗口**执行。

## 2. 观察期的三个监控面

| 监控面 | 载体 | 频率 |
|---|---|---|
| 方向一致性（View → 实际前向收益） | `python scripts/shadow_metrics.py` | 每月末一次 |
| 数据健康（READY/WARMUP、freshness、覆盖漂移） | `signal_status.py` / `historical_coverage.py` | 每月随报告 |
| 决策积累（拟议改动登记） | `docs/shadow/decision_journal.md` | 随时 |

## 3. shadow_metrics.py 怎么读

- **只读**：复用 validation 冻结机制（`allow_synthetic=False`），读 V2/V1.5 冻结输出 +
  canonical，绝不写 canonical、绝不改阈值（阈值从 `assets.yaml` 读取 = 0.15）。
- **面板**：月度 PIT 资产分数 → 声明 View（tailwind / headwind / neutral）。
- **命中规则**：仅统计非中性 View；`hit = sign(score) == sign(fwd)`（tailwind 期待正、
  headwind 期待负），中性不构成方向声明、不计入。
- **输出**：`data/local/shadow/shadow_metrics.csv`（按 date×asset 追加去重；前向收益
  随市场推进而刷新，首见日期 asof 保留）；每次运行打印近 N 个月命中率摘要。
- **诚实声明**：观察初期非中性 View 与已实现前向收益的样本极少，`hit_rate` 是
  **描述性指标**，非统计显著性；样本不足时如实显示（无强行结论）。

## 4. 节奏

```text
每月末   python scripts/shadow_metrics.py --today <本月末日>
         顺带运行 signal_status / macro / market / asset / structural 报告
         （与报告脚本同 --today 保证 as-of 同天对齐）
每季度   中期自查：对照本指南红线、更新决策日志、写一段观察摘要（可并入 01_CURRENT_STATE）
第 3–6 月  Product Stable Review：
           - 汇总 shadow 命中率 / 数据健康 / 决策日志
           - 逐项评估待决项（见 decision_journal）
           - 输出：是否模型升级 / Signal 精简 / 新功能（V5）的负责人决策
```

## 5. 观察期重点复核项（V4.6 遗留，数据到位后重检）

| 项 | 现状（V4.6） | 数据到位后的动作 |
|---|---|---|
| Wind 回填（D2/D4、Domestic 历史） | 后补空置 | 导入后重跑 validation_report → 主资产样本从 ~21 个月扩充 |
| M3 regime（yield-down × growth） | INSUFFICIENT_SAMPLE（n=11） | 历史更长后重检 m3_regime_dependent |
| GOLD real-yield decoupling | DATA_BLOCKED | 有 pre-2022 真实黄金/实际利率后重检 GOLD_X1 |
| Credit funding sensitivity | INSUFFICIENT_SAMPLE（n=19） | D1 历史补齐后重检 CREDIT_D1 |
| CN_CREDIT 3m 方向反转 | MIXED（仅登记） | 样本足够后评估 D1 funding 双刃机制 |
| growth:G3 低增量候选 | candidate=True（未降级） | 历史补齐后二次验证，负责人决定是否 Core→Diagnostic |
| X1 overlap / X2 历史（FRED） | BLOCKED / WARMUP | FRED 恢复后自动补全，先 PASS overlap 再并入 |
| S3 代理池（B 包调研） | NO_SIGNAL | 66 号调研归档后落地 |

## 6. 红线复核（每次运行自检）

- `git diff` 观察期开始 checkpoint：`config/` 与 `src/macro_compass/{macro,market,assets,signals}`
  零改动（shadow 只新增只读模块/脚本/文档）；
- shadow 输出文件仅落在 `data/local/shadow/`（git-ignored，不随 stable tag 上传）；
- 无 synthetic、无 silent fallback、无未来收益调参。

## 7. 结束与转交

- 观察期结束 → 产出 **Product Stable Review 备忘**（决策日志全量评审 + 命中率汇总 +
  数据健康 + 升级建议）→ 负责人决策 → 需改模型则在**新窗口**（新任务书）执行。
- 若负责人批准提前结束或延长观察期，在本指南顶部登记即可。
