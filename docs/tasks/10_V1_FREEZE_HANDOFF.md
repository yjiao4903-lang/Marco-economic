# Task — V1 Freeze / Handoff

## 目标

冻结已经完成的 V0 + V1，为新开发窗口建立可信 baseline。

本任务**不开发任何新功能**。

## 执行 Prompt

```text
你当前负责 Personal Macro Asset Compass 的 V1 Freeze / Handoff。

不要继续开发 V1.2 或任何新功能。

请执行：

1. 阅读 README 和当前代码；
2. 查看 repository tree；
3. 运行完整：
   python -m pytest
4. 验证 README 中现有常用命令是否仍准确：
   - generate_fixtures
   - import_wind --dry-run
   - 正式 import
   - rebuild_db
   - check_quality
5. 检查 V1 已完成能力：
   - Excel/CSV importer
   - SHA256 去重
   - raw archive
   - canonical Parquet
   - DuckDB
   - quality check
   - rebuild
6. 清理明显无效 TODO，但不要重构工作代码；
7. 创建/更新 docs/01_CURRENT_STATE.md；
8. 填写：
   - Current Version
   - Completed
   - Last Test Result
   - Last Test Count
   - Known Issues
   - Frozen Components
   - Next Task = V1.2
9. 如 README 与实际代码不一致，只做必要修正；
10. 给出建议 Git commit message；
11. 给出建议 Git tag：v0.2-local-data-engine；
12. 不开始 V1.2。

最终输出：
## Baseline
## Test Result
## README Verification
## Frozen Components
## Known Issues
## Updated Docs
## Suggested Commit
## Suggested Tag
## Handoff Notes
```

## Definition of Done

- 完整 pytest PASS；
- README 与实际命令一致；
- CURRENT_STATE 已填充真实状态；
- 已知问题清楚；
- 没有新增 V1.2 功能；
- 已形成可供新窗口读取的 Git checkpoint。
