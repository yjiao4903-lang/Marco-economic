# Task — V2.5 Historical Validation（Window F）

> 状态：**已补全（协调员，2026-08-30）**。V2 Asset Compass（55 号）交付后开窗。
> 素材来源：负责人 v0.4c 方案 §29–§32（归档于 docs/tasks/47_V1_5E_V0_4C_PRE_MARKET_STABILIZATION.md）、
> 00_MASTER_SPEC §14（验证红线）、02_ARCHITECTURE §12（Validation Layer）、
> docs/research/2026-08-30_R2_asset_prior_matrix.md（批注 5：两条 regime 待检验项）。

## 窗口范围

只做 **V2 产出（Asset Score）的历史验证**：证明（或证伪）Asset Compass 的宏观顺风/逆风
指引在历史上具有信息增量，并用结果决定是否把低效 Core Signal 降级为 Diagnostic。

**不做**：Structural Risk（V2.6）、UI（V3）、Cloud（V4）、ML/HMM、组合优化、
自动交易、参数重新拟合上线。

**不重写**：任何 V1–V2 frozen components。V2.5 只读 Asset 引擎输出做验证，不改
AssetScore 公式、不改 beta、不改 factor 权重（若验证发现必须改 → 先向协调员/负责人
报告，经批准后作为增量版本处理）。

## 前置条件

1. **V2 Asset Compass PASS**（tag `v0.5-asset-compass`，7 资产 Score/View 已可产出）；
2. **Historical Coverage Matrix 可用**：V2 交付后 Core 信号的
   `earliest observation / comparable-history start / source / breakpoints /
   revision risk / minimum validation start` 已建档（见下方 §1，若 V2 未建则本窗口首期建）；
3. **最低验证样本达标（负责人方案 §31）**：优先 `2012–present`，若不可比则 `2015–present`。
   当前 G2/G4 等仅约 30 个月历史——**在样本不足前不得仓促下"有效/无效"结论**，
   缺口通过 Wind 一次性回填补齐（§2）。

## 1. Historical Coverage Matrix（负责人方案 §29）

本窗口首个交付物：对每个 Core Signal 建立/补全覆盖矩阵，逐条记录：

```text
earliest observation
comparable-history start      # 口径可比的历史起点（含 breakpoint 记录）
source
breakpoints                   # 基期重编/统计口径变更/来源切换，禁止偷偷拼接连续一致历史
revision risk                 # 是否可修订序列（如 OECD/GSCPI）
minimum validation start      # 可用于验证的最早日期
```

## 2. 历史回填原则（负责人方案 §30）

不要为了"全自动"拒绝 Wind：**一次性人工导出往往比长期维护脆弱爬虫更便宜**。
适合 Wind 一次性 backfill 的清单（live update 仍走公开源）：

```text
TSF（社融，存量/增量）
Government Bond Financing（政府债券融资）
PMI components（新订单/购进价格等分项）
Property history（房地产历史）
Core CPI（若公开可比历史不足）
Credit spread（信用利差历史）
某些资产指数
```

回填走既有 Wind manual import 链（V1 冻结组件），不新建爬虫。

## 3. 验证方法（V2.5 首次允许的清单，02_ARCHITECTURE §12）

**首次开放**（V2.5 之前全部禁止）：

```text
forward returns
score bucket analysis
regime analysis
rolling beta
weight robustness
```

**允许的结论**：模型历史预测能力弱或不稳定（如实报告，不粉饰）。

## 4. Information Increment Test（负责人方案 §32，本窗口核心新增）

在 §3 五方法之外，必须增加：

### Leave-One-Mechanism-Out（LOMO）

对每个 factor（如 Growth）逐机制剔除后重算，观察：

```text
Factor stability
Asset-score stability
Forward-return separation
```

```text
Full Growth
Without CLI
Without PMI Orders
Without Hard Activity
Without Property
Without Export
```

**目的**：找出长期没有贡献独立信息、但增加维护成本的 Signal。判定规则：

```text
维护成本高 + 增量信息弱 → Core → Diagnostic
```

与"低维护成本优先"的最高优先级一致（00_MASTER_SPEC §2）。

## 5. R2 批注的两条 regime/结构待检验项（必做）

R2 档案头部批注 5 已列为 V2.5 待检验项（55 号任务书交付报告必须已声明），本窗口
必须设计专门检验：

1. **黄金对美债实际利率的 2022–2024 脱钩**（央行购金结构性支柱）：分段检验
   黄金 beta 对 X1（US 10Y Real Yield）在 2022 前后的稳定性差异，如实记录 regime 断点；
2. **信用债对资金面的高敏感**（理财赎回负反馈）：检验 CN_CREDIT 的 Asset Score
   对 D1（Funding Condition）的敏感性是否显著高于对增长类信号的敏感性。

## 6. 拒绝行为（禁止）

- 禁止用验证结果"自动调参"后直接上线（结论 → 报告 → 协调员/负责人决策 → 增量版本）；
- 禁止编造缺失历史、禁止把拼接历史当连续一致序列；
- 禁止在样本不足时下强结论；
- 禁止 synthetic 进入验证样本（production 隔离延续）；
- 禁止未经批准把 Core Signal 降级（LOMO 结果只是建议，降级须负责人批准）。

## 分阶段

### 第一阶段：Historical Coverage Matrix + 历史回填缺口评估
建档、评估哪些序列需 Wind 回填、给用户导出清单。

### 第二阶段：验证框架
forward returns / score bucket / regime analysis / rolling beta / weight robustness
五个方法的实现（纯函数、可复现、与 V2.5 之前产出隔离）。

### 第三阶段：Information Increment Test（LOMO）
逐机制剔除 → 稳定性/分离度报告。

### 第四阶段：报告与建议
`scripts/validation_report.py` 输出验证总览 + LOMO 结果 + 降级建议清单 + 两条 regime
检验结论；写 `data/local/validation_*.csv`。

## Acceptance Criteria

1. Historical Coverage Matrix 对 15 Core 全量建档（含 breakpoint/minimum validation start）；
2. 历史回填缺口评估完成，给用户的 Wind 一次性回填清单在案；
3. 五方法全部实现且与生产计算隔离（不污染 canonical / asset 输出）；
4. LOMO 对每个 factor 逐机制剔除，输出 Factor/Asset 稳定性与 forward-return 分离度；
5. 两条 R2 regime 待检验项有专门检验与结论（含脱钩断点记录）；
6. 验证样本明确标注（起点、breakpoints、口径可比性），不拼接、不编造；
7. 无 synthetic 进样本；无自动调参上线；无 Core 降级（仅建议）；
8. 报告入口可运行，输出验证总览 + LOMO + regime 检验 + 降级建议；
9. 完整 pytest PASS（V2 基线 + 新增）；
10. V1–V2 frozen components 未被重写。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V2.5 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 validation_report.py 并贴出输出；
- 检查是否存在自动调参/拼接历史/synthetic 进样本；
- 检查 LOMO 是否覆盖每个 factor 的每个机制；
- 检查两条 regime 检验是否有结论；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README：验证结论、LOMO 结果、降级建议
（须负责人批准才执行）、历史回填完成情况、两条 regime 检验结论。

建议 tag：

```text
v0.6-validation
```

（下一阶段：**V2.6 Structural Risk**，见 docs/tasks/65。）
