# 多 LLM 窗口开发交互指南

## 1. 工作模式

后续采用：

> 同一个项目 + 同一个代码仓库 + 多个开发窗口分阶段接力

窗口不是项目记忆。真正的项目记忆由：

```text
代码
Git history
00_MASTER_SPEC.md
01_CURRENT_STATE.md
02_ARCHITECTURE.md
当前 Task Spec
```

承担。

## 2. 推荐窗口划分

| 窗口 | 范围 |
|---|---|
| 旧窗口 | V0 + V1 Freeze/Handoff |
| Window A | V1.2A + V1.2B |
| Window B | V1.3 + V1.5A |
| Window C | V1.5B + V1.5C |
| Window D | V1.6 + V2 |
| Window E | V2.5 |
| Window F | V3 |
| Window G | V4 |

## 3. 什么时候继续当前窗口

继续当前窗口：

- 仍是同一认知模块；
- 代码范围高度相关；
- bug/测试尚未闭环；
- 当前窗口上下文清楚。

例如 V1.2A + V1.2B 都属于 Data Acquisition，建议同一窗口。

## 4. 什么时候开新窗口

建议开新窗口：

1. 阶段已验收；
2. 即将进入新的 subsystem；
3. 当前窗口历史过长；
4. LLM 开始频繁顺手重构；
5. 已形成 Git checkpoint。

## 5. 现在第一步

先让旧窗口执行：

```text
docs/tasks/10_V1_FREEZE_HANDOFF.md
```

旧窗口只做：

- 完整测试
- README 校验
- CURRENT_STATE 更新
- Known Issues
- Git checkpoint

不继续开发 V1.2。

## 6. 新窗口第一条消息

直接发送：

```text
你接手的是一个已经开发到 V1 的现有项目。
不要重新初始化，不要重新设计。

首先依次阅读：
1. README.md
2. docs/00_MASTER_SPEC.md
3. docs/01_CURRENT_STATE.md
4. docs/02_ARCHITECTURE.md
5. docs/tasks/20_V1_2_DATA_ACQUISITION.md

然后：
- 查看 repository tree
- 运行 python -m pytest 建立 baseline
- 对照 CURRENT_STATE 验证实际代码状态
- 如文档与代码冲突，以代码和测试为事实，并先报告差异
- 只执行当前 Task Spec
```

## 7. 不要这样说

不要：

```text
我想做一个宏观量化系统，你重新帮我设计。
```

也不要：

```text
根据我们以前所有讨论继续。
```

新窗口应以仓库文档为准。

## 8. 合格的新窗口接手回复

至少应包含：

```text
已读取哪些文档
baseline pytest 结果
当前代码状态
计划修改哪些文件
明确不修改哪些 frozen components
```

如果它没有 baseline 就开始大规模改代码，回复：

```text
先停止新增修改。按 Task Spec 先运行完整 baseline 测试，并确认 CURRENT_STATE 与仓库实际状态是否一致。不要提前开发。
```

## 9. 开发中你主要盯 4 件事

### 范围扩张

回复：

```text
不要扩大范围。严格按当前 Task Spec 开发；未来版本只保留接口，不实现。
```

### 重写 V1

回复：

```text
V1 数据层当前视为 frozen。除非能证明现有接口阻塞当前任务，否则不要重写。优先通过 adapter 扩展。
```

### 网络测试不稳定

回复：

```text
网络 integration test 与 deterministic unit test 分离。第三方网络偶发失败不能导致核心 pytest 不稳定；解析逻辑使用保存 fixture 测试。
```

### Silent fallback

回复：

```text
禁止 silent fallback。任何 fallback、stale、missing、manual required 都必须进入结构化状态输出。
```

## 10. 每个窗口完成时：第一轮 Self Review

发送：

```text
现在不要继续开发下一版本。

请对本次任务做 self-review：
1. 对照 Task Spec 逐条列 acceptance criteria；
2. 每条标记 PASS/FAIL；
3. 运行完整 pytest；
4. 运行 Task Spec 规定的 smoke/integration command；
5. 列出本次修改文件；
6. 列出所有已知限制；
7. 检查是否实现了范围外功能；
8. 检查是否破坏 V1 frozen components。

如果有 FAIL，继续修复，不要结束任务。
```

## 11. 第二轮 Handoff Review

全部 PASS 后发送：

```text
任务验收通过后，请完成交接：

1. 更新 docs/01_CURRENT_STATE.md；
2. 更新 README 中必要的运行说明；
3. 写入本次版本完成状态；
4. 记录最新测试结果；
5. 记录 Known Issues；
6. 给出建议 Git commit message；
7. 给出建议 Git tag（如果是阶段 checkpoint）；
8. 明确下一任务的输入接口；
9. 不开始下一版本。

最终只输出交接报告。
```

## 12. 测试失败时

回复：

```text
当前版本尚未达到 Definition of Done。不要进入下一版本。定位失败测试根因，修复后重新运行完整 pytest，并重新给出 acceptance checklist。
```

## 13. 数据源失效时

回复：

```text
不要伪造成功结果。

请将该 series 标记为 FAILED / MANUAL_REQUIRED，并：
1. 保留 deterministic parser fixture test；
2. 记录失败原因；
3. 检查是否有符合优先级规则的 fallback；
4. 如果没有，保持系统继续更新其他 series。
```

## 14. LLM 提议增加新 Core Signal

先要求回答：

```text
这个指标代表什么新的独立经济机制？
与现有 15 Core Signals 是否重复？
不加入会损失什么？
能否只放 diagnostic/satellite？
增加多少维护成本？
```

默认不加入 Core。

## 15. LLM 提出 ML/HMM

回复：

```text
记录为 V5 research candidate，不进入当前版本。当前优先采用可解释经济机制和历史验证。
```

## 16. Git checkpoint 建议

```text
V1       v0.2-local-data-engine
V1.2     v0.3-multisource-acquisition
V1.5     v0.4-macro-engine
V2       v0.5-asset-compass
V2.5     v0.6-validation
V3       v1.0-local
```

## 17. 你本人真正需要维护的内容

你只需要关注：

- 是否批准改变产品需求；
- 是否批准新增 Core Signal；
- 测试是否 PASS；
- CURRENT_STATE 是否更新；
- Git checkpoint 是否形成；
- `manual_fetch_required.csv` 是否要求 Wind。

## 18. 最简循环

```text
旧窗口 Freeze/Handoff
→ Git checkpoint
→ 新窗口读 4 份文档 + 当前 Task
→ pytest baseline
→ Implement
→ Self Review
→ pytest
→ Handoff
→ CURRENT_STATE
→ Git checkpoint
→ 下一窗口
```
