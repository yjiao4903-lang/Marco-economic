# Personal Macro Asset Compass — Gate A/B 交付评审简报（数据质量专项）

**报告日期**：2026-08-30　|　**撰写**：协调员会话（非开发窗口）
**评审对象**：V1.2C Data Coverage Hardening（Gate A）+ V1.5D Signal Quality Gate（Gate B）交付结果
**Git 锚点**：tag `v0.4b-data-quality`（commit `656d120`）　|　**测试基线**：163 passed / 0 failed（另 6 个网络集成测试 opt-in）
**本报告自包含**，无需仓库访问权；仓库核对锚点随文标注。

---

## 1. 一句话结论

数据质量专项按负责人框架完成两个 Gate：**真实数据覆盖率从 3/15 提升到 9/15 READY
（另有 2 个 WARMUP、1 个 PARTIAL）**，系统首次输出真实宏观状态（Regime = TRANSITION）；
框架设定的 12/15 目标**未达成，但缺口全部为如实分类的客观 blocker**（数据源缺失/网络），
未使用 synthetic 填充、未缩短 rolling window、未放宽阈值——交付诚实性经协调员逐条核验。

## 2. 本轮完成了什么

### Gate A — 数据覆盖（V1.2C）

1. **新增/修复 provider 与数据链**（与两轮外部调研结论逐条对应）：
   - X3 ANFCI：Chicago Fed 直链 CSV 落地（周频，1989 年起可回溯）；
   - G2 PMI 新订单、I2 PPI：东方财富 datacenter API 直连 adapter
     （即调研确认的 AKShare 上游；已按数据源政策记录 provider=EASTMONEY /
     original_source=NBS）；
   - G4 房地产销售：NBS 新闻稿解析 + 累计值→单月值差分（含年初重置/跨月/缺月/
     修订/异常下降五类 fixture test）；
   - D1 资金利率：ChinaMoney DR007（2017-06 起）+ PBOC OMO 路由 + 人工转录利率台阶；
   - D2/D4 社融：PBOC 月度金融统计数据报告链路打通（累计差分为月度流量，
     replace_window 模式）；
   - I3：GSCPI（NY Fed 直链 CSV，full_refresh 全量覆盖模式，raw vintage 留存）；
   - 依据调研发布日历落地了三类 update policy：append / replace_window / full_refresh；
   - AKShare 已安装并激活为 P3 兜底路由。
2. **Synthetic 生产隔离**：生产入口默认 `allow_synthetic=false`，
   I1 的 synthetic CPI 兜底被正式切断（这正是 I1 当前 MISSING 的原因，属预期行为）；
3. **Freshness 元数据**：按调研的发布日历配置各序列 expected_release_lag；
4. **Snapshot/vintage**：真实抓取留存 asof_date/provider/original_source/fetch_time，
   可修订序列（GSCPI、OECD）保留 raw snapshot，开始积累自有 vintage history。

### Gate B — 信号质量（V1.5D）

1. **WARMUP 状态**正式纳入引擎契约：有真实数据但 minimum_history 不足 →
   status=WARMUP、score=null（D2/D4 即此状态，约 9 个月数据累积后自动转 READY）；
2. **饱和度诊断**：全部核心信号输出 24M/60M 饱和度比例（|score|≥0.95 占比），
   用于发现先验 scale 失真（当前 G5 momentum、G4 level 存在贴边，详见 §6）；
3. **Composite 显式覆盖**：available/required inputs + coverage 逐项输出；
4. **As-of 一致性**：引入 release lag 语义，不假设观测日当日可知；
5. 新增 `python scripts/signal_quality.py` 质量报告。

## 3. 当前真实覆盖全景（2026-08-30 实机核验）

| 因子 | READY | 状态明细 |
|---|---|---|
| Growth | **5/5** ✅ | G1–G5 全部 real、READY |
| Inflation | **2/3** | I2/I3 READY；I1 MISSING（核心 CPI 仅存在于 NBS 解读栏目，路由已备好待命中） |
| Domestic | **1/4** | D1 READY；D2/D4 WARMUP（真实数据已在流入，差分历史回填未做）；D3 PARTIAL（缺社融存量腿） |
| Global | **1/3** | X3 READY；X1/X2 MISSING（FRED 本机网络间歇超时，endpoint 已验证正确） |
| **合计** | **9/15**（12/15 目标未达成） | 另：WARMUP 2、PARTIAL 1 |

**Blocker 分类**（框架 §16 要求，全部如实记录于 CURRENT_STATE §10）：

| 类型 | 项目 | 说明与出路 |
|---|---|---|
| network blocker | X1/X2（FRED） | 端点已验证正确，本机网络间歇超时；网络可用日运行 update 即自动补齐 |
| history warmup | D2/D4 | 数据链已通；列表页仅静态暴露近 4 个月，差分历史回填需 gov.cn 镜像或 manual 档案，否则约 9 个月后自然转 READY |
| source blocker | D3、I1 | 社融存量无自动可爬源（第二轮调研已证实）；核心 CPI 待 NBS 解读页命中 |
| environment blocker | CSI300 等 market 层 | 本机代理间歇问题，非本轮 Gate 范围 |

## 4. 系统首次输出真实宏观状态

```text
REGIME: TRANSITION
  growth    score -0.409（下行）   breadth 与 confidence 见 macro_report
  inflation score +0.125（中性，阈值带内）
```

