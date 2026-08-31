# Personal Macro Asset Compass — 协调员交接文档（Coordinator Handoff）

> **历史文档提示（2026-08-30）**：本文主体冻结于 V1.6A 交接期，内部的“当前状态”、测试数、
> 待办队列和 tag 指针已经过时，不再作为当前工程事实。当前接手请以
> `docs/01_CURRENT_STATE.md`、`docs/review/2026-08-30_final_delivery_report.md` 和实际
> `git log` / `git tag` 为准；当前阶段为 `v0.11-s3-property-pool` 后的 Shadow Operation。

**交接日期**：2026-09-01　|　**撰写**：状态同步窗口
**接收方**：下一任协调员窗口（负责 D1 验收及之后的全部协调工作）
**如何使用本文档**：这是你的工作手册。先通读一遍，然后按 §3 核实当前状态、按 §8 执行 D1 验收。
本文档自包含——所有背景都在文内或指向的仓库文件里，不依赖任何会话历史。

---

## 1. 你的角色：协调员窗口（不是开发窗口）

你**不写业务代码**。你的职责：

1. **验收开发窗口的交付**：核对测试、覆盖率声明、冻结组件、Git tag，然后确认或打 tag；
2. **起草任务书**：每个开发窗口开工前，`docs/tasks/` 里必须有一份完整的 Task Spec
   （对照 20/45/47/50 号的格式：窗口范围、启动 Prompt、逐条 Acceptance Criteria、
   Self Review Prompt、Handoff 要求、建议 tag）；
3. **管理外部只读调研窗口**：打包任务（见 §7.2）、抽验结果、归档进 `docs/research/`；
4. **维护项目记忆**：验收后更新 `docs/01_CURRENT_STATE.md`（下一任务指针、交接记录、
   Known Issues）、路线图变更写入 `docs/00_MASTER_SPEC.md` §15（必须带批准日期）；
5. **Git checkpoint 纪律**：确认每个阶段形成 tag；文档类改动单独提交，不与开发混杂。

**你不做**：替开发窗口写代码、替外部窗口做调研、替负责人做产品决策。
产品需求变更/新增 Core Signal/冻结组件变更 → 必须用户（项目所有者）批准。

## 2. 项目 30 秒概览

个人使用、本地优先、低维护、可解释的宏观资产配置辅助系统（Python，Windows 本地）。
数据获取 → 15 Core Signals + 6 Market + 3 Structural → 宏观因子（Growth/Inflation/
Domestic/Global）+ Regime → （进行中）市场确认层 → （未来）7 资产池顺风/逆风指引。

**优先级**：低维护成本 > 数据可追溯 > 解释力 > 稳定性 > 功能丰富度 > 模型复杂度。
**红线**（MASTER SPEC）：Market 不得反向修改 Fundamental；Asset Score ≠ 预期收益 ≠
交易信号；禁止 silent fallback；禁止 synthetic 进 production；禁止用未来收益调参；
未经批准不得新增 Core Signal、不得跳版本。

**负责人确立的 4 个 GATE**（评审一切进展的标尺，见 v0.4c 方案 §42）：
Economic Coverage（关键机制有真实数据吗）/ Explainability（能回到 raw source 吗）/
Empirical Value（历史上真有信息吗）/ Maintenance Cost（用户每月要动手几次）。

## 3. 当前状态快照（截至 2026-09-01）

```bash
cd D:\宏观监控体系
git log --oneline --decorate -8     # 应见 tag v0.4c-pre-market-stable 及其后
git status --short                  # 应干净
python -m pytest 2>&1 | tail -1     # 应 176 passed（D1 交付后会更多）
```

- **最新 tag**：`v0.4c-pre-market-stable`（V1.5E 数据稳定版）；
- **覆盖**：15 Core **15/15 READY**；FRED/X2 已恢复并 READY；D2/D4 生产历史已落地，
  但 release gate 为 **conditionally accepted**（采用公开累计报告差分 10 bn_cny 分辨率感知门，
  不等于高精度同口径无条件 PASS）；严格 live-PBC 原始解析验收门独立保留；Regime = TRANSITION（真实数据）。
