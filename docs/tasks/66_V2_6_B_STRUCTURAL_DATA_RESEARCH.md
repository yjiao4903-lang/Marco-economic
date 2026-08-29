# B 包调研 — V2.6 Structural Risk 数据深挖（只读调研任务，交外部窗口）

> 状态：**已打包（协调员，2026-08-30）**。V2 开发期间派发（负责人方案：V2.6 前置）。
> 交付物为 Markdown 调研报告，归档 `docs/research/` 后经协调员抽验才可用于 65 号任务书。

## 性质

只读调研窗口任务：不修改仓库、不写代码，交付物为 Markdown 研究报告。
沿用「数据源调研」外包模式的铁律（COORDINATOR_HANDOFF §7.2）：

> 端点必须实测才标 VERIFIED（附响应片段 ≤15 行 + 状态码）；失败逐条记录；不确定写
> "不确定"；AKShare 结论须源码溯源 + 上游实测双证据；只读不改仓库。

## 目标（V2.6 Structural Risk 的输入数据深挖）

### A. BIS WS_* 档案稳定性与更新行为（S1/S2 直接输入）

第二轮调研已实测并归档（docs/research/2026-08-30_data_layer_round2_validation.md 任务 D）：

- S1：`WS_CREDIT_GAP(1.0)`，CN/P，Type C（gap），1995-Q4 起，2025-Q4 = −7.6881%；
  端点 `https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip`（~250KB，HTTP 200）
  及 SDMX REST `https://stats.bis.org/api/v1/data/BIS,WS_CREDIT_GAP,1.0/Q.CN.P.A.C?format=sdmx-json`；
- S2：`WS_DSR(1.0)`，CN/P，1999-Q1 起，2025-Q4 = 18.8%；
  端点 `https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip`（~40KB，HTTP 200）。

**本包要补的是稳定性与更新行为**（第二轮只验证了"可获取"，未深挖"长期维护性"）：

1. 更新节奏：BIS 该系列实际的季度发布日历（官方发布日/滞后）、
   历史序列是否修订（retrospective revision）及修订幅度观察；
2. Bulk CSV 与 SDMX REST 两条路线的稳定性（哪个更适合长期自动抓取，
   响应格式变更风险、限流行为）；建议 primary/fallback 路由；
3. 中国数据是否持续覆盖（近几个季度是否及时更新、有无缺口/断点）；
4. 历史断点/口径变更记录（BIS 是否注明 breakpoint，如疫情口径调整）。

### B. S3 房地产脆弱性代理池可获取性

BIS 未编制细分中国房地产脆弱性指数，需代理池（第二轮档案已列初选清单，本包逐项落地）：

1. **价格端**：70 城新建/二手住宅销售价格指数（月度环比/同比/定基）——
   公开源（NBS/东财/AKShare）端点可获取性、历史深度、更新行为；
2. **景气与投资端**：国房景气指数（月度）、地产开发投资/新开工/施工/竣工累计同比——
   端点、历史、更新；
3. **资金与流动性端**：房地产开发企业本年到位资金累计同比（细分）——端点、历史；
4. **居民杠杆与债务端**：居民部门杠杆率（NIFD 宏观杠杆率，季度）、
   个人住房贷款余额同比增速/不良率（央行/NFRA）——端点、更新频率、可得性。

每项输出：端点 + VERIFIED/失败记录 + 历史起点 + 最新日期 + 更新滞后 + 建议路由
（自动源/Wind manual/不可得则如实标注）。

> 已知线索：南华旧接口已死（第三轮 F13），工业品指数类转 ccidx.com；NBS 反爬较严
> （第二轮 F-02），需评估经东财/AKShare 中介层。

## 交付标准

每个数据点至少包含：Endpoint / 验证状态（VERIFIED/FAILED/不确定）/ 历史起点 /
最新值 / 更新行为 / 建议路由。失败逐条记录进 Failed Attempts Log。

## 用途

作为 65 号任务书（V2.6 Structural Risk）第一阶段 BIS provider 落地与 S3 代理池
选型的依据。协调员抽验（2–4 个关键端点数值）后归档 `docs/research/`。
