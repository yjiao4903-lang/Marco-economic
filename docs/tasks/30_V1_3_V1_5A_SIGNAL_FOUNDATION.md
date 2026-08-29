# Task — V1.3 Signal Registry + V1.5A Transform Engine

## 窗口范围

建议同一个窗口完成：

- V1.3 Signal Registry
- V1.5A Transform Engine

这是 Macro Engine 的地基。本窗口只做「注册 + 变换」，**不做任何打分聚合**。

## 启动 Prompt

```text
你接手的是一个已经完成 V1.2 的现有仓库。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md
5. docs/tasks/30_V1_3_V1_5A_SIGNAL_FOUNDATION.md

然后：
- 查看 repository tree
- 运行 python -m pytest 建立 baseline（应为 50 passed）
- 对照 CURRENT_STATE 验证实际状态
- 如文档与代码冲突，以代码和测试为事实并先报告差异
- 不重新初始化项目
- 不重写 V1 / V1.2 frozen components

本窗口只负责 V1.3 Signal Registry + V1.5A Transform Engine。
```

## V1.3 Signal Registry

### 要求

1. 新增 `config/signals.yaml`，以配置声明全部 **15 Core Fundamental Signals**
   （G1–G5、I1–I3、D1–D4、X1–X3，定义见 MASTER SPEC §5）；
2. M1–M6（Market）与 S1–S3（Structural）允许在 registry 中**声明占位**
   （标明 layer，不实现引擎）；
3. 每个 signal 至少声明：
   - `signal_id`、`name`、`layer`（core / market / structural）
   - `mechanism`：一句话说明它代表的经济机制（这是新增 Core Signal 的准入理由）
   - `factor`：所属 factor（growth / inflation / domestic_financial / global_financial）
   - `inputs`：输入 series_id 列表及各自角色（composite 需可分解 contribution）
   - `transforms`：变换链（V1.5A 实现的白名单之内）
   - `direction`、`neutral`（如 PMI 的 50、CLI 的 100）、`level_weight` / `momentum_weight`
4. registry 与 `config/indicators.yaml` 的关系要明确：
   indicators.yaml 仍是 series 元数据的唯一真源（V1.2 冻结约定）；
   signals.yaml 只引用 series_id，不复制 series 元数据；
   indicators.yaml 中 V0 时代的 `factor` 字段（liquidity / rates 等）
   如与 MASTER SPEC 因子分类冲突，以 MASTER SPEC 为准调整，并在报告中列出改动；
5. 信号注册必须**配置驱动**，不硬编码在代码里。

### 输入数据缺口的处理

15 个 Core Signal 所需的部分 series（如 PMI Input Price、GSCPI、DR007、TSF、
Government Bond Financing、DR007-Policy Rate 利差等）当前 canonical 中可能不存在或只有
synthetic fixture。要求：

- 每条 signal 记录其 inputs 的可用性；
- 输入缺失时该 signal 输出显式 status（如 `MISSING_INPUT` / `NO_SIGNAL`），不得崩溃、
  不得静默输出 0；
- 生成/更新缺失 series 清单，供后续 V1.2 扩展或 manual fetch 使用；
- **禁止**为凑齐输入而新增数据源或改写 data_sources 配置。

## V1.5A Transform Engine

### 要求

1. 新增 `src/macro_compass/transforms/`（或同级清晰模块），实现
   ARCHITECTURE §7 的完整白名单：

   ```text
   level, delta, pct_change, yoy, mom, moving_average,
   rolling_percentile, robust_zscore, neutral_gap,
   rolling_sum, rolling_mean, acceleration
   ```

2. 全部纯函数：输入 DataFrame/Series + 参数，输出结果。
   禁止网络访问、禁止 DB side effect、禁止隐式 forward fill
   （如需填充必须是显式参数且记录）；
3. indicators.yaml 既有 transform 声明（`level_gap`、`zscore`）与白名单命名不一致
   （应为 `neutral_gap`、`robust_zscore`）：统一到白名单命名，保持向后兼容读取
   或一次性迁移配置，并在报告中说明；
4. 每种 transform 至少 2 个确定性单元测试（含边界：短序列、NaN、全 NaN）；
5. 提供一个 smoke 命令，对 canonical 中真实存在的一条 series 跑完 transform 链并输出预览，
   作为人工验收入口。

## 推荐目录

```text
src/macro_compass/signals/
├─ registry.py        # 读取 signals.yaml，校验引用的 series_id 存在
└─ ...
src/macro_compass/transforms/
├─ __init__.py
├─ trend.py           # level / delta / pct_change / yoy / mom / acceleration
├─ smoothing.py       # moving_average / rolling_mean / rolling_sum
├─ stats.py           # rolling_percentile / robust_zscore / neutral_gap
└─ pipeline.py        # 按声明顺序应用 transform 链
config/signals.yaml
```

目录命名可由实现窗口微调，但 transforms 与 signals 必须分层清晰、互不反向依赖。

## 禁止

- Signal Score 聚合、Factor 计算（V1.5B / V1.5C）
- Market Confirmation、Structural Risk 引擎（V1.6）
- Asset Score、Streamlit、Cloud、ML
- 新增数据源 provider 或修改 `config/data_sources.yaml` 的 provider 定义
- 修改 canonical 契约与 V1 ingestion

## Acceptance Criteria

1. `config/signals.yaml` 覆盖 15 Core Signals，每条含 mechanism / factor / inputs /
   transforms / neutral / weights；
2. M1–M6、S1–S3 在 registry 中有 layer 声明占位；
3. registry 校验：引用不存在的 series_id 时报明确错误；
4. ARCHITECTURE §7 白名单 12 种 transform 全部实现；
5. transform 全部纯函数，无网络 / 无 DB side effect / 无隐式 forward fill；
6. 每种 transform 有确定性单元测试，完整 pytest PASS（原 50 + 新增全过）；
7. 输入缺失的 signal 输出显式 status，不崩溃、不静默；
8. smoke 命令可对一条真实 canonical series 输出 transform 链预览；
9. indicators.yaml transform 命名已统一到白名单，且 import/rebuild/update 既有命令不回归；
10. V1 / V1.2 frozen components 未被重写（data_sources 错误契约、状态语义、
    canonical 契约、Wind importer 均保持）。

## 完成前 Self Review Prompt

```text
现在不要继续下一版本。

对照 V1.3 + V1.5A Task Spec：
- 逐条列 acceptance criteria PASS/FAIL；
- 运行完整 pytest；
- 运行 transform smoke 命令并贴出输出；
- 检查 transforms 是否有网络/DB side effect；
- 检查是否实现了范围外功能（任何打分/聚合都算范围外）；
- 检查 V1 / V1.2 frozen components 是否被修改；
- 列出本次修改文件与所有已知限制。

存在 FAIL 就继续修复。
```

## Handoff

完成后更新 `docs/01_CURRENT_STATE.md` 与 README（新增 smoke 命令说明），
写明：signal registry 覆盖情况、transform 白名单实现情况、缺失输入 series 清单。

建议 tag：

```text
v0.4a-signal-foundation
```

（Window C 完成 V1.5B + V1.5C 后打 `v0.4-macro-engine`。）
