# Task — V2.6 Structural Risk（Window G）

> 状态：**已补全（协调员，2026-08-30）**。V2.5 交付后开窗。
> 素材来源：docs/research/2026-08-30_data_layer_round2_validation.md（任务 D：BIS 实测 +
> S3 代理池）、docs/tasks/65 原占位（背景与约束）、00_MASTER_SPEC §7/§12。
> 前置 B 包外部调研（BIS 档案稳定性 + S3 代理池可获取性）由协调员在 V2 期间派发，
> 本任务书按第二轮已验证端点撰写，B 包回来后补充更新行为细节。

## 窗口范围

只做 **Structural Risk 引擎**（S1 / S2 / S3 三条诊断信号）：中长期脆弱性监测。
**不做**：Asset Compass（V2）、Historical Validation（V2.5）、UI（V3）、Cloud（V4）、
组合优化、自动交易。

**核心约束（00_MASTER_SPEC §7 + 原占位任务书）**：
- Structural Risk **不进入短期 Asset Score**；
- 生产环境无真实数据时输出 `NO_SIGNAL`，**禁止 synthetic 占位**；
- 输出为诊断性质（中长期的脆弱性监测），与 V2.5 历史验证相互独立；
- 输入 BIS 季频序列为**新 provider 增量**（属 V1.2 范围，遵守 V1.2 冻结契约），
  config.py 已预留 quarterly frequency。

## 前置条件

1. **B 包外部调研完成并经协调员抽验归档**：BIS WS_* 档案稳定性与更新行为、
   S3 代理池可获取性（`docs/research/` 新档案；§7.2 铁律模板 + 抽验义务）；
2. **V2.5 PASS**（可选但建议，避免与验证窗口并行冲突）。

## 输入序列与数据源（已实测端点，第二轮档案任务 D）

### S1 Credit-to-GDP Gap（信贷/GDP 缺口）
- 数据集：BIS `WS_CREDIT_GAP(1.0)`；国家 `CN`，部门 `P`（Private non-financial sector）
- 数据类型：`A` actual ratio / `B` trend（HP 滤波）/ `C` gap（=Actual−Trend）——**S1 用 Type C**
- 历史起点：Type C **1995-Q4**；最新（实测）：2025-Q4 = **−7.6881%**
- 端点（已验证 HTTP 200）：
  - Bulk CSV Zip：`https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip`（~250KB）
  - SDMX REST：`GET https://stats.bis.org/api/v1/data/BIS,WS_CREDIT_GAP,1.0/Q.CN.P.A.C?format=sdmx-json`

### S2 Debt Service Ratio（偿债比率）
- 数据集：BIS `WS_DSR(1.0)`；国家 `CN`，部门 `P`
- 历史起点：**1999-Q1**（实测首值 10.1%）；最新：2025-Q4 = **18.8%**
- 端点（已验证）：Bulk CSV Zip `https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip`（~40KB）

### S3 Property Vulnerability（房地产脆弱性，代理池）
BIS 未直接编制细分中国房地产脆弱性指数，构建官方指标代理池（来源：第二轮档案 §3）：
1. **价格端**：70 城新建/二手住宅价格指数（月度环比/同比/定基，一线/二线/三线分化）；
2. **景气与投资端**：国房景气指数（阈值 100，当前 91–92 历史低位）、
   地产开发投资/新开工/施工/竣工累计同比；
3. **资金与流动性端**：房地产开发企业本年到位资金累计同比（细分国内贷款/自筹/定金预收/按揭）；
4. **居民杠杆与债务端**：居民部门杠杆率（NIFD/央行金稳局，季度）、
   个人住房贷款余额同比增速及不良率（央行金融统计/NFRA 季度）。

**S3 具体代理组合由 B 包外部调研落地**（每项端点可获取性 + 历史深度 + 更新行为），
禁止在本窗口未验证就硬编码路由。

## 引擎要求

- 复用 V1.5A transforms 白名单（S1/S2 为季度水平值 + 趋势变化，可用 level/mom/
  rolling_percentile/robust_zscore 等现有变换）；**需新增变换必须先扩展白名单并测试**；
- 注册方式：signals.yaml 中 S1/S2/S3 现有占位（layer: structural）补全 inputs/transforms
  声明（structural 层不含打分配置，沿用既有语义）；
- 状态语义沿用 V1.5D（READY/WARMUP/PARTIAL/MISSING_INPUT）与 V1.2 状态机
  （OK/STALE/FAILED/FALLBACK_USED/MANUAL_REQUIRED）；
- 无数据/季度最新值超时 → `NO_SIGNAL` 显式输出，禁止 silent fallback、禁止 synthetic。

## 分阶段

### 第一阶段：BIS provider 落地（S1/S2）
新增 BIS data adapter（data_sources.yaml 路由，季度频率），Bulk CSV 或 SDMX 取数，
确定性 fixture 测试 + network 测试 opt-in。

### 第二阶段：S3 代理池落地
按 B 包结果注册 S3 输入路由（可含 Wind manual 项），明确代理组合与口径。

### 第三阶段：Structural 引擎
逐信号计算 + 输出诊断状态；报告入口 `scripts/structural_report.py`。

## Acceptance Criteria

1. B 包调研归档并经协调员抽验（端点实测、失败逐条记录、S3 代理池落地清单）；
2. S1/S2 走 BIS 真实数据（WS_CREDIT_GAP Type C / WS_DSR），provider 路由在 data_sources.yaml
   且遵守 V1.2 契约；无数据时 NO_SIGNAL，无 synthetic；
3. 新增变换（若有）先扩展白名单并有测试；
4. S3 代理组合落地并注明口径（价格/景气/资金/杠杆四类）；
5. Structural 引擎输出为诊断状态，**不进入 Asset Score**（有测试证明无数据流）；
6. 报告入口 `structural_report.py` 输出 S1/S2/S3 状态与最新值；
7. 完整 pytest PASS（V2.5 基线 + 新增）；网络测试 opt-in；
8. V1–V2.5 frozen components 未被重写。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V2.6 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 structural_report.py 并贴出输出；
- 检查 S1/S2/S3 是否进入任何 Asset Score（grep）；
- 检查无数据时是否 NO_SIGNAL 且无 synthetic；
- 检查是否实现范围外功能；
- 列出修改文件与已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README：S1/S2/S3 状态、BIS provider 路由、
S3 代理池口径、无数据行为、与 Asset Score 隔离证明。

建议 tag：

```text
v0.7-structural-risk
```

（下一阶段：**V3 Local Dashboard（Streamlit）**，见 docs/tasks/70。）
