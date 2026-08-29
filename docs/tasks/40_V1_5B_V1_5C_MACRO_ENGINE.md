# Task — V1.5B Signal Engine + V1.5C Macro Factor Engine

## 窗口范围

建议同一个窗口完成：

- V1.5B Signal Engine
- V1.5C Macro Factor Engine

完成后系统首次输出宏观状态（Factor + Regime）。本窗口**不做任何资产映射**。

## 启动 Prompt

```text
你接手的是一个已经完成 V1.3 + V1.5A 的现有仓库。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md
5. docs/tasks/40_V1_5B_V1_5C_MACRO_ENGINE.md

然后：
- 查看 repository tree
- 运行 python -m pytest 建立 baseline（应为 100 passed）
- 运行 python scripts/signal_status.py 与 transform_smoke.py 确认起点状态
- 如文档与代码冲突，以代码和测试为事实并先报告差异
- 不重新初始化项目
- 不重写 V1 / V1.2 / V1.3+V1.5A frozen components

本窗口只负责 V1.5B Signal Engine + V1.5C Macro Factor Engine。
```

## V1.5B Signal Engine

### 要求

1. 读取 `config/signals.yaml`，对每条 **layer=core** 的 signal 计算：
   - `level`：transform 链输出作为 level basis，再映射为 `level_score`；
   - `momentum`：`momentum_transform` 输出，映射为 `momentum_score`；
   - `score`：`level_weight * level_score + momentum_weight * momentum_score`
     （权重来自 registry，配置驱动，禁止代码硬编码或自动搜索权重）；
2. **composite 信号**（多 inputs）：聚合方式必须可解释（如等权 average、
   显式声明的优先级 fallback），并输出每个 input 的 contribution breakdown
   （ARCHITECTURE §8 硬性要求）；
3. 输出契约严格遵循 ARCHITECTURE §8：

   ```text
   signal_id, date, level, level_score, momentum, momentum_score,
   score, freshness, coverage, status
   ```

4. status 与 registry 语义一致（READY / PARTIAL / MISSING_INPUT / DECLARED）；
   输入不足的日期输出显式 status 与 null score，不得静默补 0；
5. `coverage` = 可用输入占比；`freshness` = 最新观测距 today 的陈旧度
   （对照 data_sources.yaml 的 max_staleness_days，超期视为 stale）；
6. 计算函数纯函数化：输入 canonical DataFrame + registry 声明，输出 signal 表。
   禁止网络访问、禁止写库副作用（持久化由独立脚本/存储层完成）；
7. score 映射（basis → score）必须有明确定义并在文档中说明
   （例如 robust z-score 截断到 [-3,3] 后线性映射到 [-1,1]；
   percentile 直接映射到 [0,1]）。禁止黑箱函数。

## V1.5C Macro Factor Engine

### 要求

1. 只读取 Signal 输出，**不得直接跳回 raw series**
   （ARCHITECTURE §9 硬性约束）；
2. 聚合四个 factor：growth / inflation / domestic_financial / global_financial；
   聚合按「机制 → factor」层级进行，**禁止把所有原始序列拉平直接平均**
   （MASTER SPEC §11）；
3. 每个 factor 输出：
   - factor score（基于其下 signal scores 的加权聚合，权重可配置，默认等权）；
   - **Breadth**：支持当前方向的不同经济机制数量（不是序列条数）；
   - **Confidence**：至少分解 coverage（signal 可用比例）、freshness（数据陈旧度）、
     source quality（可从 data_sources.yaml 的来源分级读取）；
     Confidence 是数据质量描述，**不是预测概率**；
4. **Regime**（仅由 growth × inflation 两轴驱动）：
   - Growth ↑ + Inflation ↑ = Reflation
   - Growth ↑ + Inflation ↓ = Goldilocks
   - Growth ↓ + Inflation ↑ = Stagflation
   - Growth ↓ + Inflation ↓ = Deflationary Slowdown
   必须支持 Mixed / Transition / Low Confidence / No Signal 状态；
   阈值配置化（config 中显式声明），不硬编码；
5. Factor 输出必须可追溯：Factor → Signal → series_id → source；
6. 提供一个报告命令（如 `scripts/macro_report.py`），输出最新一期的：
   全部 core signal 状态与 score、四个 factor（score + breadth + confidence）、
   当前 regime 及其判定依据。这是人工验收的主入口。

## 推荐目录

```text
src/macro_compass/signals/
├─ engine.py          # V1.5B：signal 计算（registry.py 保持只读不动）
src/macro_compass/macro/
├─ factors.py         # V1.5C：factor 聚合 + breadth + confidence
├─ regime.py          # V1.5C：regime 判定
scripts/macro_report.py
config/macro.yaml     # factor 权重、regime 阈值等（如无配置需求可并入现有 yaml）
```

目录命名可微调；signals/registry.py、transforms/ 为 frozen，只调用不改写。

## 数据现状提醒

截至 V1.3+V1.5A，15 个 core signal 中仅 G1/G3/G5 等少数 READY，
多数为 MISSING_INPUT（清单见 `python scripts/signal_status.py`）。
要求：

- 引擎必须在这种数据状态下优雅运行并输出真实状态；
- factor 的 coverage 低时 Confidence 必须如实反映（低 coverage → 低 confidence）；
- **禁止**为提高 coverage 而新增 provider、伪造数据或放宽 data_sources 配置；
- 不得把 synthetic fixture 数据当作真实信号输出（报告须能区分数据来源为
  synthetic / real / mixed，synthetic 来源的 signal 必须标注）。

## 禁止

- Market Confirmation（M1–M6 引擎）、Structural Risk 引擎（V1.6）
- Asset Score / Asset Compass（V2）
- forward return、历史回测（V2.5）
- ML / HMM / 任何权重自动搜索
- 修改 canonical 契约、data_sources 契约、signals.yaml 的 15+6+3 声明

## Acceptance Criteria

1. 全部 15 core signal 按输出契约产出（含 READY 与 MISSING_INPUT 状态的信号）；
2. composite 信号提供 contribution breakdown；
3. score 映射规则明确、文档化、无黑箱；权重全部来自配置；
4. 四个 factor 按「机制 → factor」层级聚合，无拉平平均；
5. Breadth 与 Confidence（coverage/freshness/source quality）正确输出；
6. Regime 判定含 4 象限 + Mixed / Transition / Low Confidence / No Signal，
   阈值配置化；
7. Factor 只依赖 Signal 输出，代码中无绕过 signal 层读取 raw series 的路径；
8. synthetic 与 real 数据来源在报告中可区分；
9. `scripts/macro_report.py` 一次运行输出完整最新快照；
10. 新增逻辑有确定性单元测试（用构造的 signal/transform fixture，不依赖网络），
    完整 pytest PASS（原 100 + 新增全过）；
11. V1 / V1.2 / V1.3+V1.5A frozen components 未被重写。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V1.5B + V1.5C Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 python scripts/macro_report.py 并贴出完整输出；
- 检查 factor 聚合是否只依赖 signal 输出；
- 检查是否存在任何权重自动搜索或黑箱映射；
- 检查是否实现了范围外功能（market/asset/回测都算范围外）；
- 检查 frozen components 是否被修改；
- 列出本次修改文件与所有已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README（新增 macro_report 命令说明），
写明：signal engine 输出契约落地情况、factor/breadth/confidence/regime 实现情况、
当前真实数据下的 regime 快照、仍 MISSING_INPUT 的 series 清单。

建议 tag：

```text
v0.4-macro-engine
```

（下一窗口 Window D：V1.6 Market Confirmation + Structural Risk + V2 Asset Compass。）
