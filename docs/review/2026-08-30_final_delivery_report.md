# Personal Macro Asset Compass — 最终交付报告（v0.11-s3-property-pool）

- **报告日期**：2026-08-30
- **评估对象**：`Personal Macro Asset Compass`（本地宏观监控与大类资产指引系统）
- **代码基线**：`git rev-parse HEAD` = `4f5a57f`（tag **`v0.11-s3-property-pool`**）
- **测试基线**：全量 pytest **全绿**（进度条计数约 263 项，含 Shadow/V4.6/S3 新增；
  `-m network` opt-in；0 failed）
- **用途**：本报告为**外部评估窗口**提供自包含的项目全貌、验证路径与已知限制。
  所有结论可经报告中的命令与文件复现；未编造任何数字、来源或测试结果。
- **交付定位**：V4.6 Empirical Validation Round 2 → **Shadow Operation 观察期**已启动；
  本窗口（87 号任务书）在观察期内完成**诊断层**开发（S3 代理池落地）并冻结 v0.11。

---

## 1. 评估导航（如何验证本报告）

仓库根目录：`D:\宏观监控体系`（Windows + Python 3.11+，`pip install -e .`）。

**建议按序执行的验证命令（只读/可重建）：**

```bash
cd D:\宏观监控体系
git log --oneline --decorate -20          # 版本里程碑（tag：v0.3→v1.0 + v0.11）
git tag -n                                # 全部稳定 tag 与语义
python -m pytest                           # 全量（约 263 项全绿；-m network opt-in）
python -m pytest -m network                # 网络集成测试（环境 blocker 可能 skip）
python scripts/signal_status.py            # 15 Core + 6 Market + 3 Structural 可用性
python scripts/macro_report.py             # 宏观快照：信号/四因子/Regime
python scripts/market_report.py            # 市场确认层：Matrix + Divergence 五状态
python scripts/asset_report.py             # 7 资产 Score/View/1M/3M/贡献/确认/置信
python scripts/structural_report.py        # S1/S2/S3 结构风险诊断（S3 代理池 PARTIAL）
python scripts/validation_report.py        # V2.5/V4.6 历史验证：五方法/LOMO/regime/verdict
python scripts/shadow_metrics.py           # Shadow 观察期方向一致性命中率（只读）
python scripts/historical_coverage.py      # 数据层历史覆盖矩阵
python scripts/cloud_sync.py --dry-run     # V4 云同步清单（config/raw/canonical）
python -m streamlit run src/macro_compass/ui/app.py   # V3 本地 Dashboard
```

**权威文档地图（事实来源）：**

| 文档 | 内容 |
|---|---|
| `docs/00_MASTER_SPEC.md` | 项目宪法：定位/最高优先级/15+6+3 信号/数据源原则/红线/版本顺序/§15 路线图 |
| `docs/01_CURRENT_STATE.md` | 当前状态/每版本交接记录/Known Issues（每次验收后更新） |
| `docs/02_ARCHITECTURE.md` | 分层架构与各层约束 |
| `docs/03_LLM_INTERACTION_GUIDE.md` | 多窗口接力开发流程 |
| `docs/COORDINATOR_HANDOFF.md` | 协调员工作手册：角色/验收程序/待办队列/红线 |
| `docs/tasks/85,86,87.md` | V4.5/V4.6/S3 任务书（含 Acceptance Criteria） |
| `docs/research/*.md` | 5 份外部只读调研档案（含 B 包调研 `2026-08-30_bpack_structural_survey.md`） |
| `docs/SHADOW_OPERATION_GUIDE.md` | Shadow Operation 观察期运营指南（3–6 个月，非开发窗口） |
| `docs/shadow/decision_journal.md` | 决策日志（DJ-001..005，观察期只登记不执行） |
| `docs/V46_EMPIRICAL_VALIDATION.md` | V4.6 经验验证报告（逐资产 Verdict + M3 regime + 专项） |
| `docs/review/*.md` | 给负责人的评审简报 |

---

## 2. 项目定位与设计原则

**定位**：个人使用、本地优先、低维护、可解释的宏观资产配置辅助系统。将主要宏观与市场
数据自动获取后压缩为少数彼此独立的机制信号，形成宏观状态，监测市场是否确认，输出大类
资产的**顺风/逆风指引**（非预期收益、非交易信号、非仓位建议）。

