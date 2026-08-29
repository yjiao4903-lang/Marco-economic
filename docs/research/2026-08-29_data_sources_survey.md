# 数据源调研档案 — 2026-08-29 外部窗口报告

> **来源**：外部只读调研窗口（Gemini/Antigravity，2026-08-29），任务包为「宏观数据源调研」。
> 本档案为原始报告全文存档，未经内容改动。
>
> **协调员抽验记录（2026-08-29，本机网络）**：
> - Chicago Fed `https://api.data.chicagofed.org/NFCI/nfci-data-series-csv.csv` → HTTP 200，
>   表头/首行与报告一致（周五周频，起点 1971-01-08，最新 2026-08-21）。**通过**。
> - ChinaBond `POST yield.chinabond.com.cn/cbweb-mn/pgxh/yzQuery?gjqx=10` → HTTP 200，
>   返回 10 年期日度收益率 JSON（[毫秒时间戳, %]），数值与报告一致。**通过**。
> - ChinaMoney `https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`
>   → HTTP 200，DR007 2026-08-28 = 1.3859，与报告一致。**通过**。
>
> **对 provider 扩展的关键影响**（协调员批注，转入后续任务书）：
> 1. FRED 三条序列（DFII10/DTWEXBGS/ANFCI）可走 `fredgraph.csv` 直链 CSV——
>    需确认现有 fred.py 是否已用此路径（V1.2 超时可能是网络环境问题而非端点问题）；
> 2. ChinaBond 旧 searchYc 已死，替代端点为 `pgxh/yzQuery`（历史区间）+ `pgxh/xyQuery`（单日截面）；
> 3. Chicago Fed provider 的 `options.url` 待填值即 NFCI CSV 直链（一份文件同时含 NFCI 与 ANFCI）；
> 4. ChinaMoney `prr-chrt.csv` 仅滚动保留约 66 个交易日——DR007 历史回填需
>    AKShare（`repo_rate_hist`）或 Wind manual，增量模式可行但 backfill 不行；
> 5. GSCPI 为 PCA 模型输出，全历史可能逐月 revision——更新机制须支持全量覆盖；
> 6. 商品房销售面积为「年初至今累计值」——D4/G4 消费前需差分为单月值（transform 层新增或 signal 层处理，须显式声明）；
> 7. PBOC 官网 URL 动态易变（报告 14 条失败记录中 3 条源于此）——社融类序列
>    优先走 AKShare（P3）或 ChinaMoney 公告流，不做 PBOC 硬编码 URL 抓取；
> 8. NBS 数据门户 data.stats.gov.cn WAF 403——NBS 序列走新闻发布页解析（P2），
>    与 V1.2 已确立的「官方网页/文件」路线一致。

---

# 宏观监控系统公开数据源调研与端点验证报告

---

## 摘要

