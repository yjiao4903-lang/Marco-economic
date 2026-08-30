# Task — V2 Asset Compass（Window E）

> 状态：**已补全（协调员，2026-08-30）**。前置三 Gate 齐备后开窗。
> 素材来源：`docs/research/2026-08-30_R2_asset_prior_matrix.md`（含协调员抽验批注）、
> `docs/COORDINATOR_HANDOFF.md` §10（转写规则与硬约束）、负责人 v0.4c 方案 §26–§27。

## 窗口范围

只做 **Asset Compass 资产层**：7 资产池 × 15 Core Signal 驱动的先验矩阵映射 →
每资产宏观顺风/逆风指引（Score + View + 变化 + 贡献分解 + 市场确认 + Confidence）。

**不做**：Historical Validation（V2.5）、Structural Risk（V2.6）、UI（V3）、
Cloud（V4）、ML/HMM、组合优化、自动交易、行业轮动、个股选择。

**不重写**：任何 V1–V1.6A frozen components（见 CURRENT_STATE §5，含 V1.6A 新冻结的
`config/market.yaml`、`market/engine.py` 口径、M4/M6 口径）。V2 只读 factor 输出与
market 层输出，不反向修改任何 Fundamental/Market 引擎。

## 前置 Gate 状态（协调员 2026-08-30 更新：负责人豁免部分后补项，V2 已开窗）

1. **Economic Coverage Gate — 负责人豁免开放**（2026-08-30 负责人授权）：
   D2/D4 的 `wind_backfill_tsf.csv` 导入、X2 FRED 补历史、X1 overlap check PASS、
   B 包调研（66 号）均标记**后补**——**不阻塞本窗口开发**。数据/调研就绪后由协调员
   补齐导入与归档，D2/D4 届时自动转 READY。本窗口不得以 synthetic 冒充真实数据
   （沿用 V1.5D production 隔离；缺失输入以 WARMUP/PARTIAL 显式保留，engine 对
   null 输入按既有语义处理，禁止静默补 0 或伪造）。
2. **V1.6A Market Confirmation PASS**：tag `v0.4d-market-confirmation`（2026-08-30 已验收，
   192 passed + network opt-in 通过）。
3. **R2 资产先验矩阵调研完成并经协调员验收**：已归档
   `docs/research/2026-08-30_R2_asset_prior_matrix.md`。

## 启动 Prompt

```text
你接手的是一个已完成 V1.6A（v0.4d）的现有仓库（tag v0.4d-market-confirmation，
192 passed）。你的角色是 V2 Asset Compass 开发窗口。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md（§8 资产池、§13 Asset Score、§15 版本顺序）
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md（§11 Asset Layer 约束、§12 Validation 红线）
5. docs/tasks/55_V2_ASSET_COMPASS.md（本任务书）
6. docs/research/2026-08-30_R2_asset_prior_matrix.md（先验矩阵经济学依据 + 头部批注）

然后：
- 运行 baseline：python -m pytest（应 192 passed）
- 运行 python scripts/macro_report.py 与 python scripts/market_report.py 确认起点
- 对照 CURRENT_STATE 验证实际状态，冲突以代码为准并先报告
- 不重写任何 frozen components

本窗口只负责 V2 Asset Compass 资产层。
```

## R2 → config 转写规则（硬约束，缺一不可）

写在 `config/assets.yaml` 的头部注释中，并在验收时逐条核对：

1. **券商研报的胜率/相关系数只能支撑 importance tier，不得作为权重数值依据**
   （R2 档案头部批注 2）；权重数值只来自 R2 给出的 prior range（先验区间，非精确 beta）。
2. **"超额流动性"映射以系统 D3 定义为准**：D3 = M2 YoY − 私人社融 YoY
   （00_MASTER_SPEC §5）；R2 档案的"超额流动性"是 M2−名义GDP 口径（头部批注 3）——
   两者机理同向但不是同一指标，先验矩阵映射不得直接套用 R2 的数值表述。
3. **符号约定必须写入 config**：利率债/信用债 `+` = 价格上涨/收益率下行；
   CNY `+` = 人民币升值（USD/CNY 下行）；权益/商品/黄金 `+` = 价格上涨。禁止隐式假设。
4. **R2 赋 `ambiguous` 的项默认权重 0 并标注**，不得强行赋符号。已知清单：
   CN_CREDIT 对 CLI/PMI/硬活动、CN_CREDIT 对私人信贷脉冲、CN_GOV_BOND 对成本压力、
   GOLD 对私人信贷脉冲等（以 R2 摘要矩阵 `ambiguous` 项为准）。