- **进行中**：**Window D1 = V1.6A Market Confirmation**（任务书
  `docs/tasks/50_V1_6A_MARKET_CONFIRMATION.md`，含 G0 预置任务=G3 活源切换，
  这是负责人已批准的唯一 frozen signals.yaml 变更）；
- **D2/D4**：2018-01..2026-03 Wind 历史已落地，2026-04 起保留 PBC 尾部；备份与 DuckDB
  重建已完成。后续仅需按决策简报确认 release gate 策略，不重复执行 `--apply`。
- **外部调研已完成 3 轮**（全部归档并抽验，见 §12）。

**若实际状态与上述不符**：以代码和测试为准，先向用户报告差异。

## 4. 必读文档地图

```text
docs/00_MASTER_SPEC.md            项目宪法 + §15 版本顺序（含历次批准批注）
docs/01_CURRENT_STATE.md          当前状态/交接记录/Known Issues（你每次验收后更新）
docs/02_ARCHITECTURE.md           分层架构与各层约束（§4/§8/§9/§10 尤其重要）
docs/03_LLM_INTERACTION_GUIDE.md  窗口划分与盯梢话术
docs/tasks/20,30,40,45,47,50      已用任务书（新任务书的格式范本）
docs/tasks/52,55,60,65,70,80      占位任务书（52=R2 已完成；55=V2 待起草；60=V2.5；65=V2.6）
docs/research/                    3 份外部调研档案（含协调员抽验批注，§12 有索引）
docs/review/                      2 份给负责人的评审简报（历史决策依据）
README.md                         运行命令
```

## 5. 时间线与 tag 体系

| tag | 内容 | 备注 |
|---|---|---|
| v0.3-multisource-acquisition | V0→V1.2（初始 commit，V0/V1 tag 因 git 晚初始化跳过，已留档） | |
| v0.4a-signal-foundation | V1.3 注册表 + V1.5A 变换引擎 | |
| v0.4-macro-engine | V1.5B 信号引擎 + V1.5C 因子/Regime | 首次端到端 |
| v0.4b-data-quality | V1.2C 覆盖加固 + V1.5D 质量门（负责人框架批准） | 9/15 READY |
| v0.4c-pre-market-stable | V1.5E 数据稳定（负责人 v0.4c 方案批准） | 12/15 READY |
| （D1 交付后） | V1.6A Market Confirmation | **tag 命名见 §8 注意事项** |
| （V2 后） | Asset Compass | 负责人保留 v0.5 给 Asset Compass |

路线图（负责人批准的现行版）：V1.6A → V2 → V2.5 → V2.6 → V3 → V4；
V2 前置三 Gate：Economic Coverage PASS + V1.6A PASS + R2 先验矩阵（已完成，待转写）。
负责人明确：**V2 之后立即 V2.5，不做 UI**（防"看起来合理=有效"偏差）。

## 6. 冻结组件清单（累计，验收时逐条对照）

- **V1**：Wind importer、normalizer/validator、raw archive、SHA256 去重、
  canonical Parquet（真源）、DuckDB 缓存、质量检查、synthetic fixtures；
- **V1.2**：`data_sources/base.py` 错误契约（FetchError/ProviderUnavailable/
  ManualFetchRequired）、`updater.py` 状态语义（OK/STALE/FAILED/FALLBACK_USED/
  MANUAL_REQUIRED）、`data_sources.yaml` schema、indicators.yaml 为 series 元数据唯一真源；
- **V1.3/V1.5A**：signals.yaml 的 15+6+3 声明与字段语义、transforms 12 种白名单与
  纯函数契约、registry 校验与状态语义（READY/PARTIAL/MISSING_INPUT/DECLARED，
  v1.5D 增 WARMUP）；
- **V1.5B/C**：engine 输出契约（ARCHITECTURE §8 十列）与 score 映射规则、组合语义
  （single/fallback/difference/average + contribution breakdown）、factors 只读 Signal
  的硬约束、Confidence=数据质量非预测概率、regime 判定顺序、macro.yaml schema；
- **V1.2C/D**：三类 update policy（append/replace_window/full_refresh）、synthetic
  生产隔离（allow_synthetic 默认 false）、as-of/release-lag 语义、共享
  `resolve_signal_status`（任何报告脚本禁止复制状态逻辑）；
