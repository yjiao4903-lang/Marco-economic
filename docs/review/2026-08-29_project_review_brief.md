# Personal Macro Asset Compass — 项目进展评审简报

**报告日期**：2026-08-29　|　**撰写**：协调员会话（非开发窗口）
**用途**：提交外部项目负责人评审。评审对象：项目健康度、数据获取策略、若干需拍板的设计决策。
**阅读前提**：无需访问代码仓库，本报告自包含；仓库内可交叉核对的锚点（tag/文件）已随文标注。

---

## 1. 项目是什么

个人使用、本地优先、低维护、可解释的宏观资产配置辅助系统（Python，Windows 本地）。
自动获取宏观与市场数据 → 压缩为 15 个核心基本面信号 + 6 个市场确认信号 + 3 个结构性风险
信号 → 形成宏观状态（Regime）→ 输出对 7 个大类资产的顺风/逆风指引。
**不是**：量化交易平台、自动交易系统、个股选股器、黑箱 AI 预测。

明确的长期优先级排序：低维护成本 > 数据可追溯 > 解释力 > 稳定性 > 功能丰富度 > 模型复杂度。

## 2. 开发模式（评审需知的背景）

采用「同一仓库 + 多个 LLM 开发窗口接力」模式。每个窗口只做一个版本增量，交接依靠四份
文档（MASTER SPEC / CURRENT_STATE / ARCHITECTURE / 交互指南）+ 当前任务书 + Git checkpoint。
协调员会话（本会话）负责：验收、Git tag、起草下一份任务书、外包只读调研任务。

版本路线与当前状态：

| 版本 | 内容 | 状态 | Git tag |
|---|---|---|---|
| V0–V1 | 数据层：Wind 手工导入、canonical Parquet（真源）、DuckDB 缓存、质量检查 | DONE（冻结） | —* |
| V1.2 | 多源自动获取：10 个 provider adapter、增量更新、状态输出 | DONE（冻结） | v0.3-multisource-acquisition |
| V1.3+V1.5A | 信号注册表（15+6+3 配置化）+ 12 种纯函数变换引擎 | DONE（冻结） | v0.4a-signal-foundation |
| V1.5B+V1.5C | 信号引擎（Level+Momentum 打分）+ 宏观因子引擎（Breadth/Confidence/Regime） | DONE（冻结） | v0.4-macro-engine |
| V1.6 + V2 | 市场确认 + 结构性风险 + 资产指南针 | **下一窗口（Window D）** | — |
| V2.5 / V3 / V4 | 历史回测验证 / Streamlit 看板 / 云同步 | 未开始 | — |

\* V1 单独的 tag 因 git 初始化晚于 V1 开发完成而无法回溯创建，已在文档留档，属流程瑕疵而非代码问题。

**质量基线**：当前 `python -m pytest` 137 passed / 0 failed（网络集成测试独立标记 opt-in，
不污染核心基线）。每个版本均有确定性单元测试，数据解析使用离线 fixture。

## 3. 当前系统的真实运行状态（2026-08-29 实机快照）

系统已能端到端运行：自动抓取 → canonical → 变换 → 信号打分 → 因子聚合 → Regime 判定，
全程状态显式、可追溯（Asset←Factor←Signal←原始序列←数据源）。

真实数据已稳定入库的序列（来自 OECD / ChinaMoney / NY Fed / PBOC）：
中国 CLI（410 期）、工业生产指数、零售销售指数、出口同比、美元/人民币中间价、
US SOFR、1 年期 LPR。

**核心问题——信号覆盖率严重不足**：15 个核心信号中仅 3 个可计算（G1/G3/G5，全部属
growth 因子），2 个部分可用（I1/D3），10 个因缺输入序列完全无法计算。当前 Regime 输出为
`NO_SIGNAL`——这是**数据缺口问题，不是引擎缺陷**（inflation/domestic/global 三个因子
coverage 为 0，引擎如实输出而非编造）。growth 因子当前 score −0.118，breadth=1（仅 1 个
机制支持，弱信号）。

## 4. 已解决的主要问题（记录供评审参考）

1. **FRED 网络超时**（V1.2 遗留）：外部调研窗口验证 `fredgraph.csv` 直链可用，
   三条 FRED 序列恢复成本低；
