# Release / Version Policy (V4.5 Task 8)

> 生效：2026-08-30（负责人批准并入 V4.5 路线，见 `docs/00_MASTER_SPEC.md` §15）。
> 目的：区分 **Product Milestone** 与 **Git Release Tag**，为当前工程完成状态冻结一个
> **语义明确的 stable tag**，同时不重写任何历史 tag。

## 1. 两个概念

| 概念 | 定义 | 载体 | 是否可覆盖 |
|---|---|---|---|
| **Product Milestone** | 面向负责人的功能/验证里程碑（V0/V1/V1.5A/…/V4/V4.5），表达"这一阶段交付了什么能力"，与 MASTER SPEC §15 版本顺序一一对应 | `docs/00_MASTER_SPEC.md` §15 + `docs/01_CURRENT_STATE.md` | 里程碑推进后各版本保持顺序，不后退 |
| **Git Release Tag** | Git 层面可回滚/可审计的提交快照，用于对接验收、回滚、多 PC 回溯 | `git tag`（lightweight/annotated） | **永不重写**；新增稳定版本只打新 tag |

**核心纪律**：健壮性靠 tag 不可变；演进靠新 tag 追加。任何既有 tag（`v0.3`…`v1.0-local`）一经打标即冻结，后续版本只新增、不覆盖、不 `git push --force` 改写。

## 2. 命名约定

```
v<MAJOR>.<MINOR>[-<suffix>]
```

- **MAJOR 保留给产品级里程碑**：`v0.x` 表示 V0–V4 数据/引擎族（0 为非正式稳定前的
  迭代族）；`v1.0-local` 是负责人既定的 V3 Local Dashboard tag；`v2.x+` 预留未来。
- **MINOR 表示该族内的行进号**：每个 Product Milestone 完成后递增一次 semantic tag。
- **suffix（可选）**：语义后缀，如 `-data-completion`（V4.5）、`-cloud-mirror`（V4）。
- 历史 tag 继续存在，仅作审计锚点；当前工程完成状态 = 最新 semantic stable tag。

## 3. Semantic Stable Tag 定义

一个 Git Release Tag 被视为 **stable**，当且仅当同时满足：

1. 该阶段窗口全部 Acceptance Gate PASS（测试全绿、无越权变更、无反向数据流、
   无 synthetic 进 production、无 silent fallback、Known Issues 有 blocker 分类）；
2. 该 Product Milestone 的文档（`01_CURRENT_STATE.md` §8 交接记录 + README）已更新；
3. tag 指向的 commit 是干净的（`git status` 无夹带运行产物；`data/local/`/`*.duckdb`
   不上传）。

stable tag 应与 RUNNING 工程状态对齐：即"若在此 commit 停机，可完整重建并复现所有
真实报告"。

## 4. 当前工程 Tag 快照（截至 V4.5 冻结）

| Tag | Product Milestone | 语义 | 状态 |
|---|---|---|---|
| v0.3-multisource-acquisition | V0→V1.2 | 数据源族起点 | 历史 |
| v0.4a-signal-foundation | V1.3 + V1.5A | 注册表+变换引擎 | 历史 |
| v0.4-macro-engine | V1.5B + V1.5C | 信号+因子+Regime | 历史 |
| v0.4b-data-quality | V1.2C + V1.5D | 覆盖加固+质量门 | 历史 |
| v0.4c-pre-market-stable | V1.5E | 数据稳定版 | 历史 |
| v0.4d-market-confirmation | V1.6A | 市场确认层 | 历史 |
| v0.5-asset-compass | V2 | 资产罗盘 | 历史 |
| v0.6-validation | V2.5 | 历史验证 | 历史 |
| v0.7-structural-risk | V2.6 | 结构风险 | 历史 |
| v1.0-local | V3 | 本地 Dashboard | 历史 |
| v0.8-cloud-mirror | V4 | 云镜像 | 历史 |
| **v0.9-data-completion**（本窗口候选） | **V4.5** | **数据补全 + Coverage Matrix + 版本纪律** | **稳定（本窗口冻结）** |

> 说明：`v0.8-cloud-mirror` 与 `v1.0-local` 的 MINOR 顺序由历史既成决定决定，此处仅如实
> 登记，不重排、不重写。V4.5 之后由下一窗口（V4.6 Empirical Validation Round 2）按其
> 任务书定义新 tag。

## 5. 打 tag 程序（协调员/负责人）

1. 窗口自检：对照任务书逐条 Acceptance Gate PASS；
2. 协调员复核：test count、冻结组件 diff、CURRENT_STATE §8 已更新、Known Issues 更新；
3. 打 annotated tag 指向干净 commit：
   ```bash
   git tag -a v0.9-data-completion -m "V4.5 Historical Completion (data completion + coverage matrix + version policy)"
   git push origin v0.9-data-completion   # 若已配置远程
   ```
4. 若窗口自打 tag 命名与既有冲突/预留给后续里程碑（如 v0.5 预留给 Asset Compass 的先例），
   协调员可依本政策重命名（不覆盖任何历史 tag，只新增正确 semantic tag）。

## 6. 禁止事项

- 不 `git push --force` 或用 `-f` 覆盖任何既有 tag；
- 不把运行产物（`data/local/`、`*.duckdb`、`logs/`）混入 stable tag 指向的 commit；
- 不因未来小改动回退/删除 stable tag；
- 不在无负责人批准下跳版本（严格遵循 MASTER SPEC §15）。