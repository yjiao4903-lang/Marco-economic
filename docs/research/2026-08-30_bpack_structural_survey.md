# B 包调研归档 — V2.6 Structural Risk 数据深挖（S1/S2 稳定性 + S3 代理池）

> 状态：**已归档（开发 Agent，2026-08-30）**，待协调员抽验（§7.2 铁律）。
> 依据：66 号任务书交付标准；实测脚本 `_scratch_b_research/`（bis_check / bis_parse /
> bis_break / em_test1-3 / ak_test / ak_cnbs / nbs_nifd_test）。
> 用途：87 号任务书（S3 代理池落地）的输入依据。
> 数据实测日期：2026-08-30（网络实时）；canonical 基线 as-of 同步。

---

## 0. 结论速览

- **S1/S2 BIS WS_\* 长期稳定性良好**：bulk CSV zip 与 SDMX REST 双路线均可获取、
  HTTP 200、文件体积小（credit gap ~280KB / DSR ~40KB）；CN 序列**无 period 断点、
  无 OBS_PRE_BREAK / OBS_STATUS 非 A 标记**；缺口序列仅随 HP 趋势重估而做整体修订
  （gap/trend 两个 dtype 修订，actual dtype 稳定）。建议 **primary=bulk CSV zip，
  fallback=SDMX REST**（与现有 `data_sources.yaml` 路由一致）。
- **S3 代理池四类落地清单**：景气端（国房景气，自动源，VERIFIED）、杠杆端（居民
  部门杠杆率，自动源，VERIFIED 但滞后大）、价格端（70 城房价，东财可达但 per-city
  面板 + 定基口径残缺，本轮标 Wind manual）、资金端（到位资金，东财报表配置不存在，
  NBS 新闻稿可解析但未落地，本轮标不可得/Wind manual 候选）。

---

## 1. BIS WS_\* 稳定性与更新行为（66 §A — S1/S2 直接输入）

### 1.1 端点与获取性（均 VERIFIED，2026-08-30）

| 端点 | 文件/类型 | HTTP | 体积 | ETag/Last-Modified | 说明 |
|---|---|---|---|---|---|
| `https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip` | CSV zip | 200 | ~280KB | 由 headers 携带 | 无 Key，直接下载 |
| `https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip` | CSV zip | 200 | ~40KB | 由 headers 携带 | 同上 |
| `https://stats.bis.org/api/v1/data/BIS,WS_CREDIT_GAP,1.0/Q.CN.P.A.C?format=sdmx-json` | SDMX-JSON | 200 | — | — | REST，可过滤 CN |
| `https://stats.bis.org/api/v1/data/BIS,WS_DSR,1.0/Q.CN.P?format=sdmx-json` | SDMX-JSON | 200 | — | — | REST |

### 1.2 中国序列连续性与修订行为（bis_parse / bis_break 实测）

**WS_CREDIT_GAP（CN/P）**
- 共 403 行，distinct period 161 个：**1985-Q4 .. 2025-Q4**，period 序列 gap = **0**（完全连续）。
- 三个 dtype 并存：A=actual credit-to-GDP、B=HP trend、C=gap（actual−trend）。
- 近期 dtype C（本窗口实际使用）：
  - 2024-Q4 = −7.577，2025-Q1 = −4.4219，2025-Q2 = −5.3031，2025-Q3 = −6.39，2025-Q4 = **−7.6881**。
- **修订行为**：见 2025-Q1 = −4.4219（明显高于相邻期）—— gap/trend 序列随季度整体
  修订（BIS 每季度用新样本重估 HP 趋势），**actual dtype 不回改**。因此 S1 采用
  `full_refresh`（与 GSCPI 先例一致）是正确的。

**WS_DSR（CN/P）**
- 共 108 行（与 canonical 108 一致），**1999-Q1 .. 2025-Q4**，period 序列 gap = **0**。
- 无 OB_STATUS 非 A、无 OBS_PRE_BREAK 标记。

**断点/口径记录（bis_break）**
- 两序列 `OBS_PRE_BREAK 非空 = 0`、`OBS_STATUS != 'A' = 0`：BIS 对 CN 序列**未标注任何
  断点/口径变更标记**（含疫情）。

### 1.3 发布日历与更新滞后

