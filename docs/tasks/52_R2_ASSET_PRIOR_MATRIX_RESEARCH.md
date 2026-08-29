# R2 — Asset Prior Matrix Research（只读调研任务，交外部窗口）

> 状态：**占位文件，尚未撰写**。在 V1.6A 开发期间并行派发（负责人 2026-08-30 批准）。

## 性质

只读调研窗口任务：不修改仓库、不写代码，交付物为 Markdown 研究报告。
沿用「数据源调研」外包模式的铁律：证据可溯源、禁止编造、区分 VERIFIED/推断。

## 目标

对 7 个资产池资产（CN_EQUITY / HK_EQUITY / CN_GOV_BOND / CN_CREDIT / GOLD /
INDUSTRIAL_COMMODITY / CNY），逐资产研究：

- 主要宏观驱动（对应 15 Core Signals 与 4 因子）
- 预期方向（sign）与重要性分层（importance tier）
- 经济机制阐述、中国市场特异性
- 历史稳定性与 regime dependence
- 合理先验区间（不是精确最优 beta）

## 交付标准（负责人方案 §25）

每个资产至少包含：Driver / Expected Sign / Importance / Economic Mechanism /
Supporting Research / Contradictory Evidence / Regime Dependence / Confidence。

证据优先级：学术论文 > BIS / IMF / 央行 > 国内大型券商资产配置研究 > 可复现统计研究。

禁止：博客观点直接成为权重依据；单一年份相关性决定长期 beta；
根据本项目历史回测反推先验。

## 用途

作为 V2 Asset Compass 先验矩阵（AssetScore = Σ beta × MacroFactor）的经济学依据，
协调员抽验后归档 docs/research/，转写进 55 号任务书。
