# Task — V1.2 Multi-Source Acquisition

## 窗口范围

建议同一个新窗口完成：

- V1.2A
- V1.2B

这是完整的 Data Acquisition subsystem。

## 启动 Prompt

```text
你接手的是一个已经完成 V1 的现有仓库。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md
5. docs/tasks/20_V1_2_DATA_ACQUISITION.md

然后：
- 查看 repository tree
- 运行 python -m pytest 建立 baseline
- 对照 CURRENT_STATE 验证实际状态
- 如文档与代码冲突，以代码和测试为事实并报告差异
- 不重新初始化项目
- 不重写 V1 frozen components

本窗口只负责 V1.2 Multi-Source Acquisition。
```

## V1.2A Providers

优先实现：

- FRED
- OECD
- AKShare
- ChinaBond
- ChinaMoney

## V1.2B Providers

随后补充：

- PBOC
- SAFE
- NY Fed
- Chicago Fed

如果某数据已经能通过已有 Adapter 稳定获取，复用，不创建重复 provider。

## 推荐目录

```text
src/macro_compass/data_sources/
├─ base.py
├─ registry.py
├─ fred.py
├─ oecd.py
├─ akshare_source.py
├─ chinabond.py
├─ chinamoney.py
├─ pbc.py
├─ safe.py
├─ nyfed.py
├─ chicagofed.py
└─ wind_manual.py
```

## 统一接口

```python
class DataSourceAdapter:
    def fetch(self, series_id, start_date=None, end_date=None) -> pd.DataFrame:
        ...
```

返回 canonical-compatible DataFrame。

## 配置

新增：

```text
config/data_sources.yaml
```

至少包含：

- primary provider
- fallback provider
- provider-specific code
- frequency
- max staleness
- original source

## 增量更新

必须记录：

```text
last_observation_date
last_successful_fetch
last_provider
fetch_status
```

正常更新只抓新增区间。

同时提供单条 series backfill。

## 状态输出

至少：

```text
OK
STALE
FAILED
FALLBACK_USED
MANUAL_REQUIRED
```

生成：

```text
data_status.csv
manual_fetch_required.csv
```

## 失败隔离

一个 provider/series 失败，不得阻止其他数据继续更新。

网络 integration tests 与 deterministic unit tests 分离。第三方页面解析逻辑使用 fixture 测试。

## Batch A 首批链路

优先尝试：

```text
China CLI
PMI New Orders
Industrial Production
Retail Sales
CPI
PPI
US 10Y Real Yield
Broad USD
ANFCI
China 10Y Yield
CSI300
USD/CNY
```

## 禁止

- Transform Engine
- Signal Score
- Macro Factor
- Asset Score
- Streamlit
- Cloud
- ML

## Acceptance Criteria

1. 至少 5 个外部序列成功自动进入 canonical；
2. 至少 3 个 provider 被真实验证；
3. 重复更新不重复写入；
4. 单 source 失败全局任务仍继续；
5. fallback 有显式状态；
6. manual fetch list 可生成；
7. Wind importer 保持兼容；
8. DuckDB rebuild 保持通过；
9. parser 有 deterministic tests；
10. 完整 pytest PASS。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V1.2 Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行一次真实 update dry-run；
- 检查 source failure isolation；
- 检查 manual_fetch_required；
- 检查是否修改了 V1 frozen components；
- 列出所有真实验证成功与失败的 provider。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 CURRENT_STATE。

建议 tag：

```text
v0.3-multisource-acquisition
```
