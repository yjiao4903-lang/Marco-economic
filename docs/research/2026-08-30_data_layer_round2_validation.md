# 数据源深度验证档案 — 2026-08-30 外部窗口第二轮报告

> **来源**：外部只读调研窗口（第二轮，2026-08-30）。原始报告全文存档，未经内容改动。
> 任务包：社融序列验证 / AKShare 上游端点挖掘 / 发布日历与历史深度 / BIS 可用性。
>
> **协调员抽验记录（2026-08-30，本机网络）— 4/4 通过**：
> 1. MOFCOM `POST data.mofcom.gov.cn/.../shrzgmQuery` → HTTP 200，数值与报告一致
>    （202604 tiosfs=6245 等），并独立确认仅 9 字段、**无政府债券分项**；
> 2. Eastmoney `RPT_ECONOMY_PPI`（带 columns 参数）→ HTTP 200，
>    2026-07 BASE_SAME=3.5 与报告一致；
> 3. ChinaMoney `FrrHis` 2016-12-13~16 → FDR007=`"---"`（证实 2017-06-28 前无 FDR007 定盘数据）；
> 4. ChinaMoney `FrrHis` 2017-06-26~30 → FDR007=2.8000（证实起点论断）。
>
> **协调员批注：对 Gate A（V1.2C）覆盖目标的影响**：
> - 直接受益解锁：X1/X2/X3（FRED+ChicagoFed 直链）、I2（东财 PPI 直连）、
>   I1 fallback 口径（东财 CPI；核心 CPI 仍需 NBS 解读页解析）；
> - 需开发工作但可行：G4（NBS 新闻稿解析）、D1（DR007 2017-06 起约 9 年日度，
>   对 rolling 窗口足够；7 天逆回购利率源仍未验证）、I3（GSCPI 单腿，coverage<1）；
> - **仍阻塞（预计 Gate A 覆盖为 10–11/15 而非 12/15）**：
>   G2（PMI 新订单：聚合商均无分项，唯一路线 NBS 新闻稿解析或 Wind manual）；
>   D2/D4（政府债券融资：MOFCOM 源无此分项；东财是否存含政府债券的社融报表未验证）；
>   D3（社融存量：AKShare 无接口，需东财报表验证或 Wind manual）；
> - 数据源政策提醒：东财 datacenter API 是 AKShare 这些接口的同一上游，属聚合商层级
>   （与 AKShare 同级），实现时必须记录 provider=EASTMONEY / original_source=NBS/PBOC；
>   东财 API 强制要求显式 columns 参数（F-03），省略即 9501 错误；
> - 发布日历表可直接落 Gate A §12 的 freshness 配置：OECD 序列需 replace_window（≥12–24 月）、
>   GSCPI 全历史修订（full_refresh）、ANFCI 轻度修订（replace_window 4–8 周）、
>   NBS PMI/CPI/PPI 与 FRED 日频为 append；
> - BIS S1/S2 已验证（WS_CREDIT_GAP / WS_DSR bulk CSV），V2.6 前置调研完成。

---

# 宏观监控系统数据获取层·第二轮只读验证调研报告

> **调研性质**：只读验证与架构选型调研（第二轮）  
> **报告基准时间**：2026-08-30  
> **执行铁律**：所有 VERIFIED 端点均附带真实请求状态码及 ≤15 行原始响应片段；失败尝试逐条归档；不确定项明确标注。

---

## 摘要表