5. **两条 regime/结构发现提示 V2.5 设计检验**：黄金对美债实际利率 2022-2024 脱钩
   （央行购金）、信用债对资金面高敏感（理财赎回负反馈）——V2 交付报告中必须把这两条
   列为 V2.5 的待检验项，不得在本窗口"修平"或忽略。

## 范围要点（负责人方案 §26–§27）

- 先验矩阵来自 R2 证据：每资产 × 每信号 = sign（+/-/0/ambiguous）+ importance tier
  （HIGH/MEDIUM/LOW）+ prior range（beta 先验区间）。全部可配置（`config/assets.yaml`）。
- **每资产输出契约（负责人方案 §27）**：
  `Score / View / 1M change / 3M change / Factor contribution / Signal contribution /
  Market confirmation / Confidence`
- **全链路可追溯**：Asset → Factor → Signal → Raw Series → Provider。
- **AssetScore = Σ beta × MacroFactor**；beta 来自先验区间（配置化，可设中值/区间）。
  **禁止用历史收益自动搜索权重**（V2.5 之前，00_MASTER_SPEC §13 / ARCHITECTURE §11/§12 硬约束）。
- **Asset Score ≠ 预期收益 ≠ 交易信号 ≠ 仓位建议**（00_MASTER_SPEC §13）。
  View 文案只允许顺风/逆风/中性描述，禁止买卖/仓位字样。

## 分阶段

### 第一阶段：Asset 配置与先验矩阵转写（先于一切引擎代码）

产出 `config/assets.yaml` + `docs/research` 交叉引用对照（每个 sign/tier/range 注明
R2 出处段落）。转写必须逐条对照 R2 摘要矩阵，diff 任何与 R2 不一致的决策都要在
交付报告中说明理由（如"按系统 D3 定义调整"）。

### 第二阶段：Asset 引擎

`src/macro_compass/assets/`（建议 config.py + engine.py 结构，参照 market/ 分层）：
- 纯函数：只读 factor 输出（`macro/factors.py`）+ market 层输出（`market/engine.py`），
  不读 raw series、不 import market 包做任何反向写；
- beta × factor score 求和 → 每资产 score；importance tier 决定置信显示与敏感性；
- Market confirmation 作为独立字段并列输出（确认/背离/混合），**不得**并入 Asset Score
  加权（隔离原则：确认层是并列观察，不是打分输入——若需加权须负责人批准）；
- Confidence：沿用数据质量三分量语义（coverage/freshness/source_quality），非预测概率。

### 第三阶段：报告入口

`scripts/asset_report.py`：7 资产 Score/View/1M/3M/contribution/confirmation/confidence
快照，写 `data/local/asset_scores.csv`；asset 输出需与 macro_report/market_report 同 as-of
可对齐。

## Acceptance Criteria

1. `config/assets.yaml` 落地，R2 转写 5 条规则全部显式执行（含头部注释 + 交叉引用），
   ambiguous 项权重 0 并标注；
2. Asset 引擎纯函数、只读 factor/market 输出；**无任何反向数据流**，且有测试证明
   （源码级 + 行为级，参照 V1.6A 隔离测试）；
3. 每资产输出契约 8 字段齐备，全链路可追溯（Asset→Factor→Signal→series→provider）；
4. **无历史收益搜索权重**（代码层面禁止 + 测试/评审确认）；
5. 无任何 BUY/SELL/仓位字样；View 只描述顺风/逆风/中性；
6. Market confirmation 字段并列展示，未并入 Asset Score 加权（如需加权需另批）；
7. 新增确定性 fixture 测试；网络测试 opt-in；
8. 报告入口 `asset_report.py` 输出 7 资产快照 + 逐资产贡献分解；
9. 完整 pytest PASS（192 基线 + 新增）；
10. V1/V1.2/V1.3/V1.5/V0.4c/V1.6A frozen components 未被重写；
11. 交付报告含 R2 转写对照表 + 与 R2 不一致决策的理由 + 两条 V2.5 待检验项声明。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V2 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 asset_report.py 并贴出完整输出；
- 检查是否存在任何 Asset→Factor/Market 的反向数据流（grep）；
- 检查 config/assets.yaml 的 R2 转写 5 条规则是否逐条满足；
- 检查是否存在历史收益搜索 / BUY/SELL / 仓位字样；
- 检查是否实现范围外功能（validation/UI/cloud 都算）；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README，写明：assets.yaml 先验矩阵、
引擎实现与隔离证明、asset_report 输出、R2 转写对照、未决项与 V2.5 待检验项。

建议 tag：

```text
v0.5-asset-compass
```

（下一阶段：**V2.5 Historical Validation**——负责人明确 V2 之后立即 V2.5，不做 UI，
防"看起来合理=有效"认知偏差；60 号任务书开工前补全，须含负责人新增的
Information Increment / Leave-One-Mechanism-Out 要求。）