**明确非目标**：Wind/Bloomberg 仿品、高频量化、自动交易、个股选股、黑箱 AI 预测、
自动仓位组合优化器、新闻 NLP、云上计算（云只做数据镜像）。

**最高优先级**（MASTER SPEC §2）：
> 低人工维护成本 > 数据可追溯性 > 模型解释力 > 稳定性 > 功能丰富度 > 模型复杂度

**核心纪律（贯穿全部版本，v0.11 验收再次验证）**：权重/beta/阈值/信号声明为**声明先验，
不拟合、不搜索**；无 synthetic 进生产；无 silent fallback；资产层只读 factor 输出无反向流；
结构性诊断（S 信号）**永不进入 Asset Score**（源码级 + 行为级测试锁定）。

---

## 3. 版本里程碑与稳定 tag（截至 2026-08-30）

| Tag | 里程碑 | 语义 |
|---|---|---|
| v0.3-multisource-acquisition → v0.8-cloud-mirror | V0→V4 | 数据/引擎/市场/资产/验证/结构/UI/云镜像族 |
| v0.9-data-completion | V4.5 | 数据补全 + Coverage Matrix + source-transition + 版本纪律 |
| v0.10-empirical-validation | V4.6 | Empirical Validation Round 2（6 类如实 verdict + M3 regime + 专项） |
| **v0.11-s3-property-pool** | Shadow 观察期 J3 | Shadow 基建 + B 包调研归档 + S3 四类代理池（PARTIAL 如实）+ D2/D4 占位 + V4.6 验证产物 |

全部历史 tag 不重写、不覆盖；`v0.11` 指向干净 commit（`4f5a57f`，工作区无夹带运行产物）。

---

## 4. 当前工程状态快照（2026-08-30）

- **Fundamental Core：READY 14/15**。D2/D4 于本窗口按负责人指令以 **`WIND_PLACEHOLDER`**
  固定常数占位转 READY（2018-01..2026-03 历史；**2026-04 起保留真实 PBOC 观测**，source
  显式标记、不伪装真实、可被后续 `wind_backfill_tsf.csv` 导入按 (date) 覆盖）；剩 **X2
  WARMUP**（FRED 网络 blocker，H.10 fallback 已实战工作）。
- **Market Confirmation：6/6 real READY**（M1–M6 全部真实数据）。
- **V2 Asset Compass：7/7 real READY**（7 资产 Score/View/1M/3M/逐因子/逐信号贡献/市场
  确认/置信快照；资产层只读，无反向流）。
- **Structural Risk（V2.6 + 本窗口 S3）**：
  - S1 Credit-to-GDP Gap：**READY**（BIS 真实季频，2025-Q4 = −7.688%，BELOW_TREND）；
  - S2 Debt Service Ratio：**READY**（BIS 真实季频，2025-Q4 = 18.8%，ELEVATED）；
  - S3 Property Vulnerability：**PARTIAL（代理池 2/4）**——景气（国房景气，AKShare）+
    杠杆（居民杠杆率，AKShare）VERIFIED 可用；价格（70 城房价）与资金（到位资金）缺数据，
    **如实 PARTIAL，不硬塞弱代理、不伪装 READY**（`python scripts/structural_report.py`
    可复现）。S3 诊断 **不进入 Asset Score**（隔离测试锁定）。
- **V4.6 Empirical Validation（v0.10）**：逐资产 Verdict 六类如实输出（WEAKLY_SUPPORTED
  港股/工业商品、MIXED 信用债 3m 方向反转、NO_EFFECT_OR_WEAK A股/利率债/CNY、
  INSUFFICIENT_SAMPLE 黄金）+ M3 regime-dependent + Gold decoupling / Credit funding 专项 +
  LOMO 候选 growth:G3（不降级）。结论如实：**既不证实、也不证伪** 方向信息价值（样本约 21
  个月，wind 回填未到）；异象仅登记不改模型。
- **Shadow Operation（观察期）**：`scripts/shadow_metrics.py` 只读月度方向一致性命中率
  （`data/local/shadow/shadow_metrics.csv`）+ 指南 + 决策日志（DJ-001..005 预置待决项）。
  观察期红线：**不修改任何权重/beta/阈值/Signal/因子/Regime**；一切改动力议进日志，
  Product Stable Review 统一裁定。