判定逻辑透明可追溯（阈值 ±0.15 配置于 config/macro.yaml，growth 在带内 → TRANSITION
而非直接判 Deflationary Slowdown）。**重要提醒**：当前 breadth 仍低（growth 仅 3 个
独立机制支持）、部分信号 history 尚短（G2/G4 仅 30 个月），该结论**仍不具备投资参考
效力**，仅证明引擎在真实数据上端到端可信运行。

## 5. 开发窗口结论与外部调研的交叉印证

两轮外部只读调研（第一轮 3/3、第二轮 4/4 抽验通过）在本轮开发中得到了实现层面的验证：

- 东财上游端点方案、MOFCOM 社融源缺失政府债券、DR007 公开数据 2017-06 起、
  GSCPI 全历史修订需 full_refresh——全部与调研一致，开发窗口未发现调研幻觉；
- 开发窗口补充的新发现（调研未能覆盖的）：PBOC 报告列表页仅静态暴露近 4 个月
  （更早月份 JS 渲染）——这是 D2/D4 历史回填困难的真实根因；
- 调研档案与实现决策已形成闭环，`docs/research/` 两份档案可直接作为后续维护的
  数据源手册。

## 6. 协调员验收发现的问题（不阻塞，交下一窗口）

1. **状态显示不一致（小缺陷）**：`signal_status.py` 将 D2/D4 显示为 READY，
   而 `macro_report.py` 正确显示 WARMUP——两脚本 WARMUP 语义未同步，
   以 macro_report 为准，signal_status 需修复（1 处判断逻辑）；
2. **I1 fallback 腿疑问**：I1 声明 headline CPI 为正式 fallback（框架 §6），且东财
   CPI 端点两轮均已验证可拉，但 I1 当前两条腿全 MISSING——下一窗口应核查
   fallback 腿是漏配数据源还是解析未命中，而不是等核心 CPI 命中；
3. **饱和度确认**：G5 momentum、G4 level 分数贴 ±1 截断边（先验 scale 口径问题），
   饱和度诊断已如实报告；调整属 macro.yaml 显式变更，按冻结流程执行；
4. G3（OECD 工业/零售）数据 121 天未更新仍 STALE——OECD 发布时滞属实，
   freshness release-lag 配置的收敛效果需观察 1–2 个更新周期。

## 7. 需要负责人决策的事项

1. **Gate A 未达标（9/15 vs 12/15）的验收态度**：缺口全部为客观 blocker 且分类如实。
   协调员意见：**接受本轮交付**；X1/X2 网络恢复即 +2，D2/D4 历史回补后可达 12/15，
   覆盖率目标应作为滚动指标而非本轮 gate 失败处理；
2. **D2/D4 历史回填路线**：(a) gov.cn 镜像站爬取（开发工作，可行性未验证）、
   (b) Wind manual 一次性回填（人工约 1–2 小时）、(c) 等待 9 个月自然累积。
   协调员建议 (b)——成本最低且框架明确允许 manual 计入 REAL；
3. **政策利率人工维护点**：`data/manual_series/CN_POLICY_RATE_7D.csv` 为人工转录的
   利率台阶，PBOC 公告会自动覆盖近 20 个交易日，但**每次降息需人工追加台阶**——
   这是"低维护"目标下的一个长期人工成本项，请负责人知悉并接受（或后续指定
   自动化方案）；
4. **下一窗口派发批准**：V1.6A Market Confirmation（50 号任务书待起草），
   前置条件已满足（Gate B 完成、tag 已形成）。是否按原计划执行请负责人确认；
5. **评审简报 §7-F 遗留决策**：synthetic fixture 的退役策略仍未定（当前已做生产隔离，
   退役仅为磁盘与心智负担问题，不紧急）。

## 8. 项目全景时间线（累计）

| 阶段 | 内容 | tag | 覆盖率里程碑 |
|---|---|---|---|
| V0–V1 | 数据层（Wind 手工导入、canonical、DuckDB） | —* | — |
| V1.2 | 10 个 provider adapter、增量更新 | v0.3-multisource-acquisition | — |
| V1.3+V1.5A | 信号注册表 + 12 种变换引擎 | v0.4a-signal-foundation | 注册 15+6+3 |
| V1.5B+V1.5C | 信号引擎 + 因子/Regime 引擎 | v0.4-macro-engine | 首次端到端（3/15 real） |
| **V1.2C+V1.5D** | **数据覆盖加固 + 信号质量门** | **v0.4b-data-quality** | **9/15 real READY，Regime=TRANSITION** |
| 下一 | V1.6A Market Confirmation | （待派发） | — |

\* V1 tag 因 git 初始化晚于开发而跳过，已留档。

## 9. 附：核对锚点

- 实机入口：`python -m pytest`（163 passed）；`python scripts/macro_report.py`；
  `python scripts/signal_status.py`；`python scripts/signal_quality.py`；
  `python scripts/update_sources.py --dry-run`
- 调研档案：`docs/research/2026-08-29_data_sources_survey.md`（第一轮）、
  `docs/research/2026-08-30_data_layer_round2_validation.md`（第二轮）
- 状态文档：`docs/01_CURRENT_STATE.md`（§10 Known Issues 含全部 blocker 详情）