| 任务 | 调研目标 | 推荐来源 | 验证状态 | 一句话备注与核心结论 |
| :--- | :--- | :--- | :--- | :--- |
| **A1** | 社融增量 (`CN_TSF_TOTAL`) & 政府债券 (`CN_GOV_BOND_FINANCING`) | 东方财富宏观库 / 央行通稿解析 | **VERIFIED (MOFCOM) / UNVERIFIED (PBOC直抓)** | AKShare 商务部源实测成功但**缺失政府债券分项**；PBOC 官网存在动态 WAF，无法硬编码抓取。 |
| **A2** | 社融存量 (`CN_PRIVATE_TSF_YOY`) | 央行通稿 / 东方财富数据中心 | **FAILED (AKShare无接口)** | AKShare 源码中**无任何社融存量接口**，必须通过爬虫或第三方金融数据源补充。 |
| **B1** | PMI 及新订单/购进价格 | 东方财富 `RPT_ECONOMY_PMI` / 统计局 | **VERIFIED (综合指数) / FAILED (分项)** | AKShare 上游仅返回制造业/非制造业综合 PMI，**新订单与原材料购进价格分项在当前表缺失**。 |
| **B2** | CPI 同比/环比 & 核心 CPI fallback | 东方财富 `RPT_ECONOMY_CPI` & 金十 CDN | **VERIFIED (CPI) / UNVERIFIED (核心CPI)** | CPI 综合指数实测正常；东方财富上游主表不含核心 CPI，核心 CPI 需单独从统计局通稿抓取。 |
| **B3** | PPI 同比 (`CN_PPI_YOY`) | 东方财富 `RPT_ECONOMY_PPI` | **VERIFIED** | 接口完全可用，字段直连映射清晰，覆盖 1996 年至今历史。 |
| **B4** | 房地产销售面积/销售额 | 统计局月报 / 东方财富指标库 | **FAILED (口径错配)** | AKShare `macro_china_real_estate` 实测为**国房景气指数**而非销售额/面积，需更换报表。 |
| **B5** | DR007 历史回填 (`CN_DR007`) | 中国货币网 `FrrHis` (FDR007) | **VERIFIED (2017起) / FAILED (2014-2017)** | ChinaMoney 定盘 FDR007 **实际起点为 2017-06-28**，2014-12 至 2017-06 数据为空值，需静态回填。 |
| **B6** | 公开市场 7D 逆回购 (`CN_POLICY_RATE_7D`)| 中国货币网公告流 / 金十 / 东方财富 | **FAILED (AKShare已失效)** | AKShare `macro_china_gksccz` 已废弃失效；推荐使用中国货币网公告流或公开市场操作流水。 |
| **C** | 发布日历与历史深度表 | 各官方权威发布渠道 | **VERIFIED** | 完整覆盖 10 类核心宏观资产日历，明确区分 `replace_window` 与 `append`。 |
| **D** | BIS 中国 Credit Gap 与 DSR | BIS 官方 Bulk CSV / REST API | **VERIFIED** | BIS 完整提供中国 Credit-to-GDP Gap（1995Q4起）与 DSR（1999Q1起），实测均为季度更新。 |

---

## 任务 A 详情：社融序列验证

### A1. 社融增量 (`CN_TSF_TOTAL`) 与政府债券分项 (`CN_GOV_BOND_FINANCING`)

#### 1. AKShare `macro_china_shrzgm` 源码与上游定位
- **源码文件**：`akshare/economic/macro_china.py` 中的 `macro_china_shrzgm()`
- **请求上游**：`https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery`
- **请求方式**：`POST`，无请求体，采用 TLS 适配器
- **返回格式**：JSON 数组（`application/json`）
- **字段解析**：
  AKShare 对该 JSON 做了如下列重命名：
  - `date` $\rightarrow$ 月份
  - `tiosfs` $\rightarrow$ 社会融资规模增量
  - `rmblaon` $\rightarrow$ 人民币贷款（注意商务部接口字段拼写为 `rmblaon`）
  - `forcloan` $\rightarrow$ 外币贷款
  - `entrustloan` $\rightarrow$ 委托贷款
  - `trustloan` $\rightarrow$ 信托贷款
  - `ndbab` $\rightarrow$ 未贴现银行承兑汇票
  - `bibae` $\rightarrow$ 企业债券
  - `sfinfe` $\rightarrow$ 非金融企业境内股票融资
- **重大发现**：MOFCOM 接口仅返回 9 个字段，**完全不包含“政府债券”分项**！商务部该接口沿用了 2015 年初期的统计口径，未同步央行后续将“地方政府专项债券”（2018年9月）及“政府债券”（2019年12月）纳入社融增量的改版。