- **负责人批准的唯一例外**：D1 窗口可为 G3 活源切换修改 signals.yaml（仅限 G3 条目，
  OECD 须保留为 fallback，需 score 前后对照 + regression test）。

## 7. 核心工作流

### 7.1 开发窗口循环

```text
开窗（粘贴任务书启动 Prompt）→ 接手回复须含 baseline pytest 结果
（若未跑 baseline 就改代码 → 命令其停止，先跑 baseline）
→ Implement → 用户发 Self Review Prompt（任务书自带）→ 全 PASS
→ 用户发 Handoff Prompt → 窗口更新 CURRENT_STATE/README + 建议 tag + 停止
→ 【你】按 §8 程序验收 → 确认/打 tag → 起草下一份任务书 → 用户开下一窗
```

开发中盯梢话术（详见 03 指南 §9）：范围扩张 / 重写 frozen / 网络测试不稳定 /
silent fallback——四句话术原样使用。

### 7.2 外部只读调研窗口

已完成 3 轮，全部成功。**铁律模板**（每次任务包必含）：
端点必须实测才标 VERIFIED（附响应片段 ≤15 行 + 状态码）；失败逐条记录；不确定写
"不确定"；AKShare 结论须源码溯源 + 上游实测双证据；只读不改仓库；交付 Markdown 报告。

**抽验义务**：报告回来后你必须亲自 curl/请求 2–4 个关键端点核对数值（历史 3 轮：
3/3、4/4、2 通过+1 环境复现）。抽验结果与批注写进档案头部的
"协调员抽验记录"块，然后 `git add docs/research/ && git commit`。

**注意本机环境**：Git Bash；用户机器有代理，curl 国内站点可能需 `--noproxy "*"`
+ 浏览器 UA（中债 historyQuery 实测如此）；eastmoney push2 在本机间歇不可达
（环境 blocker，不代表端点失效）。

### 7.3 文档与 Git 纪律

- 每次验收后 CURRENT_STATE 必须更新：下一任务指针、§8 交接记录（Test Count/Tag/
  Modified Files）、§10 Known Issues；
- 路线图变更只在负责人批准后写入 MASTER SPEC §15，附日期；
- 协调员的文档提交独立成 commit（`docs: ...`），不混入开发改动；
- 提交前 `git status` 确认没有夹带 `data/` 下的运行产物。

## 8. D1（V1.6A）交付验收程序 ← 你的第一个任务

用户会说"D1 完成/交付了"。依次执行：

1. **Git 核查**：`git log --oneline --decorate -6`（D1 窗口应已自行 commit）；
   `git status --short` 应干净；
2. **测试**：`python -m pytest 2>&1 | tail -1`——应 ≥176 passed 且 0 failed；
   `python -m pytest -m network` opt-in 也应通过；
3. **G0 范围核查（红线）**：`git diff v0.4c-pre-market-stable..HEAD -- config/signals.yaml`
   ——**只允许 G3 一处变更**；OECD 输入须保留；应有 regression test；
   要求窗口出示 G3 切换前后同 as-of 的 score 对照；
4. **隔离核查（最重要红线）**：检查是否存在任何 Fundamental←Market 的数据流
   （grep macro/、signals/ 对 market 输出的引用）；窗口应有测试证明隔离；
5. **Market Data Matrix 核对**：交接报告须含六信号的 provider/history/frequency/
   freshness/READY 表；**≥5/6 real READY** 才算 PASS；未 READY 的须有 blocker 分类
   （network/source/environment），禁止 synthetic 凑数。对照
   `docs/research/2026-08-30_market_layer_sources.md` 的已验证端点抽查其实现
   （M3/M4 应走中债 historyQuery 或等价；M1 应有显式 fallback + FALLBACK_USED）；
6. **实机运行**：`python scripts/macro_report.py`（或新 market_report 入口）——
   六市场信号状态 + divergence 快照应输出；方向约定应在 config 中可见；
7. **M4 口径**：确认用「中票AAA 3Y − 国债 3Y」正式注册，未沿用 fixture 旧口径；
8. **Divergence 语义**：五状态 + macro/market direction + agreement + confidence；
   阈值配置化；**确认没有任何 BUY/SELL/仓位字样**；
