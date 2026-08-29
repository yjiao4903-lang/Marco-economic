# Personal Macro Asset Compass — ARCHITECTURE

## 1. 设计目标

针对：

- 单人使用
- Windows 本地
- 低维护
- 无 Wind API
- 长期运行
- 后续可能多 PC
- 需要历史回溯

因此不采用重型服务化架构。

## 2. 分层

```text
[External Sources]
        ↓
[Source Adapters]
        ↓
[Canonical Normalizer]
        ↓
[Validation]
        ↓
[Canonical Parquet]
        ↓
[DuckDB Cache]
        ├─────────────┐
        ↓             ↓
[Transform]      [Market Data]
        ↓             ↓
[Signal Engine] [Market Confirmation]
        ↓
[Macro Factor Engine]
        ↓
[Asset Mapping]
        ↓
[Asset Compass]
        ↓
[Streamlit]
```

## 3. Source Adapter

Adapter 只负责：

1. 请求数据；
2. 解析原始响应；
3. 映射 canonical-compatible DataFrame；
4. 返回元数据。

不负责 Factor、Asset、UI 或投资方向判断。

统一接口建议：

```python
class DataSourceAdapter:
    def fetch(self, series_id, start_date=None, end_date=None) -> pd.DataFrame:
        ...
```

## 4. Source Registry

使用：

```text
config/data_sources.yaml
```

每个 `series_id` 声明：

- primary provider
- fallback provider
- provider-specific code
- frequency
- source quality
- staleness threshold

## 5. Canonical Layer

最小：

```text
series_id
date
value
source
source_file
import_time
```

推荐扩展：

```text
provider
original_source
observation_date
release_date
asof_date
vintage_date
```

## 6. Data Status

每条 series 至少支持：

```text
OK
STALE
FAILED
FALLBACK_USED
MANUAL_REQUIRED
```

单个数据源失败不得让整个系统崩溃。

必须生成：

```text
data_status.csv
manual_fetch_required.csv
```

## 7. Transform Layer

Transform 必须纯函数化。

禁止网络访问、DB side effect、隐式 forward fill。

支持：

```text
level
delta
pct_change
yoy
mom
moving_average
rolling_percentile
robust_zscore
neutral_gap
rolling_sum
rolling_mean
acceleration
```

## 8. Signal Layer

每个 Signal 输出：

```text
signal_id
date
level
level_score
momentum
momentum_score
score
freshness
coverage
status
```

Composite Signal 必须提供 contribution breakdown。

## 9. Macro Layer

只读取 Signal 输出，不得直接跳回 raw series。

主要输出：

- Growth
- Inflation
- Domestic Financial Components
- Fiscal
- Global Financial Conditions
- Breadth
- Confidence
- Regime

## 10. Market Layer

Market 与 Fundamental 隔离。

输出：

- trend
- percentile
- confirmation state
- divergence state

不得反向改变 Growth/Inflation。

## 11. Asset Layer

使用经济学先验矩阵。

V2 不得用历史收益自动搜索最优权重，也不得让资产自身价格进入该资产 Fundamental Score。

## 12. Validation Layer

V2.5 才允许：

- forward return
- bucket analysis
- regime analysis
- rolling beta
- weight robustness

允许结论：模型历史预测能力弱或不稳定。

## 13. UI Layer

V3 使用 Streamlit。

不建立 FastAPI / React / Next.js。

## 14. Cloud Layer

V4 才开发。

云端同步：

```text
raw/
canonical/
config/
```

本地保留：

```text
*.duckdb
cache/
logs/
.venv/
```

每台 PC 独立 DuckDB。