#### 2. 实测上游端点证据
- **请求 URL**：`POST https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery`
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
[
  {
    "date": "202604",
    "ndbab": -5284,
    "entrustloan": -283,
    "forcloan": 184,
    "rmblaon": -4006,
    "bibae": 4520,
    "tiosfs": 6245,
    "sfinfe": 835,
    "trustloan": -129
  },
  {
    "date": "202603",
    "ndbab": 1258,
    "entrustloan": -127,
    "forcloan": -102,
    "rmblaon": 32873,
    "bibae": 4652,
    "tiosfs": 53818,
    "sfinfe": 218,
    "trustloan": 234
  }
]
```
- **验证状态**：`VERIFIED`（端点可用，但数据口径残缺，无法满足政府债券分项需求）。

#### 3. 中国人民银行官网 (`pbc.gov.cn`) 发布页 URL 结构与硬编码抓取可行性评估
- **发布页结构**：央行通过“首页 $\rightarrow$ 沟通交流 $\rightarrow$ 新闻发布”发布每月《社会融资规模增量统计数据报告》。其实际 URL 结构为：
  `http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/{动态7位文章ID}/index.html`（例如 `/5141234/index.html`）。
- **WAF 与反爬阻断**：PBOC 部署了政务级网宿 WAF 防护系统，对未经授权的 Python 请求直接返回 `403 Forbidden` 或 `404 Not Found`，并通过 JS 动态挑战生成 Cookie 凭证（`wzws_cid`）。
- **内容格式**：页面正文为富文本新闻通稿（非结构化表格），且每月通稿的段落格式、标点符号常有微调。
- **可行性评估**：**不可行（FAIL）**。无法通过静态 URL 模板拼接获取，且正文解析维护成本极高。

#### 4. 落地结论与架构建议
1. **来源裁决**：
   - 放弃直接硬编码抓取 PBOC 页面。
   - 放弃使用 AKShare 的 `macro_china_shrzgm`（商务部源缺失政府债券）。
   - **推荐方案**：采用东方财富数据中心底层宏观报表 API（直连 adapter，需传完整 columns 参数）或接入商业/开放财经 API；若必须走央行源，需搭建具备无头浏览器（Headless Browser）的通稿采集与正则抽取 sidecar。
2. **政府债券项归属**：在央行正规社融增量统计体系及主流金融终端中，政府债券（国债+地方政府债）与社融总量在同一张表中同步发布。

---

### A2. 社融存量验证 (`CN_PRIVATE_TSF_YOY`)

#### 1. AKShare 源码排查
- 检查 `akshare/economic/` 目录下全部模块，包含 `macro_china.py`、`macro_bank.py`、`macro_finance_ths.py` 等。
- 搜索社融相关函数，仅发现 `macro_china_shrzgm()`（增量）。
- **结论**：**AKShare 官方代码库中不存在任何社融存量（Stock）接口**。

#### 2. 实测状态
- **状态**：`FAILED / NOT_AVAILABLE`（AKShare 无此能力）。
- **技术要求**：私营部门社融存量同比增速需要：$\text{Private TSF Stock} = \text{Total TSF Stock} - \text{Gov Bond Stock}$。该数据在央行每月《社会融资规模存量统计数据报告》中发布（月末存量余额），需独立建立存量数据抓取通道。

---

## 任务 B 详情：AKShare 上游端点挖掘

### B1. `macro_china_pmi` $\rightarrow$ `CHN_PMI_NEW_ORDERS`, `CHN_PMI_INPUT_PRICE`

- **AKShare 源码实现**：
  ```python
  url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
  params = {
      "columns": "REPORT_DATE,TIME,MAKE_INDEX,MAKE_SAME,NMAKE_INDEX,NMAKE_SAME",
      "reportName": "RPT_ECONOMY_PMI",
      "sortColumns": "REPORT_DATE",
      "sortTypes": "-1",
      "pageSize": "2000",
      "pageNumber": "1",
      "source": "WEB",
      "client": "WEB",
  }
  ```
- **上游 URL**：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`
- **参数详情**：`reportName=RPT_ECONOMY_PMI`, `columns=REPORT_DATE,TIME,MAKE_INDEX,MAKE_SAME,NMAKE_INDEX,NMAKE_SAME`, `pageSize=20`, `pageNumber=1`, `sortColumns=REPORT_DATE`, `sortTypes=-1`, `source=WEB`, `client=WEB`
- **返回格式**：JSON
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
{
  "version": "f664488d431c2d85e1f99ce51e9fef6d",
  "result": {
    "pages": 45,
    "data": [
      {
        "REPORT_DATE": "2026-07-01 00:00:00",
        "TIME": "2026年07月份",
        "MAKE_INDEX": 49.2,
        "MAKE_SAME": -0.20283976,
        "NMAKE_INDEX": 49,
        "NMAKE_SAME": -2.19560878
      }
    ],
    "count": 222
  }
}
```
- **字段映射**：
  - `MAKE_INDEX` $\rightarrow$ 官方制造业 PMI（综合）
  - `NMAKE_INDEX` $\rightarrow$ 官方非制造业 PMI（综合）
  - `CHN_PMI_NEW_ORDERS` / `CHN_PMI_INPUT_PRICE`：**本表无此字段**。
- **历史起点**：2008-01-01
- **更新时滞**：每月最后一日（或次月 1 日）09:30 CST
- **验证状态**：`VERIFIED`（综合 PMI）；分项指标需访问国家统计局细分指标库（`A0B01`）或第三方数据商。

---

### B2. `macro_china_cpi` $\rightarrow$ `CN_CORE_CPI_YOY` Fallback 验证

- **AKShare 源码实现**：
  - 主接口：东方财富 `RPT_ECONOMY_CPI`
  - 备用接口：`macro_china_cpi_yearly` 请求金十 CDN（`https://cdn.jin10.com/dc/reports/dc_chinese_cpi_yoy_all.js`）