- 实测最新发布期 = **2025-Q4**（2026-08-30 可见），相对季末滞后约 **8 个月**。
- canonical 现配置 `max_staleness_days = 260`、`expected_release_lag_days = 240`，
  与观测滞后一致，**无需调整**（否则即"用观察结果实时调参"，观察期禁止）。

### 1.4 路由建议

- **primary = bulk CSV zip**（确定性、keyless、体积小、Content-Type/ETag 稳定）；
- **fallback / 复核 = SDMX REST**（可按 BORROWERS_CTY 过滤，便于抽验具体 dtype）。
- 与现有 `data_sources.yaml`（BisAdapter `CREDIT_GAP_C` / `DSR_P`，全量 zip）一致，无需改动。

---

## 2. S3 代理池四类落地清单（66 §B）

### 2.1 价格端 — 70 城新建/二手住宅价格指数

| 项 | 内容 |
|---|---|
| Endpoint | 东财 `datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_HOUSE_PRICE`（filter CITY）；AKShare `macro_china_new_house_price`（东财上游，city_first/city_second 两两） |
| 验证状态 | **VERIFIED**（em_test1/em_test2；2026-08-30 HTTP 200 code=0，北京 count=187） |
| 历史起点 | SAME/SEQUENTIAL 口径约 2011 年起（187 期 @ 北京月度）；**BASE（定基）仅 2022-12 起、且为部分填充（北京 84/187）；2026-07 后 BASE=None（未回填）** |
| 最新日期 | 2026-07-01（北京 FIRST_COMHOUSE_SAME=97.7、SEQUENTIAL=99.7；SECOND_HOUSE_SAME=95.5） |
| 更新滞后 | 月度，约次月中发布 |
| 建议路由 | **本轮标 Wind manual**。理由：① per-city 面板（70 城）需先做全国聚合（等权重/销售加权），属"组合口径"决策，不在本窗口自动落地；② BASE 定基口径残缺，若用于定基水平将引入口径偏差；③ 东财仅 SAME/SEQUENTIAL 可用于环比/同比类代理。`RPT_ECONOMY_HOUSE_PRICE` 端点本身稳定，保留为后续自动源候选。 |

### 2.2 景气/投资端 — 国房景气指数 + 开发投资/开竣工

| 项 | 内容 |
|---|---|
| Endpoint | AKShare `macro_china_real_estate()`（国房景气指数）；东财 `RPT_INDUSTRY_INDEX`（INDICATOR_ID=EMM00121987，2026-08-30 HTTP 200 count=652）；NBS 新闻稿（开发投资/新开工/施工/竣工累计同比） |
| 验证状态 | **VERIFIED**（ak_test / em_test1 双重证据） |
| 历史起点 | 国房景气 **1998-01 起**，共 **326 行**（1998-01 .. 2025-12） |
| 最新日期/值 | 2025-12 = **91.45**（东财与 AKShare 双源一致）；`RPT_INDUSTRY_INDEX` 最新 2025-12-01=91.45 |
| 更新滞后 | 月度，约次月中发布 |
| 建议路由 | **自动源（AKShare）**，本轮落地。开发投资/新开工/施工/竣工累计同比走 NBS 新闻稿解析（`nbs_nifd_test` 显示到位资金/新开工等关键字均在新闻稿中出现），但解析器未在 B 包内实现，标候选。 |

### 2.3 资金端 — 房地产开发企业本年到位资金累计同比（细分）

| 项 | 内容 |
|---|---|
| Endpoint | 候选：NBS 房地产月度新闻稿（"到位资金/国内贷款/自筹资金/定金及预收款/个人按揭贷款"关键字均在，`nbs_nifd_test` 实测）；东财报表 **不存在** |
| 验证状态 | **NBS = VERIFIED（可抓取、含关键字）；东财报表 = FAILED** |
| 历史起点 | NBS 累计同比口径，依赖新闻稿归档深度；未实测完整历史 |
| 最新日期 | 未在 B 包内解析出精确最新值 |
| 更新滞后 | NBS 房地产新闻稿约次月 15–17 日 |
| 建议路由 | **不可得（本轮）/ Wind manual 候选**。东财 `RPT_ECONOMY_LOAN` 等报表配置不存在（见 Failed Attempts），自动落地需新建 NBS 新闻稿解析器（超出本窗口）或 Wind manual 导入。 |