2. **ChinaBond 端点失效**：已找到替代接口 `pgxh/yzQuery`（实测 HTTP 200，数值核验一致）；
3. **Chicago Fed 下载 URL 缺失**：已找到直链 CSV（一份文件同时含 NFCI 与 ANFCI）；
4. **测试污染工作区**：pytest 曾每次重写仓库内 fixture 文件，Window C 已修复
   （生成改到 tmp_path）；
5. **窗口流程缺陷**：前两个窗口未形成 Git checkpoint，已由协调员补建并制度化
   （此后每个窗口自行 commit + tag，交接记录写入 CURRENT_STATE）。

## 5. 遗留问题清单（已知、未解决、不阻塞当前进度）

| # | 问题 | 影响 | 现状/缓解 |
|---|---|---|---|
| 1 | 10+2 个核心信号缺输入序列（DR007、TSF、政府债券融资、PPI、核心CPI、PMI分项、GSCPI、房地产销售、美债实际利率、广义美元等） | 系统输出能力受限（Regime 长期 NO_SIGNAL） | 调研报告已完成端点验证（见 §6），待转化为 provider 扩展任务 |
| 2 | FRED 在本项目运行网络下超时 | X1/X2/X3 依赖 manual list | 直链已验证；怀疑是网络环境问题，待复测 |
| 3 | AKShare 未安装（可选依赖） | CSI300 等走 MANUAL_REQUIRED | `pip install akshare` 即恢复 |
| 4 | check_quality 对 synthetic+real 混合序列报频率警告 | 噪音告警 | 过渡现象，真实数据覆盖后消失 |
| 5 | ChinaMoney WAF 限流（高频请求 403） | 更新频率受限 | adapter 已限速+退避 |
| 6 | G3 数据 120 天未更新（STALE） | growth 因子 freshness 分被拉低 | OECD 数据发布时滞属实，阈值评估见 §7-D |

## 6. 数据源调研结论（外部窗口完成，协调员抽验 3/3 通过）

调研报告全文已归档于仓库 `docs/research/2026-08-29_data_sources_survey.md`。要点：

- **P1 级可直接落地**：FRED 直链 CSV（美债实际利率/广义美元/ANFCI）、Chicago Fed NFCI
  直链、NY Fed GSCPI 直链 CSV、ChinaMoney DR007 静态 CSV、ChinaBond 新接口；
- **P2 级需网页解析**：NBS 新闻发布页（PMI 分项、核心 CPI、PPI、房地产累计值）——
  NBS 数据门户有 WAF 反爬（403），只能走新闻稿解析路线；
- **P3 级备选**：AKShare（社融、PMI、CPI 等中国序列的兜底）；
- **需注意的坑**：ChinaMoney DR007 文件仅滚动保留 66 个交易日（历史回填须走 AKShare 或
  Wind）；GSCPI 为 PCA 模型输出、全历史逐月修正（更新机制须支持全量覆盖）；商品房销售
  为年初至今累计值（消费前需差分）；PBOC 官网 URL 动态易变（社融类不建议硬编码抓取）。

## 7. 需要项目负责人深度评估并拍板的点

按影响排序。每条给出协调员建议，但决策权在外部负责人。

### A. 关键路径决策：先补数据还是先做 V1.6+V2？

当前状况：模型引擎（V1.3–V1.5C）已就位但 12/15 信号无数据可算；下一版本 V1.6+V2
（市场确认 + 资产指南针）在此状态下开发，只能用 3 个真实信号 + synthetic 数据调试。
**两个选项**：
- 选项一（协调员建议）：**插入一个轻量 provider 扩展窗口**（V1.2 范围内的增量，不跳版本
  ——内容为已验证端点的 adapter 实现 + 数据源配置，工作量约半个窗口），把 P1 级序列
  先打通，再做 Window D；
- 选项二：按原计划直接 Window D，数据缺口留待以后补。
评审要点：选项一推迟 V1.6/V2 约 1 个窗口周期，换取 Window D 开发与验收时的真实数据
覆盖率大幅提升；是否符合"不跳版本"原则请负责人确认（协调员认为 provider 增量属于
V1.2 既定范围，不构成跳版本）。

### B. 分数映射的先验口径问题

各信号的 score scale 全部为手定先验（如 G1 level=3.0、G5 level=0.15），未做历史拟合
（这是有意为之，防止过拟合）。但 G5 的 momentum 分已长期贴 ±1 截断边界，提示先验
宽度可能失真。**评审要点**：这些先验值应在什么时点、用什么标准校准？协调员建议：
V2.5 历史验证阶段统一评估，当前阶段只在"贴边界"信号上做显式记录，不逐个调参。