9. **CURRENT_STATE/README** 已更新，Known Issues 含未 READY 信号与 G3 对照；
10. **tag 命名决策**：任务书建议 `v0.5-market-confirmation`，但负责人 v0.4c 方案 §17
    曾表示 **v0.5 留给 Asset Compass**。建议改用 `v0.4d-market-confirmation`，
    并在交接报告里向用户说明；若用户无偏好，按 v0.4d 执行；
11. 全部通过后：更新 CURRENT_STATE（下一任务 → V2/55 号），tag，然后按 §10 起草 55 号。

**红线（任何一条不满足 = 退回修复，不得带病接受）**：测试不全绿；signals.yaml 越权变更；
存在反向数据流；synthetic 进了 production；silent fallback；缺 blocker 分类的coverage 声明。

## 9. 待办队列（按 owner 标注）

| 事项 | Owner | 状态 |
|---|---|---|
| `wind_backfill_tsf.csv` 上传（社融增量+政府债券流量，建议含存量两列） | 用户 | 已确认可取得，待上传 |
| D2/D4 生产落地后的 release gate 取舍 | 负责人/协调员 | **已确认 conditionally accepted**：采用公开累计报告差分 10 bn_cny 门；严格 live-PBC 原始解析验收门独立保留；见 `docs/review/2026-09-01_d2_d4_release_decision_brief.md` |
| FRED/X2 历史恢复与 X1 overlap | 协调员 | X2=READY；X1 overlap 仍由独立硬门控制 |
| ChinaMoney WAF 限流、AKShare 接口变更风险、check_quality 混频警告 | 持续观察 | 见 CURRENT_STATE §10 |
| 本机代理分流实验（trust_env=False 按域名分流，可能同时解决 FRED 超时与 eastmoney push2） | 可建议 D1 或下窗顺手做 | 假设成立但未验证 |

## 10. 下一步任务起草指引（D1 验收通过后）

### 55 号任务书 = V2 Asset Compass（你的下一个主产出）

素材与硬约束（缺一不可，全部已在档案里）：

- **前置三 Gate**：Economic Coverage PASS（等 §9 的 wind 文件导入）、V1.6A PASS、
  R2 已完成（`docs/research/2026-08-30_R2_asset_prior_matrix.md`）；
- **R2 → config 的转写规则**（写在 R2 档案头部批注，务必沿用）：
  1. 券商研报的胜率/相关系数只能支撑 importance tier，**不得作为权重数值依据**；
  2. R2 的"超额流动性"是 M2−名义GDP 口径，系统 D3 是 M2−私人社融——映射以系统定义为准；
  3. 符号约定必须写入 config：利率债/信用债 `+`=价格上涨/收益率下行，CNY `+`=升值；
  4. R2 赋 `ambiguous` 的项默认权重 0 并标注，不得强行赋符号
     （CN_CREDIT 的 CLI/PMI/硬活动、私人信贷脉冲等）；
  5. 黄金-实际利率脱钩、信用债-资金面高敏感两条 regime 发现 → 提示 V2.5 设计检验；
- 输出契约（负责人方案 §27）：Score/View/1M/3M change/Factor contribution/
  Signal contribution/Market confirmation/Confidence，全链路可追溯；
- AssetScore = Σ beta × MacroFactor，beta 来自 R2 证据的先验区间（可配置），
  **禁止历史收益搜索权重**；Asset Score ≠ 预期收益 ≠ 交易信号 ≠ 仓位；
- 建议 tag：`v0.5-asset-compass`（与负责人 §17 的编号意图一致）。

### B 包外部调研（V2.6 前置，V2 开发期间派发）

V2.6 Structural Risk 数据深挖：BIS WS_CREDIT_GAP/WS_DSR 档案稳定性与更新行为
（第二轮已验证端点：`data.bis.org/static/bulk/WS_*.zip`）；S3 房地产脆弱性代理池
可获取性（70 城房价指数、国房景气指数、NIFD 居民杠杆率等——第三轮失败记录 F13 提示
南华旧接口已死、转 ccidx.com）。用 §7.2 铁律模板打包。

### 占位任务书