- **V3 Local Dashboard（v1.0-local）**：Streamlit 只读四面板 + 全链路可追溯下钻，无买卖/仓位字样。
- **V4 Cloud Mirror（v0.8）**：Git 私有仓库同步 config/raw/canonical，本地隔离运行产物。

---

## 5. 本窗口（J3，87 号任务书）交付内容

1. **B 包调研归档**：`docs/research/2026-08-30_bpack_structural_survey.md`——BIS WS_\*
   稳定性（bulk CSV zip primary / SDMX fallback，CN 无 period 断点、无 breakpoint 标记）、
   S3 四类代理池逐项 VERIFIED/FAILED/不可得 + 建议路由（含 Failed Attempts Log，如实记录
   `RPT_ECONOMY_LOAN` 等报表配置不存在）。**待协调员抽验**（§7.2 铁律，抽 2–4 关键端点）。
2. **S3 代理池落地**（structural 诊断层）：四类组合代理（景气/杠杆 VERIFIED，价格/资金缺），
   equal-weight percentile composite；无数据 → 显式 `NO_SIGNAL`/`PARTIAL`，无 synthetic。
   多输入组合由 `structural/engine.py` 支持，`config/signals.yaml`/`structural.yaml`/
   `indicators.yaml`/`data_sources.yaml` 声明落地。
3. **Shadow 基建**：`scripts/shadow_metrics.py` + `src/macro_compass/shadow/`（只读监控，
   与 production 隔离，同 validation 契约）。
4. **D2/D4 固定常数占位**：`data/inbox/wind/wind_backfill_tsf_placeholder.csv` +
   `config/wind_mapping.yaml` 两列（占位与未来真实文件共用）；canonical 已含占位 +
   真实 PBOC 并存，source 可辨。
5. **测试与回归**：全量 pytest 全绿；S3/Signals/Validation 测试更新；fixtures 同步含
   TSF/GOV 两列。

---

## 6. 已知限制与后补项（如实）

| 项 | 状态 | 说明 / 后续动作 |
|---|---|---|
| Wind `wind_backfill_tsf.csv` | **后补空置（占位已落地）** | D2/D4 现为 `WIND_PLACEHOLDER` 驱动 READY；用户上传真实文件后 `import_wind.py` 按 (date) 覆盖，无需改代码 |
| X1 overlap check / X2 历史（FRED） | BLOCKED / WARMUP | FRED 网络恢复后自动补全；未 PASS overlap 前禁止 FRED 行并入 X1 |
| S3 价格/资金两类代理 | PARTIAL（缺数据） | 70 城房价定基口径仅 2022-12 起、资金端报表配置不存在；B 包已给 Wind manual 候选，待用户补 |
| V4.6 样本充足性 | 约 21 个月 | wind 回填未到；Product Stable Review 前不追加结论 |
| B 包调研抽验 | 待协调员 | 抽验后可在 87 号任务书登记 PASS |
| S3 代理组合方向 | provisional（direction: negative） | 观察期登记于决策日志；不自动改 |

---

## 7. 红线符合性（v0.11 验收）

- `git diff` 历史中 `config/assets.yaml`、Core Signal 声明、阈值、Regime 零改动
  （本窗口只动 structural 诊断层与数据/文档）；
- S1/S2/S3 **不进入 Asset Score**（源码 grep + 行为测试证明无数据流）；
- 无 synthetic 进生产、无 silent fallback、无未来收益调参；
- Shadow 观察期红线未触碰：一切拟议改动（DJ-001..005）仅登记、未执行。

---

## 8. 结论

本项目已完成 **V0 → V4.6 → Shadow Operation 启动** 全链路交付并冻结 **v0.11**：数据层
（15 Core 14/15 READY、6/6 Market、结构风险 S1/S2 真实 + S3 代理池落地）、验证层（V4.6
六类如实 verdict）、UI（V3 本地 Dashboard）、云镜像（V4）、观察期基建（Shadow）均已
落地且测试全绿。当前处于 **3–6 个月 Shadow Operation 观察期（非模型开发窗口）**：真实
样本外方向证据将逐月累积，Product Stable Review 后由负责人决定模型升级 / 信号精简 /
V5 方向。已知后补项（wind 回填、FRED、S3 两代理、B 包抽验）均显式登记，不阻塞。