- **上游 URL**：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`
- **参数详情**：`reportName=RPT_ECONOMY_CPI`, `columns=REPORT_DATE,TIME,NATIONAL_SAME,NATIONAL_BASE,NATIONAL_SEQUENTIAL,NATIONAL_ACCUMULATE,CITY_SAME,CITY_BASE,CITY_SEQUENTIAL,CITY_ACCUMULATE,RURAL_SAME,RURAL_BASE,RURAL_SEQUENTIAL,RURAL_ACCUMULATE`, `pageSize=20`, `pageNumber=1`, `sortColumns=REPORT_DATE`, `sortTypes=-1`, `source=WEB`, `client=WEB`
- **返回格式**：JSON
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
{
  "version": "ceadff2e28b774f82e485666d8be4056",
  "result": {
    "pages": 45,
    "data": [
      {
        "REPORT_DATE": "2026-07-01 00:00:00",
        "TIME": "2026年07月份",
        "NATIONAL_SAME": 0.5,
        "NATIONAL_BASE": 100.5,
        "NATIONAL_SEQUENTIAL": -0.1,
        "NATIONAL_ACCUMULATE": 100.9,
        "CITY_SAME": 0.5,
        "CITY_BASE": 100.5,
        "CITY_SEQUENTIAL": -0.1,
        "CITY_ACCUMULATE": 100.9
      }
    ],
    "count": 222
  }
}
```
- **字段映射**：
  - `NATIONAL_SAME` $\rightarrow$ 全国 CPI 同比
  - `NATIONAL_SEQUENTIAL` $\rightarrow$ 全国 CPI 环比
  - `CN_CORE_CPI_YOY`（核心 CPI 同比）：**该主表未提供核心 CPI 细分列**（仅包含全国/城市/农村的总体、同比、环比、累计）。
- **历史起点**：1987-01-01（金十 CDN 源为 1986-02-01）
- **更新时滞**：每月 9–11 日 09:30 CST
- **验证状态**：`VERIFIED`

---

### B3. `macro_china_ppi` $\rightarrow$ `CN_PPI_YOY`

- **AKShare 源码实现**：
  ```python
  url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
  params = {
      "columns": "REPORT_DATE,TIME,BASE,BASE_SAME,BASE_ACCUMULATE",
      "reportName": "RPT_ECONOMY_PPI",
      "sortColumns": "REPORT_DATE",
      "sortTypes": "-1",
      "pageSize": "2000",
      "pageNumber": "1",
      "source": "WEB",
      "client": "WEB",
  }
  ```
- **上游 URL**：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`
- **参数详情**：`reportName=RPT_ECONOMY_PPI`, `columns=REPORT_DATE,TIME,BASE,BASE_SAME,BASE_ACCUMULATE`, `pageSize=20`, `pageNumber=1`, `sortColumns=REPORT_DATE`, `sortTypes=-1`, `source=WEB`, `client=WEB`
- **返回格式**：JSON
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
{
  "version": "df8e956e3a3fafa3527f69da60ea6601",
  "result": {
    "pages": 50,
    "data": [
      {
        "REPORT_DATE": "2026-07-01 00:00:00",
        "TIME": "2026年07月份",
        "BASE": 103.5,
        "BASE_SAME": 3.5,
        "BASE_ACCUMULATE": 101.8
      }
    ],
    "count": 249
  }
}
```
- **字段映射**：
  - `BASE_SAME` $\rightarrow$ `CN_PPI_YOY`（工业生产者出厂价格指数同比）
  - `BASE` $\rightarrow$ 当月指数（上年同月=100）
  - `BASE_ACCUMULATE` $\rightarrow$ 累计指数（上年同期=100）
- **历史起点**：1996-08-01
- **更新时滞**：每月 9–11 日 09:30 CST
- **验证状态**：`VERIFIED`

---

### B4. `macro_china_real_estate` $\rightarrow$ `CN_PROPERTY_SALES_*`

- **AKShare 源码实现**：
  ```python
  url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
  params = {
      "sortColumns": "REPORT_DATE",
      "sortTypes": "-1",
      "pageSize": "1000",
      "pageNumber": "1",
      "reportName": "RPT_INDUSTRY_INDEX",
      "columns": "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE,CHANGERATE_3M,CHANGERATE_6M,CHANGERATE_1Y,CHANGERATE_2Y,CHANGERATE_3Y",
      "filter": '(INDICATOR_ID="EMM00121987")',
      "source": "WEB",
      "client": "WEB",
  }
  ```