| 序列代码 / 调研项 | 推荐来源 | 优先级 | 验证状态 | 一句话备注 |
| :--- | :--- | :---: | :---: | :--- |
| **A1: FRED 直接 CSV 下载** | 圣路易斯联储 FRED (`stlouisfed.org`) | P1 | **VERIFIED** | `DFII10`、`DTWEXBGS`、`ANFCI` 均支持标准 CSV 直接拉取 |
| **A2: ChinaBond 10Y 国债收益率** | 中债收益率曲线 (`yield.chinabond.com.cn`) | P1 | **VERIFIED** | 发现当前活跃接口 `pgxh/yzQuery`，直接返回 10 年期日度收益率 JSON |
| **A3: Chicago Fed NFCI / ANFCI** | 芝加哥联储 (`api.data.chicagofed.org`) | P1 | **VERIFIED** | 探测到直链 CSV (`nfci-data-series-csv.csv`) 及 XLSX 历史文件 |
| **CHN_PMI_NEW_ORDERS** | 国家统计局新闻发布页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 官方网页直采月度值；统计局数据门户因 WAF 反爬返回 403 |
| **CHN_PMI_INPUT_PRICE** | 国家统计局新闻发布页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 官方每月最后一日发布分项购进价格指数；AKShare 为备选 |
| **CN_CORE_CPI_YOY** | 国家统计局月度解读页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 官方每月 9~11 日随 CPI 解读发布核心 CPI 同比数值 |
| **CN_PPI_YOY** | 国家统计局新闻发布页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 官方每月 9~11 日发布当月 PPI 同比与环比；OECD/FRED 为补充 |
| **CN_DR007** | 中国货币网 (`chinamoney.com.cn`) | P1 | **VERIFIED** | 官方静态文件 `currency/prr-chrt.csv` 返回日度加权 DR007 |
| **CN_POLICY_RATE_7D** | 中国货币网央行业务公告 / PBOC | P1 / P2 | **VERIFIED (P1)** | 中国货币网每日同步 7 天逆回购操作量与中标利率公告 |
| **CN_TSF_TOTAL** | 人民银行金融统计数据报告 / AKShare | P2 / P3 | **UNVERIFIED (P2)** | 央行每月月中发布增量统计表；AKShare 对应接口可提取 |
| **CN_GOV_BOND_FINANCING** | 人民银行社会融资规模统计表 / AKShare | P2 / P3 | **UNVERIFIED (P2)** | 包含在社融分项中（国债+地方债），按月发布增量 |
| **CN_PRIVATE_TSF_YOY** | 派生计算（社融总存量 - 政府债券存量） | P1/P2 (派生) | **VERIFIED (逻辑)** | 确认业界标准定义为社融剔除政府债券后计算同比增速 |
| **CN_PROPERTY_SALES_AREA** | 国家统计局房地产发布页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 每月 15~17 日发布当年前 N 个月累计销售面积 |
| **CN_PROPERTY_SALES_VALUE** | 国家统计局房地产发布页 / AKShare | P2 / P3 | **VERIFIED (P2)** | 每月 15~17 日发布当年前 N 个月累计销售金额 |
| **US_GSCPI** | 纽约联储 (`newyorkfed.org`) | P1 | **VERIFIED** | 官方直链 CSV (`gscpi_interactive_data.csv`) 全历史修订矩阵可读 |

---

## 任务 A 详情：三个失效/受阻来源的替代端点验证

### A1. FRED 直接 CSV 下载验证

#### 1. 序列 `DFII10`（10年期通胀指数国债/TIPS收益率）
* **请求 URL**：`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10`
* **HTTP 状态码**：`200 OK`
* **验证状态**：**VERIFIED**
* **真实响应片段（前 10 行）**：
```csv
observation_date,DFII10
2003-01-02,2.43
2003-01-03,2.43
2003-01-06,2.46
2003-01-07,2.42
2003-01-08,2.29
2003-01-09,2.41
2003-01-10,2.41
2003-01-13,2.38
2003-01-14,2.34
```
* **元数据**：
  * **数据频率**：日度（工作日，节假日空值，如 `2003-01-20,`）。
  * **日期格式**：`YYYY-MM-DD`。
  * **更新时滞**：T+1 工作日。
  * **历史起点**：`2003-01-02`。

#### 2. 序列 `DTWEXBGS`（广义名义贸易加权美元指数）
* **请求 URL**：`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS`
* **HTTP 状态码**：`200 OK`
* **验证状态**：**VERIFIED**
* **真实响应片段（前 10 行）**：
```csv
observation_date,DTWEXBGS
2006-01-02,101.4155
2006-01-03,100.7558
2006-01-04,100.2288
2006-01-05,100.2992
2006-01-06,100.0241
2006-01-09,100.1794
2006-01-10,100.1436
2006-01-11,99.8710
2006-01-12,100.0643
```
* **元数据**：
  * **数据频率**：日度（工作日）。
  * **日期格式**：`YYYY-MM-DD`。
  * **更新时滞**：每周一更新上周日度数据（约滞后 3~5 工作日）。
  * **历史起点**：`2006-01-02`。

#### 3. 序列 `ANFCI`（芝加哥联储调整后国家金融状况指数）
* **请求 URL**：`https://fred.stlouisfed.org/graph/fredgraph.csv?id=ANFCI`
* **HTTP 状态码**：`200 OK`
* **验证状态**：**VERIFIED**
* **真实响应片段（前 10 行）**：
```csv
observation_date,ANFCI
1971-01-08,0.584
1971-01-15,0.638
1971-01-22,0.710
1971-01-29,0.793
1971-02-05,0.879
1971-02-12,0.956
1971-02-19,1.015
1971-02-26,1.053
1971-03-05,1.069
```
* **元数据**：
  * **数据频率**：周度（每周五观测日期）。
  * **日期格式**：`YYYY-MM-DD`。
  * **更新时滞**：每周三美东时间 8:30 发布上周五数据（滞后 5 天）。
  * **历史起点**：`1971-01-08`。