### 2.4 杠杆端 — 居民部门杠杆率 + 个人住房贷款

| 项 | 内容 |
|---|---|
| Endpoint | AKShare `macro_cnbs()`（NIFD 宏观杠杆率，居民部门）；NIFD 官网季度报告 |
| 验证状态 | **VERIFIED**（ak_cnbs 实测；2026-08-30 返回 80 行 9 列） |
| 历史起点 | 约 2015 年起（80 期季度） |
| 最新日期/值 | **2024-12 = 61.4%**（居民部门）；含非金融企业 168.4、政府 60.8、实体经济 290.6 |
| 更新滞后 | **显著**（2024-12 距今约 20 个月）。NIFD 季度发布本身有滞后，且 AKShare 聚合端点未回填至 2026；不能据此误判"读数新鲜"。 |
| 建议路由 | **自动源（AKShare）本轮落地**，但在趋时读数上如实标注 PARTIAL/滞后；更高频或权威个人住房贷款余额/不良率走 Wind manual。 |

---

## 3. Failed Attempts Log（逐条）

| 端点 / 报表 | 实测结果 | 判定 |
|---|---|---|
| 东财 `RPT_ECONOMY_HOUSE` | HTTP 200 code=9501 `报表配置不存在,RPT_ECONOMY_HOUSE` | FAILED（配置不存在） |
| 东财 `RPT_ECONOMY_REAL_ESTATE` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_INVEST` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_HOSE_INDEX` | code=9501 `INDICATOR_VALUE 返回字段不存在`（停更/结构变更） | FAILED（em_test1/em_test3） |
| 东财 `RPT_ECONOMY_LOAN` | code=9501 `报表配置不存在` | FAILED（em_test2） |
| 东财 `RPT_ECONOMY_HOUSE_PRICE_INDEX` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_ESTATE` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_FDC` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_CITY_HOUSE` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_INDEX` | code=9501 `报表配置不存在` | FAILED（em_test3） |
| 东财 `RPT_ECONOMY_BOOM` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_INVEST_VALUE` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_FDC_INVEST` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_HOUSE_FUND` | code=9501 `报表配置不存在` | FAILED |
| 东财 `RPT_ECONOMY_MACRO` | code=9501 `报表配置不存在` | FAILED |

**失败共性**：东财报表层仅 `RPT_ECONOMY_HOUSE_PRICE`（70 城房价）与 `RPT_INDUSTRY_INDEX`（国房景气）
稳定存在；资金端/投资端细分报表配置均不存在 → 资金端无法经东财自动获得。

---

## 4. S3 代理池选型与落地口径（供 87 号任务书 Task 2 使用）

| 类别 | 子项（series_id 候选） | 路由 | 频率 | 本轮落地 | 口径/限制 |
|---|---|---|---|---|---|
| 景气端 | `CN_REAL_ESTATE_CLIMATE`（国房景气指数） | AKShare 自动 | 月度 | **是** | 326 行 1998–2025，最新 91.45 |
| 杠杆端 | `CN_HOUSEHOLD_LEVERAGE`（居民部门宏观杠杆率） | AKShare 自动 | 季度 | **是** | 80 行，最新 2024-12=61.4；滞后大，如实标注 |
| 价格端 | `CN_NEW_HOUSE_PRICE_YOY`（70 城新建住宅价格同比） | Wind manual | 月度 | 否（登记） | 东财可达但 per-city+定基残缺；BASE 仅 2022-12 起 84/187 填充 |
| 资金端 | `CN_PROPERTY_FUNDING_YOY`（到位资金累计同比） | 不可得/Wind manual 候选 | 月度 | 否（登记） | 东财报表配置不存在 |

- **组合口径（先验声明，禁止拟合）**：S3 为四分位百分位合成——各代理先对自己历史做
  rolling percentile（统一到 0..1），等权重平均得 composite percentile（0..1），
  按 composite 的 quartile 阈值给 ELEVATED/MODERATE/BENIGN 诊断；不度量、不调参数。
- **可用子集落地**：本轮 2/4 代理（景气 + 杠杆）有真实数据 → S3 **PARTIAL**；
  价格/资金登记为 inputs 但无数据，如实计为缺失，不硬塞弱代理。