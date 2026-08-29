# Task — V1.6A Market Confirmation（Window D1）

## 窗口范围

只做市场确认层（M1–M6）。**不做 Asset Compass、不做 Structural Risk、不做 UI**
（负责人 2026-08-30 批准的窗口划分：V1.6A 独立成窗，V2 待三前置 Gate 后另开窗口）。

## 启动 Prompt

```text
你接手的是一个已经完成 v0.4c 的现有仓库（tag v0.4c-pre-market-stable，176 passed）。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md（§10 Market Layer 约束）
5. docs/tasks/50_V1_6A_MARKET_CONFIRMATION.md
6. docs/research/2026-08-30_data_layer_round2_validation.md（发布日历与 provider 现状）

然后：
- 运行 baseline：python -m pytest（应 176 passed）
- 运行 signal_status / macro_report 确认起点
- 对照 CURRENT_STATE 验证实际状态，冲突以代码为准并先报告
- 不重写任何 frozen components

本窗口只负责 V1.6A Market Confirmation。
```

## G0 预置任务（负责人已批准的唯一 signals.yaml 变更）

G3 Hard Activity 活源切换：NBS 增速序列为 live 输入，OECD 工业生产/零售保留为
historical backfill 与 fallback。要求：

1. 修改 `config/signals.yaml` 中 G3 的 inputs 声明（声明顺序即优先级，
   沿用 engine 的 fallback 历史偏好语义，不新增机制）；
2. OECD 序列保留在 inputs 中作 fallback，不得删除；
3. 变更前后对 G3 做同 as-of 的 score 对照并记录（进交接报告）；
4. 增加 regression test 锁定新声明；
5. **除 G3 外不得触碰 signals.yaml 的任何其他条目**。

## 第一阶段：Market Data Readiness（先于一切引擎代码）

产出 Market Data Matrix 并写入交接报告：

| Market Signal | Provider (primary/fallback) | History 起点 | Frequency | Current Freshness | READY? |

六个信号与已知起点：

- M1 CSI300：Eastmoney push2（环境 blocker 已知）→ AKShare 兜底；
- M2 Hang Seng Index：AKShare / 其他公开源（需本窗口验证）；
- M3 China 10Y Government Yield：ChinaBond `pgxh/yzQuery`（已验证）；
- M4 AAA Credit Spread：ChinaBond/ChinaMoney 路由（需验证；若无公开自动源，
  如实标 MANUAL_REQUIRED，禁止凑数）；
- M5 USD/CNY：ChinaMoney 中间价（已在库）；
- M6 Industrial Commodity / Copper proxy：AKShare（SHFE/LME 现货或期货代理）
  或 Wind manual（需本窗口验证并声明口径）。

要求：

1. 全部走既有 `data_sources` 框架 + `data_sources.yaml` registry，不新造架构；
2. 新增/变更路由遵守 V1.2 冻结契约（provider/original_source、错误契约、状态语义）；
3. **最低 5/6 real READY** 才算 Market Data Readiness PASS；达不到时按
   network/source/environment blocker 分类如实记录；
4. 禁止 synthetic 进入 production Market Confirmation。

## 第二阶段：市场信号计算

首版统一计算（复用 transforms 白名单，不新增变换）：

```text
1M move、3M move、6M trend、rolling percentile
```

方向约定必须配置化并写入文档（禁止隐式假设）：

- M1/M2：指数上涨 = positive；
- M3：收益率变动需与宏观语境对齐（收益率下行在增长下行语境 = 债券牛市信号），
  首版以「收益率下行 =宽松/牛市方向」声明并在报告中说明局限；
- M4：利差走阔 = negative；
- M5：USD/CNY 上行 = 人民币贬值 = 国内金融条件转弱；
- M6：商品上涨 = positive。

Market 层只输出市场价格方向信息，**不得反向修改任何 Fundamental Score**
（00_MASTER_SPEC §4 硬约束）。

## 第三阶段：Divergence 引擎

每个市场信号输出确认状态：

```text
CONFIRMED_POSITIVE / CONFIRMED_NEGATIVE /
POSITIVE_MACRO_DIVERGENCE / NEGATIVE_MACRO_DIVERGENCE / MIXED
```

并保留：macro direction、market direction、agreement、confidence。
阈值配置化（config/macro.yaml 或新 market.yaml 段），不硬编码。
**禁止**把 Divergence 翻译成 BUY/SELL 或任何仓位建议。

## 禁止

- Asset Compass / Asset Score（V2）
- Structural Risk（V2.6）
- UI / Cloud / ML
- synthetic production
- silent fallback
- 修改 Fundamental 层任何引擎/权重/除 G3 外的 registry 声明

## Acceptance Criteria

1. G0 完成：G3 活源切换落地，OECD fallback 保留，score 对照与 regression test 在案；
2. Market Data Matrix 完成，≥5/6 real READY；
3. M 层计算全部复用 transforms 白名单，方向约定配置化且文档化；
4. Divergence 五状态 + 四元组输出实现，阈值配置化；
5. Market 层与 Fundamental 层隔离：无任何反向修改路径，且有测试证明；
6. 新 provider 有确定性 fixture 测试；网络测试 opt-in；
7. 报告入口（macro_report 或新 market_report）输出六信号状态 + divergence 快照；
8. 完整 pytest PASS（176 基线 + 新增）；
9. real-data smoke：对已 READY 的市场信号输出真实 divergence 状态；
10. V1/V1.2/V1.3/V1.5/V0.4c frozen components 未被重写（G0 除外，且仅限 G3）。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V1.6A Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行市场层报告命令并贴出完整输出；
- 检查是否存在任何 Fundamental←Market 的反向数据流；
- 检查 signals.yaml 是否只有 G3 一处变更；
- 检查是否实现范围外功能（asset/UI/cloud 都算）；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README，写明：Market Data Matrix、
divergence 实现与阈值、G3 切换前后对照、未 READY 的市场信号与 blocker 分类。

建议 tag：

```text
v0.5-market-confirmation
```

（下一阶段：V2 Asset Compass——须待 Economic Coverage Gate 完成 + 本任务 PASS +
R2 先验矩阵转写，见 docs/tasks/55。）