---

### A2. ChinaBond 中债 10 年期国债收益率曲线入口验证

#### 1. 当前可用入口
* **页面入口**：`https://yield.chinabond.com.cn/cbweb-mn/pgxh/pgxhIndex`（财政部-中国国债收益率曲线专页）
* **历史期限查询接口**：`https://yield.chinabond.com.cn/cbweb-mn/pgxh/yzQuery`
* **单日全期限查询接口**：`https://yield.chinabond.com.cn/cbweb-mn/pgxh/xyQuery`

#### 2. 接口参数与实测响应
* **请求方法**：`POST`
* **请求 URL**：`https://yield.chinabond.com.cn/cbweb-mn/pgxh/yzQuery?gjqx=10&&startDate=2026-08-01&&endDate=2026-08-28`
* **HTTP 状态码**：`200 OK`
* **验证状态**：**VERIFIED**
* **真实响应片段**：
```json
[
  {
    "seriesData": [
      [1785686400000, 1.7169],
      [1785772800000, 1.7126],
      [1785859200000, 1.7137],
      [1785945600000, 1.7143],
      [1786032000000, 1.7114],
      [1786291200000, 1.7074],
      [1786377600000, 1.7161],
      [1787673600000, 1.6887],
      [1787760000000, 1.6988],
      [1787846400000, 1.6949]
    ],
    "isPoint": false,
    "ycCurveId": null,
    "dcq": 10.0,
    "ycDefName": "10年"
  }
]
```
* **单日全期限截面接口片段 (`xyQuery?workTime=2026-08-28`)**：
```json
{"comBeforeMonthZd": null, "ycDefName": "中债国债", "gjqx": "10年", "todaySyl": "1.69", "upYearSameDay": "-15.29", "comBeforeDayZd": "-0.39", "workTime": "2026-08-28"}
```
* **对接说明**：
  * 数据结构为 `[时间戳毫秒数, 收益率数值 (%)]`。
  * 更新频率为每个工作日 17:30。

---

### A3. Chicago Fed NFCI 与 ANFCI 历史数据直接下载验证

#### 1. 发现可用入口
芝加哥联储采用 `FedRelease` 数据组件，元数据发现端点：
* **API 目录端点**：`https://data.chicagofed.org/cfed-drm-chicago/NFCI` (HTTP 200)

#### 2. 直接下载 URL 验证
* **CSV 下载 URL**：`https://api.data.chicagofed.org/NFCI/nfci-data-series-csv.csv`
* **XLSX 下载 URL**：`https://api.data.chicagofed.org/NFCI/contributions-data-series-xlsx.xlsx`
* **HTTP 状态码**：`200 OK`
* **验证状态**：**VERIFIED**
* **真实 CSV 响应片段（前 15 行）**：
```csv
Friday_of_Week,NFCI,ANFCI,Risk,Credit,Leverage,Nonfinancial_Leverage
01/08/1971,0.6,0.584,0.627,-1.1,-1.014,-1.407
01/15/1971,0.633,0.638,0.657,-1.102,-1.032,-1.424
01/22/1971,0.67,0.71,0.693,-1.104,-1.048,-1.439
01/29/1971,0.711,0.793,0.732,-1.109,-1.063,-1.452
02/05/1971,0.754,0.879,0.774,-1.116,-1.075,-1.462
02/12/1971,0.798,0.956,0.816,-1.126,-1.084,-1.47
02/19/1971,0.84,1.015,0.859,-1.14,-1.089,-1.475
02/26/1971,0.881,1.053,0.903,-1.157,-1.09,-1.478
03/05/1971,0.924,1.069,0.949,-1.179,-1.087,-1.477
03/12/1971,0.969,1.069,1,-1.206,-1.08,-1.474
03/19/1971,1.02,1.063,1.057,-1.238,-1.067,-1.468
03/26/1971,1.079,1.069,1.124,-1.275,-1.049,-1.46
04/02/1971,1.145,1.104,1.2,-1.318,-1.027,-1.45
04/09/1971,1.218,1.183,1.283,-1.365,-0.999,-1.437
```
* **文件格式与字段**：
  * `Friday_of_Week`: 日期（格式 `MM/DD/YYYY`）
  * `NFCI`: 综合金融状况指数
  * `ANFCI`: 剔除经济周期后的金融状况指数
  * `Risk` / `Credit` / `Leverage` / `Nonfinancial_Leverage`: 分项贡献值
