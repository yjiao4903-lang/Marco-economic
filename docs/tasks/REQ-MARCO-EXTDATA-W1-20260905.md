# REQ-MARCO-EXTDATA-W1 — Macro Owner / Provider Consolidation & Low-Cost Derived Spreads

**Repository**：`yjiao4903-lang/Marco-economic`  
**建议 Issue**：`REQ-MARCO-EXTDATA-W1: consolidate macro ownership/providers and add low-cost derived macro spreads`  
**优先级**：W1 / GO NOW  
**任务编制时已知 main**：`f962e43f613bb6d8364aa61d385c46b00851940c`  
**要求**：开发者必须重新 fetch `origin/main`，不得假设该 SHA 仍是最新。

## 1. 目标

完成两个包：

### PKG-05 — Macro Provider / Owner Consolidation

收敛以下 4 个宏观输入：

1. `CN_PMI`
2. `CN_PPI_YOY`
3. `US_INITIAL_CLAIMS`
4. `US_CORE_CPI`

目标不是重复新增 indicator，而是：

- 确认唯一 canonical series；
- 明确 Marco 为宏观生产 Owner；
- 明确 primary / fallback / manual fallback；
- 将 Cross 同义 macro 输入逐步降为兼容消费，不形成第二套业务定义。

### PKG-06 — Low-Cost Derived Macro Spreads

新增两个派生状态：

1. `CN_DR007_SPREAD`
   - `CN_DR007 - CN_POLICY_RATE_7D`
   - owner = MARCO
   - role = Liquidity / Policy diagnostic

2. `US_10Y2Y_SPREAD`
   - `US_10Y - US_2Y`
   - owner = MARCO
   - role = macro regime / curve state
   - 不得作为短周期择时触发器

## 2. 当前仓库事实与边界

当前 Marco 已注册/具备 `CN_PMI`、`CN_PPI_YOY`、`CN_DR007`、`CN_POLICY_RATE_7D`、`CN_TSF_TOTAL`、`US_REAL_YIELD_10Y`、`USD_BROAD`、`US_SOFR` 等。

因此：

- 禁止新建 `CN_NBS_PMI_MFG` 作为与 `CN_PMI` 同义的第二 canonical id；
- 禁止新建第二个 `CN_PPI`；
- `CN_DR007_SPREAD` 应复用现有 legs；
- provider-specific identifier 只能放在 source registry / mapping，不能硬编码进 engine。

强制：
- Integration Contract v1 schema 不变；
- 不改现有 factor 权重；
- 不改 structural / fragility 语义；
- 不删除 legacy 注册项，除非独立迁移证明；
- `available_at` 必须因果安全；
- source failure 必须显式暴露，不允许默认值/静默 fallback。

## 3. M1 — 先做 Owner/Provider 基线审计

新增：

`docs/audits/EXTDATA_W1_MACRO_OWNERSHIP_BASELINE_20260905.md`

至少列出：

| canonical | registry path | provider route | live status | fallback | Cross duplicate | action |
|---|---|---|---|---|---|---|
| CN_PMI | | | | | | KEEP/UPGRADE |
| CN_PPI_YOY | | | | | | KEEP/UPGRADE |
| US_INITIAL_CLAIMS | | | | | | ADD/PROMOTE |
| US_CORE_CPI | | | | | | ADD/PROMOTE |

必须引用具体代码/配置路径，不能凭记忆填写。

## 4. M2 — CN PMI

- 保留 `CN_PMI` canonical id；
- 核对真实 provider route；
- 优先官方/当前项目已验证 provider；
- Wind 可作为 manual fallback；
- 国际镜像若 freshness/持续性不足，不得无条件升为 primary；
- source unavailable 时不得生成伪新值；
- observation/reference month、publication、available_at 分开。

## 5. M3 — CN PPI

- 保留 `CN_PPI_YOY`；
- 明确 metadata-only / live route 状态；
- 若缺 route，补正式 route；
- 语义必须是 YoY percent，不能用 price index level 静默替代；
- 明确 reference month、publication、available_at；
- 回归测试 source unavailable / stale / malformed。

## 6. M4 — US Initial Claims

建议 canonical：`US_INITIAL_CLAIMS`

要求：
- DOL/FRED `ICSA`；
- 周频；
- `ICSA` 只能在 provider mapping 层；
- 明确 release/available_at policy；
- 如 Cross 已有 ingestion，不要求本 PR 删除；只写迁移说明。

## 7. M5 — US Core CPI

建议 canonical：`US_CORE_CPI`

要求：
- BLS/FRED `CPILFESL`；
- raw canonical 保存 index level；
- 3m SAAR 如需要，只能作为 transform；
- 不与 Core PCE 混同；
- 季调年度修订必须按 revision policy 处理。

## 8. M6 — `CN_DR007_SPREAD`

定义：

```text
CN_DR007_SPREAD = CN_DR007 - CN_POLICY_RATE_7D
```

要求：

- 两腿单位统一；
- 日频输出时，政策利率使用 decision_time 前最新已发布且有效值；
- 禁止 future-fill；
- 政策利率调整日 publication 前后必须有测试；
- 缺 leg / PIT 不足时 fail closed；
- 只输出 liquidity/policy diagnostic，不自动修改资产权重。

必须覆盖：

1. 普通交易日；
2. 政策利率调整发布前；
3. 发布后；
4. DR007 缺失；
5. policy rate 缺失；
6. `available_at > decision_time`；
7. unit mismatch。

## 9. M7 — `US_10Y2Y_SPREAD`

定义：

```text
US_10Y2Y_SPREAD = US_10Y - US_2Y
```

要求：

- 优先复用 Treasury/FRED 已有 legs；
- 两腿都满足 cutoff；
- 明确 join policy；
- 不用最新值回填过去日期；
- 不在本轮添加 “0 穿越 => 自动减仓” 行为。

## 10. Cross 迁移说明

新增：

`docs/integration/MACRO_OWNER_CONSOLIDATION_W1.md`

必须列：

- Marco canonical id；
- Cross 当前同义 id；
- 目标消费路径；
- 暂不删除的兼容层；
- 哪些仍属于 Cross Market State；
- Integration Contract v1 本轮不改 schema。

如果这 4 个输入暂时没有被 Contract 导出：

- 只完成 Marco 端能力；
- 登记 future contract proposal；
- 不擅自给现有 JSON 加字段。

## 11. 测试与验收

最低要求：

- registry/config validation；
- provider mapping tests；
- PIT/available_at tests；
- missing/failure tests；
- derived spread tests；
- regression 证明 Integration Contract exporter schema/bytes contract 未被破坏；
- 全量 pytest；
- CI PASS。

## 12. GitHub 交付

建议分支：

`feature/extdata-w1-macro-owner-spreads`

PR：

`feat: consolidate W1 macro ownership and derived spreads`

PR 必须写：

```md
Refs: #<REQ issue>

## Scope
- PKG-05
- PKG-06

## No-scope confirmation
- Integration Contract v1 schema unchanged
- no factor weight changes
- no structural/fragility semantic changes

## Tests

## Real-data status

## PIT status

## Cross migration notes
```

**不要 merge。交 WEB-CONTROL 验收。**