- **上游 URL**：`GET https://datacenter-web.eastmoney.com/api/data/v1/get`
- **参数详情**：`reportName=RPT_INDUSTRY_INDEX`, `filter=(INDICATOR_ID="EMM00121987")`, `columns=REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE...`
- **返回格式**：JSON
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
{
  "version": "32e892dbb3ce0ada8706cd3575e2ae99",
  "result": {
    "pages": 131,
    "data": [
      {
        "REPORT_DATE": "2025-12-01 00:00:00",
        "INDICATOR_VALUE": 91.45,
        "CHANGE_RATE": -0.47883339,
        "CHANGERATE_3M": -1.41224666,
        "CHANGERATE_6M": -2.24478888,
        "CHANGERATE_1Y": -1.18854673,
        "CHANGERATE_2Y": -1.9723443,
        "CHANGERATE_3Y": -3.03255222
      }
    ],
    "count": 652
  }
}
```
- **关键问题发现**：
  - 该接口获取的 `INDICATOR_ID="EMM00121987"` 是**国房景气指数**（最新值约 91.45），**并不是商品房销售面积或销售额累计值**！
  - 东方财富早期房地产综合表 `RPT_ECONOMY_HOSE_INDEX` 已经在 2010 年底停更（实测仅到 2010-12-01）。
  - 商品房销售面积/销售额需直接从统计局“全国房地产开发投资与销售情况”专题发布页或对应细分行业代码指标抓取。
- **历史起点（景气指数）**：1997-03-01
- **更新时滞**：每月 15–17 日 10:00 CST
- **验证状态**：`VERIFIED`（端点本身连通有效），但对 `CN_PROPERTY_SALES_*` 目标为**口径错配**。

---

### B5. `repo_rate_hist` / `rate_interbank` $\rightarrow$ `CN_DR007` 历史回填

- **AKShare 源码实现**：
  - `repo_rate_hist`：请求中国货币网 `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis`
  - `rate_interbank`：请求东方财富 `RPT_IMP_INTRESTRATEN`（仅涵盖 Shibor/Libor 等同业拆借，无 DR007 回购数据）。
- **上游 URL (ChinaMoney)**：`POST https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis`
- **参数详情**：`lang=CN`, `startDate=YYYY-MM-DD`, `endDate=YYYY-MM-DD`
- **返回格式**：JSON
- **HTTP 状态码**：`200 OK`
- **真实响应片段**：
```json
{
  "head": {
    "version": "2.0",
    "rep_code": "200",
    "rep_message": ""
  },
  "records": [
    {
      "lfiProducDate": "2026-08-28",
      "frValueMap": {
        "date": "2026-08-28",
        "FDR001": "1.3400",
        "FDR007": "1.3800",
        "FDR014": "1.4000",
        "FR001": "1.3700",
        "FR007": "1.4100",
        "FR014": "1.4300"
      }
    }
  ]
}
```
- **关键历史回溯深度实测结论**：
  1. **FR 系列（全市场银行间定盘）**：`FR007` 历史深度极为充足，可平稳回溯至 2006 年。
  2. **FDR 系列（存款类机构回购定盘，即 FDR007）**：
     - 实测 2014-12-15：`FDR007` 返回 `'---'`；
     - 实测 2015-12-15：`FDR007` 返回 `'---'`；
     - 实测 2016-12-15：`FDR007` 返回 `'---'`；
     - **首次出现非空有效数值的日期为：`2017-06-28`（数值：2.7000）**。
  3. **结论**：虽然央行自 2014-12-15 推出 DR007 交易加权利率，但中国货币网该公开定盘接口（`FrrHis`）**仅从 2017-06-28 起提供 FDR007**。2014-12 至 2017-06 期间的 DR007 历史回填无法通过此公开接口获取，必须依赖静态历史数据集录入。
- **最新日期**：交易日当日（T日盘后）。
- **验证状态**：`VERIFIED`（2017-06-28 至今）；2014-2017 年段标记为 `FAILED (缺失)`。

---

### B6. `macro_china_gksccz` $\rightarrow$ `CN_POLICY_RATE_7D` (7D 逆回购政策利率)

- **AKShare 源码与现状**：
  - 历史版本对应中国货币网公开市场操作页面 `http://www.chinamoney.com.cn/chinese/yhgkscczh/`。
  - 在 AKShare 最新版本中，该函数已被移除或不再有效（中国货币网后台端点改组为 `cm-u-dlrp/PrDlyBltn` 公告形式）。
- **上游 URL (中国货币网公告流 / 东方财富/金十替代)**：`GET / POST`
- **替代端点实测（金十央行利率库）**：`https://cdn.jin10.com/dc/reports/dc_chinese_interest_rate_decision_all.js`
- **实测结果**：该特定静态 JS 已被金十下线（返回 HTTP 404）；需使用动态 API。
- **目标字段映射**：
  - 7天逆回购中标利率 $\rightarrow$ `CN_POLICY_RATE_7D`
- **历史起点**：2015 年 10 月起确立 7D 逆回购操作利率为核心政策利率（历史操作记录可回溯至 2004 年）。
- **更新时滞**：交易日 09:20 CST 公开市场业务交易公告发布后即时固化。
- **验证状态**：`FAILED`（原 AKShare 接口废弃），推荐改用 ChinaMoney 每日公告抓取或第三方标准化政策利率流。

---

## 任务 C 表格：发布日历与历史深度表（完整版）