### C. PARTIAL 但不可计算的判定规则

I1（fallback CPI 数据仅 36 个月 < rolling_percentile 窗口 60）与 D3（difference 组合缺
一条腿）状态为 PARTIAL 但 score 为 null——引擎不静默补 0，这是符合项目原则的行为。
**评审要点**：是否接受"PARTIAL 且长期 null"作为常态（等数据补齐），还是允许对窗口
做数据量自适应（如 min(60, 可用样本数)）？后者提高覆盖但引入口径不稳定性。协调员
建议保持现状（口径稳定优先），数据补齐后自然解决。

### D. STALE 阈值对慢频数据的合理性

G3 的输入（OECD 工业生产/零售指数）120 天未更新被判 STALE——这实际是 OECD 月度数据
的正常发布时滞叠加。**评审要点**：月度序列的 staleness 阈值是否应按"该序列的历史最大
发布间隔"动态设定（如 2×中位间隔），而非全局统一天数？影响 freshness/confidence 的
准确性。

### E. Window D 的范围是否过大

V1.6（6 个市场确认信号 + 3 个结构性风险信号引擎）+ V2（资产先验矩阵 + Asset Compass
输出）原计划同一个窗口完成，是 7 个窗口中范围最大的。协调员建议考虑拆分：Window D1
做 V1.6，Window D2 做 V2，各自形成 checkpoint。**评审要点**：拆分与否，以及结构性
风险信号（S1 信贷缺口/S2 偿债比率/S3 房地产脆弱性）所需的 BIS 季频数据目前无 provider
路由，是否接受 Window D1 期间这些信号以 synthetic 占位。

### F. synthetic 与 real 数据长期共存的治理

fixtures 为 synthetic 模拟数据，与真实数据在 canonical 中共存（靠 provenance 标记区分，
报告中已可区分）。**评审要点**：随着真实数据覆盖扩大，synthetic fixture 序列应何时、
以何种策略退役（如真实数据完全覆盖同 series_id 后自动停用）？目前无明确机制。

### G. 外包调研模式的制度化

本轮外部窗口调研（数据源验证）质量高、零仓库冲突，成功验证了"只读任务外包"模式。
**评审要点**：是否将该模式制度化——哪些任务类别可外包（调研/文档核对/数据源验证），
交付验收标准（端点实测+原文响应片段+失败记录），以及协调员抽验比例（当前为 3/7 全部
关键项）。另外 V2 的资产先验矩阵需要经济学依据支撑，可考虑下一轮外包调研对象。

## 8. 风险登记

1. **单点依赖**：真实数据入库依赖本机网络环境（FRED 超时疑似环境问题）；V4 云同步前
   无异地冗余，canonical Parquet 是唯一真源（有 DuckDB 可重建性，但 Parquet 本身无备份
   机制——建议纳入 V4 之前的日常备份习惯）；
2. **LLM 窗口质量波动**：窗口间能力/纪律有差异（第一个窗口未做 commit），依赖任务书
   的硬约束 + 协调员验收兜底；任务书质量是最大杠杆；
3. **数据源脆弱性**：中国数据源（NBS WAF、PBOC 动态 URL、ChinaMoney 限流）结构上比
   美欧官方 API 脆弱，fallback 链与 manual 流程（Wind 手工导入）是必要兜底，但 Wind
   manual 比例上升会侵蚀"低维护"目标；
4. **V2.5 之前模型未经验证**：所有打分/聚合/Regime 阈值均为先验，历史预测能力在
   V2.5 前未知——文档已明示 Asset Score ≠ 预期收益，但评审人应知晓系统当前结论
   尚无实证背书。

## 9. 附：仓库锚点（供有仓库访问权的评审人核对）

- 文档：`docs/00_MASTER_SPEC.md`（项目宪法）、`docs/01_CURRENT_STATE.md`（最新交接状态）、
  `docs/02_ARCHITECTURE.md`、`docs/03_LLM_INTERACTION_GUIDE.md`、`docs/tasks/`（各版本任务书）
- Checkpoint：`v0.3-multisource-acquisition` → `v0.4a-signal-foundation` → `v0.4-macro-engine`
- 实机验证入口：`python -m pytest`（137 passed）；`python scripts/macro_report.py`（宏观快照）；
  `python scripts/signal_status.py`（信号覆盖率）；`python scripts/update_sources.py --dry-run`
- 调研档案：`docs/research/2026-08-29_data_sources_survey.md`