60（V2.5，含负责人新增的 Information Increment/Leave-One-Mechanism-Out 要求，
见 v0.4c 方案 §32）、65（V2.6）、70（V3 UI）、80（V4 Cloud）——开工前补全。

## 11. 已知问题与环境事实（截至交接）

- **FRED 间歇超时**（X2 历史/X1 overlap 的阻塞源）：端点已验证正确；timeout 45→90s
  + updater 一次重试已缓解未根除；代理分流是头号嫌疑（§9）；
- **eastmoney push2 本机间歇不可达**：环境 blocker（M1 CSI300 受影响），必须有
  显式 FALLBACK_USED + AKShare 兜底；
- **中债接口**：现行端点 `cbweb-pbc-web/pbc/historyQuery`（≤365 天/次，需浏览器 UA
  + 绕代理）；第一轮的 `cbweb-mn/pgxh/yzQuery`（国债专页）当时有效，第三轮 F07 证实
  `cbweb-mn/yield_curve/yzQuery` 路径已死——三条路径并存过，实现以实测为准；
- **ChinaMoney**：WAF 限流（pageSize≤50、高频 403），adapter 已限速退避；
- **GSCPI/OECD 为可修订序列**：full_refresh/replace_window + vintage snapshot 已配置；
- **政策利率**：PBOC OMO live 自动持久化已验证，manual 台阶文件仅历史 bootstrap，
  月维护成本≈0；
- **数据现状**：G2/G4 仅 30 个月历史（NBS 解析起点），V2.5 前需按负责人方案 §29-31
  建 Historical Coverage Matrix 并评估 Wind 一次性回填（PMI 分项/核心CPI/房地产历史）；
- **开发环境**：Windows + Git Bash；Python 3.11+；`pip install -e .`；
  所有命令在仓库根目录执行。

## 12. 外部调研档案索引（均已抽验+批注）

| 档案 | 内容 | 对下游的用途 |
|---|---|---|
| docs/research/2026-08-29_data_sources_survey.md | 第一轮：FRED 直链/ChinaBond 新端点/Chicago Fed/GSCPI/NBS 发布页等 | provider 任务书素材 |
| docs/research/2026-08-30_data_layer_round2_validation.md | 第二轮：东财上游全表/MOFCOM 缺政府债券/DR007 起点 2017-06/发布日历/BIS | Gate A/B 执行依据 |
| docs/research/2026-08-30_R2_asset_prior_matrix.md | R2：7 资产 × 15 驱动先验矩阵（符号/分层/机制/文献） | **55 号任务书核心素材** |
| docs/research/2026-08-30_market_layer_sources.md | 第三轮：M 层六信号端点实测/M6 选型/发布日历 | D1 执行依据（已作增补发给 D1） |

## 13. 关键决策记录（谁批准了什么）

- 2026-08-29 负责人框架：插入 V1.2C+V1.5D 双 Gate；Structural Risk 后移 V2.6；
- 2026-08-30 负责人 v0.4c 方案：Gate A/B 验收 PASS（9/15 属诚实交付）；插入 V1.5E；
  V1.6A 独立成窗；V2 前置 R2；V2 后立即 V2.5；synthetic fixture 永久保留
  （production 隔离已足够，不再做"自动退役"）；4 GATE 管理框架；
- 2026-08-30 用户批准：G3 活源切换（授权 D1 修改 signals.yaml 仅限 G3）；
  D2/D4 回填走 Wind（用户将提供文件）；
- 2026-08-30 用户指示：D1 交付后的全部协调工作移交新协调员窗口（即你）。

## 14. 红线清单（任何时候都不做）

1. 不替开发窗口写业务代码、不替外部窗口做调研；
2. 不在无用户批准下：改产品需求、新增 Core Signal、变更冻结组件、跳版本；
3. 不接受任何"带病"交付：测试不全绿、越权变更、反向数据流、synthetic 进
   production、silent fallback、无 blocker 分类的覆盖声明；
4. 不让任何窗口"顺手"开始下一版本——每个窗口止步于自己的任务书；
5. 不轻信任何未经你抽验的外部报告结论（尤其端点与数值）；
6. 不在 CURRENT_STATE 之外堆积长日志——历史由 Git 承担。