| 序列代码 | 指标名称 | 官方数据源 | 官方发布频率 | 官方发布时滞 / 依据页 | 推荐来源可回溯起点 | 历史是否修订 (Revision) | 推荐加载策略 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GLOBAL_OECD_CLI** | OECD 综合领先指标 (CLI) | OECD Data Explorer (`DF_CLI`) | 月度 (M) | 每月第 2 周（通常 8–11 日）发布上月数据。<br>[OECD CLI 官网说明页](https://www.oecd.org/en/data/indicators/composite-leading-indicator-cli.html) | 1970 年代（中国序列自 1990 年代起） | **是 (严重修订)**<br>每月随 HP 滤波/季节调整参数及成分数据回溯重算历史值。 | `replace_window` (建议至少 24 个月) |
| **GLOBAL_OECD_IPI** | OECD 工业生产指数同比 | OECD SDMX (`DF_IPI`) | 月度 (M) | 滞后 45–60 天发布。<br>[OECD IPI 说明页](https://data-explorer.oecd.org/) | 1960 年代起 | **是**<br>各国统计局定期上报修订及季调修正。 | `replace_window` (12 个月) |
| **GLOBAL_OECD_RETAIL**| OECD 零售销售同比 | OECD SDMX (`DF_RETAIL`) | 月度 (M) | 滞后 40–50 天发布。<br>[OECD Retail 说明页](https://data-explorer.oecd.org/) | 1970 年代起 | **是**<br>季节调整与样本回溯修正。 | `replace_window` (12 个月) |
| **CHN_NBS_PMI** | 官方制造业/非制造业 PMI | 国家统计局 (NBS) | 月度 (M) | **每月最后一日 09:30 CST**（遇特殊节假日顺延至次月1日）。<br>[国家统计局发布日历](https://www.stats.gov.cn/sj/zxfb/) | 2005-01 起 | **否**<br>作为调查扩散指数，发布后通常不再做历史修订。 | `append` (单点追加) |
| **CHN_NBS_CPI** | CPI 同比 / 环比 / 核心 CPI | 国家统计局 (NBS) | 月度 (M) | **每月 9–11 日 09:30 CST**。<br>[国家统计局数据发布日程](https://www.stats.gov.cn/sj/zxfb/) | 1987-01 起 | **否 (极少)**<br>基期轮换（每5年）仅影响基期权重，已公布的历史同比不回溯修改。 | `append` (单点追加) |
| **CHN_NBS_PPI** | PPI 工业生产者出厂价格 | 国家统计局 (NBS) | 月度 (M) | **每月 9–11 日 09:30 CST**（与 CPI 同时发布）。<br>[国家统计局发布日程](https://www.stats.gov.cn/sj/zxfb/) | 1996-08 起 | **否**<br>发布后终值固化，不回溯修改。 | `append` (单点追加) |
| **CHN_NBS_REAL_ESTATE**| 房地产投资与销售情况 | 国家统计局 (NBS) | 月度 (M) | **每月 15–17 日 10:00 CST**（1-2月数据合并至3月发布）。<br>[国家统计局发布日程](https://www.stats.gov.cn/sj/zxfb/) | 1997-01 起 | **是**<br>统计局年末会对当年及历史累计值进行基数校验修正。 | `replace_window` (3–6 个月) |
| **CN_DR007** | 存款类机构回购利率 (DR007) | 中国货币网 (ChinaMoney) | 日度 (D) | **交易日 17:00–17:30 CST** 盘后基准固化。<br>[中国货币网回购定盘页](https://www.chinamoney.com.cn/chinese/bkfrr/) | 官方定盘 FDR007 起点为 **2017-06-28**（加权交易历史可追溯至 2014-12-15） | **否**<br>金融交易定盘数据，发布即终值。 | `append` (单点追加) |
| **US_FRED_DFII10** | 10年期 TIPS 实际利率 | 美联储 / FRED (`DFII10`) | 日度 (D) | 美东时间每个工作日 16:15 ET（美联储 H.15 报告）。<br>[FRED DFII10 页面](https://fred.stlouisfed.org/series/DFII10) | 2003-01-02 起 | **否**<br>市场交易固化数据，无事后 revision。 | `append` (单点追加) |
| **US_FRED_DTWEXBGS**| 美元广义贸易加权指数 | 美联储 / FRED (`DTWEXBGS`) | 日度 (D) | 美东时间每个工作日 16:15 ET（美联储 H.10 报告）。<br>[FRED DTWEXBGS 页面](https://fred.stlouisfed.org/series/DTWEXBGS) | 2006-01-02 起 | **否**<br>日常终值发布，权重调整时不回溯改写历史点。 | `append` (单点追加) |
| **US_FRED_ANFCI** | 芝加哥联储调整后金融状况指数 | 芝加哥联储 / FRED (`ANFCI`) | 周度 (W) | **每周四早间 08:30 ET**。<br>[FRED ANFCI 页面](https://fred.stlouisfed.org/series/ANFCI) | 1971-01-08 起 | **是 (轻微)**<br>随成分金融变量更新及主成分模型估计，历史近期点有小幅微调。 | `replace_window` (4–8 周) |
| **US_NYFED_GSCPI** | 全球供应链压力指数 (GSCPI) | 纽约联储 (NY Fed) | 月度 (M) | **每月第 4 个工作日 10:00 ET**。<br>[NY Fed GSCPI 官方主页](https://www.newyorkfed.org/research/policy/gscpi) | 1997-09-30 起 | **是 (全历史修订)**<br>每次新增月份时，动态因子模型（DFM）重新估计整个历史序列。 | `replace_window` (或全量覆盖 reload) |
| **CN_CHINABOND_10Y** | 中债国债收益率曲线 (10Y) | 中国债券信息网 / 中国货币网 | 日度 (D) | **交易日 17:30–18:00 CST** 估值曲线固化发布。<br>[中国货币网中债收益率曲线](https://www.chinamoney.com.cn/chinese/bkcurvclosedyhis/) | 2002 年起（ChinaMoney 接口可查 2010+） | **否**<br>估值定盘终值，不作历史回溯。 | `append` (单点追加) |

---

## 任务 D 详情：BIS 中国数据可用性（V2.6 储备）

### 1. Credit-to-GDP Gap (S1) 中国数据验证
- **是否提供中国数据**：**是（提供）**
- **数据结构与代码**：
  - 数据集：`WS_CREDIT_GAP(1.0)`
  - 借款国：`CN: China`
  - 借款部门：`P: Private non-financial sector`（私营非金融部门）
  - 数据类型：
    - `A`: Credit-to-GDP ratios（实际比例）
    - `B`: Credit-to-GDP trend（HP 滤波长期趋势）
    - `C`: Credit-to-GDP gaps（信贷/GDP 缺口 = Actual - Trend）
- **官方下载与 API 端点**：
  - Bulk CSV Zip：`https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip`（HTTP 200，大小约 250KB）
  - SDMX REST API：`GET https://stats.bis.org/api/v1/data/BIS,WS_CREDIT_GAP,1.0/Q.CN.P.A.C?format=sdmx-json`
- **频率与起止时间**：
  - 频率：季度（Quarterly，`Q`）
  - 实际比率（Type A）起点：**1985-Q4**
  - 缺口数据（Type C）起点：**1995-Q4**
  - 最新数据：**2025-Q4**（实测值：`-7.6881%`）
- **实测真实响应片段**：
```csv
STRUCTURE,STRUCTURE_ID,ACTION,FREQ:Frequency,BORROWERS_CTY:Borrowers' country,TC_BORROWERS:Borrowing sector,TC_LENDERS:Lending sector,CG_DTYPE:Credit gap data type,TIME_PERIOD:Time period or range,OBS_VALUE:Observation Value,COLLECTION:Collection Indicator,DECIMALS:Decimals,UNIT_MEASURE:Unit of measure,UNIT_MULT:Unit Multiplier,TIME_FORMAT:Time Format,TITLE_TS:Title (tseries level),OBS_STATUS:Observation Status,OBS_CONF:Observation confidentiality,OBS_PRE_BREAK:Pre-Break Observation
dataflow,BIS:WS_CREDIT_GAP(1.0): Credit-to-GDP gaps,I,Q: Quarterly,CN: China,P: Private non-financial sector,A: All sectors,C: Credit-to-GDP gaps (actual-trend),2025-Q4,-7.6881,E: End of period,1: One,770: Percentage of GDP,0: Units,,,A: Normal value,F: Free,
```
- **验证状态**：`VERIFIED`

---

### 2. Debt Service Ratio (S2) 中国数据验证
- **是否提供中国数据**：**是（提供）**
- **数据结构与代码**：
  - 数据集：`WS_DSR(1.0)`
  - 借款国：`CN: China`
  - 借款部门：`P: Private non-financial sector`（私营非金融部门）
- **官方下载与 API 端点**：
  - Bulk CSV Zip：`https://data.bis.org/static/bulk/WS_DSR_csv_flat.zip`（HTTP 200，大小约 40KB）
- **频率与起止时间**：
  - 频率：季度（Quarterly，`Q`）
  - 历史起点：**1999-Q1**（首期数值为 `10.1%`）
  - 最新数据：**2025-Q4**（实测值为 `18.8%`）
- **实测真实响应片段**：
```csv
STRUCTURE,STRUCTURE_ID,ACTION,FREQ:Frequency,BORROWERS_CTY:Borrowers' country,DSR_BORROWERS:Borrowers,TIME_PERIOD:Time period or range,OBS_VALUE:Observation Value,COLLECTION:Collection Indicator,UNIT_MEASURE:Unit of measure,UNIT_MULT:Unit Multiplier,DECIMALS:Decimals,TITLE_TS:Title (tseries level),OBS_CONF:Observation confidentiality,OBS_PRE_BREAK:Pre-Break Observation,OBS_STATUS:Observation Status
dataflow,BIS:WS_DSR(1.0): Debt service ratios,I,Q: Quarterly,CN: China,P: Private non-financial sector,1999-Q1,10.1,,367: Per cent,0: Units,1: One,China - Private non-financial sector,F: Free,,A: Normal value
dataflow,BIS:WS_DSR(1.0): Debt service ratios,I,Q: Quarterly,CN: China,P: Private non-financial sector,2025-Q4,18.8,,367: Per cent,0: Units,1: One,China - Private non-financial sector,F: Free,,A: Normal value
```
- **验证状态**：`VERIFIED`

---

### 3. 中国房地产脆弱性 (S3) 官方替代指标初步清单

针对 BIS 未直接编制细分中国商业/住宅房地产脆弱性指数的情况，可构建基于以下官方权威指标的监控代理池：

1. **价格端脆弱性（统计局）**：
   - `70 个大中城市新建商品住宅与二手住宅销售价格指数`（月度环比、同比、定基指数；覆盖一线/二线/三线城市分化）。
2. **景气与投资端脆弱性（统计局）**：
   - `全国房地产开发景气指数（国房景气指数）`（月度，阈值 100 为景气分界线，当前处于 91–92 历史低位区间）。
   - `房地产开发投资完成额累计同比` 与 `房屋新开工/施工/竣工面积累计同比`。
3. **资金与流动性脆弱性（统计局 / 央行）**：
   - `房地产开发企业本年到位资金累计同比`（细分国内贷款、自筹资金、定金及预收款、个人按揭贷款）。
4. **居民杠杆与债务端脆弱性（国家金融与发展实验室 NIFD / 央行金稳局）**：
   - `居民部门杠杆率 (Household Debt-to-GDP)`（季度更新，宏观杠杆率核心指标）。
   - `个人住房贷款余额同比增速及不良率`（央行金融统计报告 / 金融监管总局 NFRA 季度数据）。

---

## 全部失败尝试记录

| 序号 | 请求目标 / URL | 请求方法 | 错误类型 / 响应结果 | 根因深度剖析 |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | `http://www.pbc.gov.cn/diaochatongjisi/116835/116843/index.html` | GET | `HTTP Error 404 / 403` | 央行调查统计司栏目不存在静态时间路径，且全站启用网宿 WAF 拦截非浏览器脚本。 |
| **F-02** | `https://data.stats.gov.cn/easyquery.htm` (NBS 直接查询) | GET / POST | `HTTP Error 403: Forbidden` | 国家统计局官网启用了反自动化抓取机制，未通过浏览器会话握手初始化的请求均被直接拦截。 |
| **F-03** | `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_PMI` | GET | `Code 9501: 字段不能为空` | 东方财富宏观 API 强制要求必须显式指定 `columns` 参数，省略该参数时服务端直接抛出参数校验错误。 |
| **F-04** | `https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_HOSE_INDEX` | GET | `Count: 33 (Data stopped at 2010-12)` | 该历史报表在 2010 年底已被东方财富废弃，无法提供现代房地产开发与销售高频数据。 |
| **F-05** | `https://www.newyorkfed.org/medialibrary/media/research/policy/gscpi/gscpi_data.csv` | GET | `Status 200 (返回 HTML 包装页而非 CSV)` | 纽约联储网站将旧版媒体库直接 CSV 链接重定向至交互式 Web 应用页，直接按 CSV 解析会报错。 |
| **F-06** | `https://www.bis.org/statistics/full_credit_gap_csv.zip` / `full_dsr_csv.zip` | GET | `HTTP Error 404: Not Found` | BIS 在 2023 年迁移了数据中心架构，旧版 URL 全部失效，新版迁移至 `data.bis.org/static/bulk/WS_*.zip`。 |
| **F-07** | `https://cdn.jin10.com/dc/reports/dc_chinese_interest_rate_decision_all.js` | GET | `HTTP Error 404: Not Found` | 金十数据已废弃此类针对中国利率的静态 JS 镜像，转为动态鉴权接口。 |
| **F-08** | `AKShare repo_rate_hist (2014-12 至 2017-06 FDR007)` | POST | `frValueMap.FDR007 == '---'` | 中国货币网公开定盘接口 `FrrHis` 在 2017-06-28 之前未收录 FDR007 定盘数据，返回占位横杠。 |

---

## 你的不确定性清单

1. **国家统计局高频分项 API（新订单、购进价格、房地产投资销售）的长期反爬策略稳定性**：
   - 虽然东方财富等中介 API 稳定暴露了综合 PMI/CPI/PPI，但关于更细颗粒度的分项（如制造业 PMI 中的新订单、主要原材料购进价格指数），由于统计局反爬措施较严，第三方接口库往往未能即时建立对应的数据表，这部分可能需要通过定时爬虫结合防反爬头解析统计局月报正文。
2. **2014-12 至 2017-06 期间 DR007 加权平均利率历史序列的官方免费 API 缺失**：
   - 中国货币网公开定盘接口（`FrrHis`）仅从 2017-06-28 开始有 FDR007 数据。对于 2014-12-15 至 2017-06-27 这一区间的 DR007 每日加权利率，目前不存在免密公开的官方 REST API，是否直接采用静态 CSV 文件挂载至系统作为 Warmup 基础，需工程架构层面确认。
3. **社融存量与政府债券存量的自动化管道方案**：
   - 鉴于 AKShare 商务部源完全缺失政府债券项，且无存量接口，系统若不购买商业金融终端 API（Wind/Choice），则需要自建针对央行新闻发布通稿的自动化正文解析器。此类文本解析器可能在央行变更通稿行文句式时发生偶发性提取失败，需配置人工兜底告警。