* **数据频率与发布时滞**：周频（每周五），每周三上午 8:30 ET 发布上周值；起点 `01/08/1971`。

---

## 任务 B 详情：缺失序列的公开来源调研

### 1. `CHN_PMI_NEW_ORDERS`（制造业PMI新订单指数）
1. **推荐来源及优先级**：
   * **Primary (P2)**：国家统计局官网新闻发布页（`www.stats.gov.cn/sj/zxfb/`）
   * **Fallback (P3)**：AKShare 接口 `macro_china_pmi`
2. **端点/URL/接口名**：
   * P2 网页：`GET https://www.stats.gov.cn/sj/zxfb/`（当月发布文章，如《中国采购经理指数运行情况》）
   * P3 AKShare：`ak.macro_china_pmi()` ([AKShare 文档](https://akshare.akfamily.xyz/data/economic/macro_china.html#id16))
3. **验证状态**：**VERIFIED (P2)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段**：
   ```text
   2026年7月份，制造业采购经理指数（PMI）为49.2%，比上月下降1.1个百分点。
   新订单指数为48.5%，比上月下降2.7个百分点，表明制造业市场需求回落。
   ```
4. **频率与时滞**：月度，每月最后一天 09:30 发布当月值。历史起点 2005 年 1 月。
5. **Canonical 对接要点**：日期 `YYYY-MM`，扩散指数（临界点 50.0），单位 `%`。

---

### 2. `CHN_PMI_INPUT_PRICE`（PMI主要原材料购进价格指数）
1. **推荐来源及优先级**：
   * **Primary (P2)**：国家统计局新闻发布页
   * **Fallback (P3)**：AKShare 接口 `macro_china_pmi`
2. **端点/URL/接口名**：
   * P2 网页：`GET https://www.stats.gov.cn/sj/zxfb/`
   * P3 AKShare：`ak.macro_china_pmi()`
3. **验证状态**：**VERIFIED (P2)**
   * **HTTP 状态码**：`200 OK`
   * **数据依据**：国家统计局《中国采购经理指数运行情况》附表《相关指标解释及分类指数》。
4. **频率与时滞**：月度，每月最后一天 09:30 发布当月值。历史起点 2005 年 1 月。
5. **Canonical 对接要点**：日期 `YYYY-MM`，扩散指数，单位 `%`。

---

### 3. `CN_CORE_CPI_YOY`（核心CPI同比）
1. **推荐来源及优先级**：
   * **Primary (P2)**：国家统计局《解读当月CPI和PPI数据》官方文章
   * **Fallback (P3)**：AKShare 接口 `macro_china_cpi`
2. **端点/URL/接口名**：
   * P2 网页：`GET https://www.stats.gov.cn/sj/zxfb/`
   * P3 AKShare：`ak.macro_china_cpi()` ([AKShare 文档](https://akshare.akfamily.xyz/data/economic/macro_china.html#cpi))
3. **验证状态**：**VERIFIED (P2)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段（2026年7月份解读）**：
   ```text
   核心CPI：扣除食品和能源价格后，环比上涨0.3%，同比上涨0.9%，保持稳定。
   ```
4. **频率与时滞**：月度，每月 9~11 日 09:30 发布上月值（滞后 10 天左右）。历史起点 2013 年 1 月。
5. **Canonical 对接要点**：日期 `YYYY-MM`，同比增速（YoY），单位 `%`。

---

### 4. `CN_PPI_YOY`（PPI同比）
1. **推荐来源及优先级**：
   * **Primary (P2)**：国家统计局《工业生产者出厂价格》发布页
   * **Fallback 1 (P1)**：OECD SDMX / FRED (`CHNPPIALLMINMEI`)
   * **Fallback 2 (P3)**：AKShare 接口 `macro_china_ppi`
2. **端点/URL/接口名**：
   * P2 网页：`GET https://www.stats.gov.cn/sj/zxfb/`
   * P3 AKShare：`ak.macro_china_ppi()` ([AKShare 文档](https://akshare.akfamily.xyz/data/economic/macro_china.html#ppi))
3. **验证状态**：**VERIFIED (P2)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段（2026年7月份）**：
   ```text
   2026年7月份，工业生产者出厂价格同比上涨3.5%，环比下降0.7%。
   ```
4. **频率与时滞**：月度，每月 9~11 日 09:30 发布上月值。历史起点 1996 年。
5. **Canonical 对接要点**：日期 `YYYY-MM`，同比增速（YoY），单位 `%`。

---

### 5. `CN_DR007`（银行间存款类机构7天回购利率）
1. **推荐来源及优先级**：
   * **Primary (P1)**：中国货币网官方数据文件（`chinamoney.com.cn`）
   * **Fallback (P3)**：AKShare 接口 `repo_rate_hist` / `rate_interbank`
2. **端点/URL/接口名**：
   * P1 静态数据端点：`GET https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv`
   * P1 定盘利率端点：`GET https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/fdr.json`
   * P3 AKShare：`ak.repo_rate_hist(symbol="FDR007")`
3. **验证状态**：**VERIFIED (P1)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段（`prr-chrt.csv` 前 5 行）**：
   ```csv
   2026-08-28,,,,,,1.3378,1.3859,1.4069
   2026-08-27,,,,,,1.3594,1.395,1.41
   2026-08-26,,,,,,1.4105,1.4282,1.4265
   2026-08-25,,,,,,1.443,1.4531,1.4391
   2026-08-24,,,,,,1.4229,1.4339,1.4242
   ```
   * *注：第 1 列为日期，第 7 列为 DR001，第 8 列为 DR007（2026-08-28 为 1.3859%），第 9 列为 DR014。*
4. **频率与时滞**：日度（交易日实时变动，盘后 17:00 固化加权均价）。历史起点 2014 年 12 月。
5. **Canonical 对接要点**：日期 `YYYY-MM-DD`，年化利率数值，单位 `%`。

---

### 6. `CN_POLICY_RATE_7D`（央行7天逆回购操作利率）
1. **推荐来源及优先级**：
   * **Primary (P1)**：中国货币网“央行业务公告”
   * **Fallback 1 (P2)**：中国人民银行官网公开市场业务公告
   * **Fallback 2 (P3)**：AKShare 接口 `macro_china_gksccz`
2. **端点/URL/接口名**：
   * P1 页面：`GET https://www.chinamoney.com.cn/chinese/` -> 央行业务公告
   * P2 页面：`GET http://www.pbc.gov.cn/` -> 货币政策司
   * P3 AKShare：`ak.macro_china_gksccz()` ([AKShare 文档](https://akshare.akfamily.xyz/data/economic/macro_china.html#id20))
3. **验证状态**：**VERIFIED (P1) / UNVERIFIED (P2)**
   * **HTTP 状态码**：`200 OK` (中国货币网首页与公告流)
   * **真实公告依据**：央行每个工作日 09:00~09:20 发布《公开市场业务交易公告》，列明 7 天期逆回购操作量与中标利率。
4. **频率与时滞**：事件型 / 每个交易日 09:20 前发布。
5. **Canonical 对接要点**：日期 `YYYY-MM-DD`，政策利率，单位 `%`。

---

### 7. `CN_TSF_TOTAL`（社会融资规模增量）
1. **推荐来源及优先级**：
   * **Primary (P2)**：中国人民银行《社会融资规模增量统计表》
   * **Fallback (P3)**：AKShare 接口 `macro_china_shrzgm`
2. **端点/URL/接口名**：
   * P2 页面：`GET http://www.pbc.gov.cn/diaochatongjisi/`
   * P3 AKShare：`ak.macro_china_shrzgm()` ([AKShare 文档](https://akshare.akfamily.xyz/data/economic/macro_china.html#id18))
3. **验证状态**：**UNVERIFIED (P2 页面需在发布期爬取 HTML / Excel，直链因 PBOC 动态路由易变)**
   * **文档依据**：人民银行调查统计司每月月中发布《社会融资规模增量统计数据报告》。
4. **频率与时滞**：月度，每月 10~15 日不定期发布上月数据（滞后 10~15 天）。历史起点 2002 年。
5. **Canonical 对接要点**：日期 `YYYY-MM`，月度流量增量（Flow），单位 `亿元`。

---

### 8. `CN_GOV_BOND_FINANCING`（社融中政府债券融资）
1. **推荐来源及优先级**：
   * **Primary (P2)**：中国人民银行《社会融资规模增量统计表》中的“政府债券”列
   * **Fallback (P3)**：AKShare 接口 `macro_china_shrzgm`
2. **端点/URL/接口名**：
   * P2 页面：`GET http://www.pbc.gov.cn/` -> 调查统计司 -> 统计数据
   * P3 AKShare：`ak.macro_china_shrzgm()`
3. **验证状态**：**UNVERIFIED (P2)**
   * **文档依据**：人民银行社融增量统计表中明确包含“政府债券（国债+地方政府债券）”项目。
4. **频率与时滞**：月度，每月 10~15 日随社融发布。历史起点 2017 年口径完善后。
5. **Canonical 对接要点**：日期 `YYYY-MM`，月度增量，单位 `亿元`。

---

### 9. `CN_PRIVATE_TSF_YOY`（私人部门社融同比）
1. **推荐来源及优先级**：
   * **Primary (P1/P2 派生计算)**：系统内置计算引擎根据官方 PBOC 社融存量与政府债券存量推算
   * **Fallback (P3)**：AKShare 获取存量数据后本地计算
2. **推算可行性确认**：
   * **确认结论**：**完全可行**。
   * **计算公式**：
     $$\text{私人部门社融存量}_t = \text{社融总存量}_t - \text{政府债券存量}_t$$
     $$\text{私人部门社融同比}_t = \frac{\text{私人部门社融存量}_t - \text{私人部门社融存量}_{t-12}}{\text{私人部门社融存量}_{t-12}} \times 100\%$$
   * **经济学含义**：剔除财政/政府发债节奏扰动后，衡量实体经济企业与居民部门内生信贷需求的标准指标。
3. **验证状态**：**VERIFIED (计算逻辑与口径验证)**
4. **频率与时滞**：月度，与社融存量同步（每月 10~15 日）。
5. **Canonical 对接要点**：日期 `YYYY-MM`，同比增速，单位 `%`。

---

### 10. `CN_PROPERTY_SALES_AREA` / `CN_PROPERTY_SALES_VALUE`（商品房销售面积/销售额）
1. **推荐来源及优先级**：
   * **Primary (P2)**：国家统计局《全国房地产市场基本情况》发布页
   * **Fallback (P3)**：AKShare 接口 `macro_china_real_estate`
2. **端点/URL/接口名**：
   * P2 页面：`GET https://www.stats.gov.cn/sj/zxfb/`（当月发布文章，如 `t20260817_1965053.html`）
   * P3 AKShare：`ak.macro_china_real_estate()`
3. **验证状态**：**VERIFIED (P2)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段（2026年1—7月份数据）**：
   ```text
   1—7月份，新建商品房销售面积45021万平方米，同比下降11.8%；其中住宅销售面积下降12.7%。
   新建商品房销售额42718亿元，下降13.1%；其中住宅销售额下降13.2%。
   ```
4. **频率与时滞**：月度（1-2月合并，3月至12月每月 15~17 日发布当年前 N 个月累计值）。
5. **Canonical 对接要点**：
   * 日期：`YYYY-MM`。
   * 数值类型：**年初至今累计值（Cumulative）**，非单月值。
   * 单位：面积为 `万平方米`，销售额为 `亿元`。

---

### 11. `US_GSCPI`（全球供应链压力指数）
1. **推荐来源及优先级**：
   * **Primary (P1)**：纽约联储官网直链数据文件（`newyorkfed.org`）
2. **端点/URL/接口名**：
   * P1 CSV 直链：`GET https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/gscpi_interactive_data.csv`
   * P1 XLS 直链：`GET https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx`
3. **验证状态**：**VERIFIED (P1)**
   * **HTTP 状态码**：`200 OK`
   * **真实响应片段（`gscpi_interactive_data.csv` 最新数据列）**：
   ```csv
   Date,Jan-22,...,Jul-26,Aug-26
   30-Sep-1997,-0.49,...,-0.46,-0.49
   31-Oct-1997,-0.18,...,-0.29,-0.35
   ...
   31-May-2026,#N/A,...,1.81,1.81
   30-Jun-2026,#N/A,...,1.25,1.19
   31-Jul-2026,#N/A,...,#N/A,0.79
   ```
   * *注：CSV 最后一列即为最新修订后的全历史月度时间序列。*
4. **频率与时滞**：月度，每月第 4 个工作日 10:00 AM ET 发布上月值。历史起点 `1997-09-30`。
5. **Canonical 对接要点**：日期 `YYYY-MM`（行首为 `DD-Mon-YYYY`），标准差指数值（均值 0，正值表示供应链压力高于历史均值），无量纲。

---

## 全部失败尝试记录

| # | 请求 URL / 端点 | 请求方法 | 收到状态码 / 错误信息 | 原因分析 |
| :---: | :--- | :---: | :--- | :--- |
| 1 | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=GSCPI` | GET | `HTTP 404: Not Found` | FRED 官方未将纽约联储 GSCPI 收录在该 ID 下，应从纽约联储官网直采 |
| 2 | `https://yield.chinabond.com.cn/cbweb-mn/searchYc` | POST | `HTTP 404: Not Found` | 中债旧版检索接口已废弃下线，新接口为 `pgxh/yzQuery` |
| 3 | `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsPgFstBkRepo` | GET | `HTTP 404: Not Found` | 中国货币网历史 AJAX 接口已变迁 |
| 4 | `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FIBkLndRt` | GET | `HTTP 404: Not Found` | 中国货币网旧接口失效 |
| 5 | `https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/dr-rt.json` | GET | `HTTP 404: Not Found` | 猜想路径不存在，实际为 `prr-chrt.csv` / `fdr.json` |
| 6 | `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsPgFstBkRepoCurve` | GET | `HTTP 404: Not Found` | 中国货币网旧接口失效 |
| 7 | `https://www.chinamoney.com.cn/chinese/scjq/` | GET | `HTTP 404: Not Found` | 页面路由不存在 |
| 8 | `https://www.chinamoney.com.cn/r/cms/chinese/chinamoney/data/currency/prr-chrt.csv` | GET | `HTTP 404: Not Found` | 目录结构错误（正确目录为 `r/cms/www/` 而非 `r/cms/chinese/`） |
| 9 | `https://www.chinamoney.com.cn/data/currency/prr-chrt.csv` | GET | `HTTP 404: Not Found` | 短路径未做重定向 |
| 10 | `https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr.csv` | GET | `HTTP 404: Not Found` | 实际文件名带有 `-chrt` 后缀 |
| 11 | `http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125473/index.html` | GET | `HTTP 404: Not Found` | 人民银行货币政策司历史栏目静态 ID 变动 |
| 12 | `http://www.pbc.gov.cn/diaochatongjisi/116263/116277/index.html` | GET | `HTTP 404: Not Found` | 人民银行调查统计司历史栏目静态 ID 变动 |
| 13 | `http://www.pbc.gov.cn/diaochatongjisi/116263/116277/116281/index.html` | GET | `HTTP 404: Not Found` | 人民银行调查统计司历史子栏目静态 ID 变动 |
| 14 | `https://data.stats.gov.cn/easyquery.htm?m=QueryData&...` | GET | `HTTP 403: Forbidden` | 国家统计局数据门户部署了 WAF/反爬策略，禁止脚本无 Cookie 直接调用 API |

---

## 你的不确定性清单

1. **国家统计局商品房销售面积/销售额的“单月值”换算**：
   国家统计局官方仅公布 1-N 月的“累计值”（1-2月合并发布不拆分单月）。若监控系统需要单月流量数据，必须在系统内进行差分计算，且每年 1-2 月通常无法获取严格的单月独立值，此处需二次确认系统下游消费端是否接受累计值。
2. **中国货币网 `prr-chrt.csv` 的历史深度**：
   经实测，`https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv` 仅保留最近 66 个交易日（约 3 个月）的滚动窗口数据。若系统需要全历史（2014年至今），需要依赖中债/AKShare历史归档或建立日度入库增量累积。
3. **人民银行社融数据的自动化抓取稳定性**：
   人民银行官网（`pbc.gov.cn`）目前文章 URL 带有动态生成的内容 ID，每月发布的 Excel/HTML 路径并不固定，直接通过硬编码 URL 抓取存在时效性维护成本，更推荐在生产环境通过中国货币网公告或 AKShare 等中间件采集。
4. **不确定**：纽约联储 `gscpi_interactive_data.csv` 每月更新时是否会调整历史所有月份的估计值（由于其基于 PCA 模型，每次新增月份可能会对全历史序列产生轻微 revision），在写入数据库时建议设计为全量更新或覆盖机制。
