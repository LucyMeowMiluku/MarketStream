# MarketStream 技术所有权证据说明（中文核对版）

准备日期：2026-09-17  
当前分支：`codex/core-simplification`  
基准提交：`bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`  
项目定位：研究原型和技术验证，不是生产系统

## 1. 这份材料要回答什么

这份文件不是为了证明项目里的每一行代码都由我独立手写。项目开发中使用了 AI，也使用了公开论文、开源库和第三方数据平台。我要说明的是：我理解当前系统解决的问题；我能解释主要设计；我能指出实验能证明什么；我也能说明自己的判断、检查和修改。

| 导师关注的问题 | 本文件位置 | 主要原始证据 |
|---|---|---|
| 是否读过并核实文献 | 第 8 节和 `04_Literature_Verification_CN.md` | 论文原文页码、章节和正式链接 |
| 是否理解问题与架构 | 第 2–5 节 | 当前代码、设计记录和测试 |
| 是否有技术贡献 | 第 6 节和 `02_Technical_Contribution_Log_CN.md` | Git、代码、测试、AI 任务记录 |
| 是否理解实验与结果 | 第 7 节和 `03_Experiment_Reproducibility_CN.md` | 当前 JSON、历史 JSON、运行命令 |

## 2. 问题、范围和研究边界

MarketStream 处理流式市场事件。目标不是预测未来收益，也不是自动交易。目标是在事件到达后，找出值得人工检查的异常组合，并保留判断依据。

一个固定价格阈值不够。不同股票的正常波动不同。开盘和午间的正常状态也不同。单次价格变化还可能来自整个市场，而不是某一只股票。因此系统先计算八个较容易解释的因子，再把因子与该股票、该时段的历史状态比较。之后，CEP 状态机检查事件的方向、顺序、持续时间和跨股票关系。

当前核心数据流为：

```text
MarketEvent
  → Quality Gate
  → FactorSnapshot (10 s / 1 min / 5 min)
  → six CEP state machines
  → DetectionResult
  → Kafka / TimescaleDB / Streamlit
```

当前系统可以支持的结论有三类：

1. 当前代码通过 62 项测试和 Ruff 检查。
2. 受控生成序列可以触发六类规则，并显示规则的误警和消融变化。
3. 历史 IEX 运行证明真实输入可以进入系统并生成三种 cadence 的快照。

当前不能支持的结论也很明确：

- 不能报告真实市场 Precision、Recall 或 F1。真实标签还没有独立审阅和冻结。
- 不能把 IEX 当成完整 SIP 市场。
- 不能把 88 秒实流运行称为长期稳定运行。
- 不能用旧的人工注入实验证明当前 CEP 在真实市场全面优于 ML。

## 3. 系统数据流与组件职责

### 3.1 MarketEvent 和 Quality Gate

`MarketEvent` 统一 trade、quote、bar 和 news。它保留 event time、received time、source、feed、event ID、run ID 和 provenance。Quality Gate 标记重复、乱序、过旧、无效价格、crossed quote、零成交量和 feed gap。

质量问题不会被静默修复。严重质量标记会抑制告警。原始事件仍保留，方便之后检查。minute bar 的时间戳表示区间开始，因此代码给 bar 加了 60 秒 close grace，避免把正常 bar 当成 stale。

### 3.2 FactorSnapshot

Factor Engine 在 10 秒、1 分钟和 5 分钟窗口计算八个因子：

1. return surprise；
2. volatility burst；
3. relative volume；
4. spread stress；
5. quote imbalance；
6. signed trade imbalance；
7. market residual；
8. news shock。

快照还保存 factor state、方向、baseline 版本、质量状态和参与计算的 event IDs。这样 DetectionResult 可以追溯到原始事件。

### 3.3 CEP 状态机

当前没有用一个大型通用 NFA。系统使用六个较小的显式状态机：stock-specific dislocation、liquidity pressure move、news-confirmed move、flash reversal、sustained pressure 和 cross-asset shock。

状态机只处理有限的事件关系。它们不重新计算因子。检测器还统一处理 warm-up 抑制、严重质量抑制、300 秒 cooldown、dedupe key、severity 和 evidence IDs。

### 3.4 Kafka、TimescaleDB 和 Streamlit

- Kafka 负责在采集、因子计算和检测组件之间传递事件。它不是长期状态的唯一来源。
- TimescaleDB 保存原始事件、因子快照、检测结果和 baseline 状态。它支持时间查询和追溯。
- Streamlit 展示价格、因子、告警和对比结果。它不参与核心检测判断。

## 4. 主要架构决策

### 4.1 CEP 与旧四模型 ensemble

**问题：** 旧主线有 EWMA、Half-Space Trees、Isolation Forest 和 LSTM autoencoder。模型多，但事件顺序不容易说明。

**考虑的方案：** 保留四模型；继续增加模型；使用通用 NFA；使用轻量因子和几个显式状态机。

**最终选择：** 当前在线主线使用因子加六个 CEP 状态机。旧 ML 结果只保留为历史对照。

**原因：** 规则可以直接表达“新闻之后出现价格确认”“多个窗口持续压力”和“多个股票同时变化”。当前项目规模也不需要大型通用 NFA。

**代价：** 规则参数需要校准。单因子极端例外会产生误警。CEP 也不是天然比 ML 更准确。

**证据：** `cep/state_machines.py`、`evaluation/run_synthetic.py`、当前 synthetic JSON 和旧 comparison JSON。

### 4.2 10 秒、1 分钟和 5 分钟窗口

**问题：** 一个窗口无法同时表示快速冲击、短期持续和较慢背景。

**考虑的方案：** 单一窗口、更多窗口、固定三窗口。

**最终选择：** 10 秒、1 分钟和 5 分钟。

**原因：** 三种 cadence 已能分开快速反应和持续行为，状态数量仍然可控。

**代价：** 三个窗口不是从真实标签优化出的最优值。边界附近也可能出现重复证据。

**证据：** `processing/factor_engine.py`、`tests/test_lightweight_factor_engine.py` 和 synthetic scenarios。

### 4.3 Median、MAD 和经验分位数

**问题：** mean 和 standard deviation 容易受极端值影响。只用经验分位数时，样本少也不稳定。

**考虑的方案：** 固定阈值；mean/std；median/MAD；经验分位数；两者取较严格值。

**最终选择：** baseline 保存 median、MAD、0.995 和 0.999 分位数。`scale=max(1.4826×MAD,1e-6)`。elevated 使用经验 0.995 和 4×scale 中较严格的阈值；extreme 使用 0.999 和 6×scale 中较严格的阈值。

**原因：** median/MAD 较稳健，分位数保留数据分布信息。1.4826 是正态分布下的 MAD 缩放常数，不是无意义的换算数字。

**代价：** 这些参数是工程选择，不是当前真实数据上的最优参数。

**证据：** `processing/factor_state.py`、`processing/factor_engine.py` 和 baseline tests。

### 4.4 五维 baseline key

**问题：** 同一因子在不同股票、窗口、交易时段和日内位置上有不同正常范围。

**考虑的方案：** 全局 baseline；按 ticker；按 ticker 和 cadence；五维 cell。

**最终选择：** `(ticker, cadence, market_session, intraday_slot, factor_name)`。

**原因：** 它避免把开盘波动直接与午间比较，也避免把 SPY 和单只股票混在一起。

**代价：** cell 数量增加。每个 cell 的样本更少，所以需要暖机和状态恢复。

**证据：** `processing/factor_state.py`、`baseline/contracts.py` 和 baseline persistence tests。

### 4.5 Warm-up、先评分后更新和测试冻结

**问题：** 当天异常如果先进入 baseline，再给同一天评分，会降低异常程度并造成泄漏。

**最终选择：** 一个 cell 至少需要五个严格在先交易日。每次先读取历史并评分，再写入当天 observation。评测导入 baseline 后设置 `freeze=True`。

**代价：** 新部署或新股票会有一段无告警暖机期。

**证据：** `tests/test_lightweight_factor_engine.py` 和 replay validation tests。

### 4.6 六类状态机

**问题：** 因子越过阈值只说明一个局部信号异常，不一定形成有意义的市场事件。

**最终选择：** 六类有限模式。新闻确认最多保留五分钟。flash reversal 要求两个相反方向价格事件且间隔不超过两个 cadence。sustained pressure 在最近四个 frame 中要求三个不同窗口。cross-asset shock 在 60 秒内要求至少三个 ticker，并包括 SPY 或 QQQ。

**代价：** 部分模式对采样和缺失事件敏感。`stock_specific_dislocation` 的 extreme 单因子通道是当前主要误警来源。

**证据：** `cep/state_machines.py`、golden trace tests 和 pattern ablation。

### 4.7 Cooldown、去重和追溯

**问题：** 同一异常可能在相邻快照中重复告警。

**最终选择：** 相同 ticker、pattern 和 direction 默认在 300 秒内合并。dedupe key 还包含 pattern started_at。告警保存 factor evidence 和 event IDs。

**代价：** cooldown 内的第二个真实事件可能被合并。因此 DetectionResult 仍保留 suppressed reason。

**证据：** `cep/cep_detector.py` 和 `tests/test_factor_cep.py`。

### 4.8 Baseline epoch、持久化和恢复

**问题：** 重启后只在内存中的 baseline 会丢失。部分数据库恢复还可能产生混合状态。

**最终选择：** 显式使用 COLD_START、VERIFIED_BACKFILL 或 RESTORE。baseline、runtime 和 offset 属于同一 epoch/revision。checkpoint 保存 manifest 和 checksum。

**原因：** 启动状态不能靠猜测。状态不一致时应停止或执行明确恢复。

**代价：** 运维步骤更多。本轮还没有长期故障恢复运行证据。

**证据：** `baseline/`、`docs/BASELINE_PERSISTENCE.md` 和 7 项 persistence tests。

### 4.9 IEX 与 SIP 边界

**问题：** 免费或可用的实流来源不等于全市场 consolidated feed。

**最终选择：** 使用 Alpaca IEX 做接入验证，并在文档中记录 feed。

**代价：** IEX 只覆盖一个交易场所。报价、成交量和事件顺序可能与 SIP 不同。

**证据：** `data/evaluation/alpaca_live_e2e.json` 和 producer 配置。

## 5. 阈值与关键算法说明

主动买卖方向优先使用上游 side。若 side 不存在，则比较成交价和最近 bid/ask 中点。成交价不低于中点记为 buy，低于中点记为 sell。若 side 和可用中点都没有，该成交量不会进入 signed buy/sell 分子。这只是透明近似，不是完整 Lee–Ready 实现。

当前新闻情绪不是 FinBERT。系统使用一个小型正负词表：

```text
sentiment = (positive_count - negative_count)
            / (positive_count + negative_count)
news_shock = sentiment × log(1 + headline_count)
```

分母为零时 sentiment 为零。这种方法容易检查，但词义、否定和上下文处理较弱。

## 6. 我的六项主要技术贡献

完整记录见 `02_Technical_Contribution_Log_CN.md`。这里给出边界化摘要。

| 贡献 | 我做出的判断或检查 | AI 的作用 | 当前证据 |
|---|---|---|---|
| 统一事件、质量和追溯 | 确认统一合同和 provenance；定位 stale bar | 辅助重构和测试 | event model、quality tests、IEX output |
| 三窗口八因子和 baseline | 核查五维 key、20 日、5 日暖机、阈值和冻结 | 辅助实现 | factor code 和 tests |
| 六类 CEP 和告警控制 | 选择显式状态机；检查误警来源 | 辅助实现和实验 | state machines、synthetic JSON |
| baseline 持久化 | 发现重启丢失；提出 DB 恢复、epoch 和启动约束 | 按约束实现 | `baseline/` 和 7 项 tests |
| 无泄漏 replay | 质疑指标来源；要求预先标签、冻结和一对一事件评测 | 辅助实现 | replay validator 和 draft registry |
| IEX/Kafka/DB 链路 | 区分接入验证与准确率；复查 stale bar 和历史 soak | 辅助运行和定位 | live E2E 与 soak artifacts |

我不把这些工作写成“全部独立手写”。更准确的描述是：我提出或确认问题，给出约束，检查 AI 生成的实现，运行测试，质疑不合理结果，并要求再次修改。

## 7. 实验结果、冲突和限制

### 7.1 当前 synthetic protocol

2026-09-17 在当前工作树运行 20 个 seed。原始输出为 `reproduction_outputs/factor_cep_current_20260917.json`。

| 指标 | 结果 |
|---|---:|
| TP / FP / FN | 360 / 120 / 0 |
| Precision / Recall / F1 | 0.750 / 1.000 / 0.857 |
| delay p50 / p95 / p99 | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0131 / 0.0188 / 0.0299 ms |

120 个 FP 来自正异常场景中的额外未匹配告警。`40/240` 是另一组独立负对照场景。两者不能相加，也不是包含关系。

20 个 seed 的结果相同，因为当前生成器主要改变标识和时间平移，模式结构、幅度与规则边界没有实质变化。它说明脚本可重复，不说明真实市场稳定。

删除 `stock_specific_dislocation` 后，TP 从 360 变成 300，FP 从 120 变成 0。系统漏掉了 60 个生成异常。这是及时单因子告警与多证据确认之间的取舍。删除 activity 不改变结果，说明 `relative_volume` 当前不是六类规则的关键条件。

### 7.2 旧 ML 比较

旧对比使用真实 OHLCV 背景和人工注入异常。旧 CEP full 的 F1 为 0.785，ML ensemble 为 0.639，旧兼容协议平均 CEP 时间为 0.0033 ms。这个结果只描述旧协议。它不能证明当前六状态机在真实市场全面优于 ML，也不能与当前 0.0131 ms 直接合并。

### 7.3 Soak 和 live run

本轮不能重跑 soak，因为本地 Docker/Colima socket 不可连接。最近可用的 2026-09-10 历史结果是 240 个输入、76 个告警、p95 1.616 秒和零重复。2026-08-06 的 88 告警、p95 1.718 秒保留为旧结果。第一次 15 告警的失败 gate 也保留。

IEX run 约 88 秒，共 48,734 个事件，并产生 40 个 10 秒、5 个 1 分钟和 5 个 5 分钟快照。它证明接入、存储和 cadence 生成。它没有 ground truth，也仍在 warm-up，所以不能证明检测准确率。

### 7.4 尚未完成的正式 real replay

正式 real replay 要求 12 个异常区间和 12 个正常区间全部由独立人员审阅，并把 registry 冻结。还要验证数据 manifest、checksum、feed、baseline 时间和 evaluation 时间。当前 registry 仍是 draft，因此系统拒绝生成正式 Precision、Recall 和 F1。这是有意的评测保护，不是已有结果。

## 8. 文献、AI 和责任边界

十二篇文献已经按原文位置核实。它们支持设计动机，不直接证明本项目有效。例如 Cont 等人的 OFI 不是当前简化 imbalance；MacKinlay 的正式异常收益也不等于简单的 `r_i-r_m`。完整结果在 `04_Literature_Verification_CN.md`。

AI 参与了代码生成、调试、实验脚本、结构整理和语言修改。我的责任是给出问题、约束和验收标准，并检查输出。AI 任务索引见 `05_AI_Log_Index_CN.md`。Claude 历史目前不可访问，因此不会事后重构。私人聊天和其他项目不在提交范围内。

公开论文提供方法背景。Alpaca 提供 IEX 数据接口。Kafka、PostgreSQL/TimescaleDB、Streamlit 和 Python 库是第三方工具。导师提出需要证明技术理解和贡献，但本证据包框架还没有被导师确认。

## 9. 尚未完成的工作

1. 完成真实事件标签的独立审阅和冻结。
2. 在可用的 Kafka/PostgreSQL 环境重跑 current soak。
3. 用更长时间和更多交易日检查 IEX feed 行为。
4. 用冻结真实数据比较 CEP 与 ML，并统一输入、时间和调参协议。
5. 收到 ChatGPT 账户导出后补充完整可访问日志。

## 10. 技术答辩准备问题

1. 为什么 1.4826 不是随意数字？它把正态分布下的 MAD 转成标准差一致估计，但系统仍把它当作工程近似。
2. 为什么要先评分再更新 baseline？这样可以避免当天观测影响当天阈值。
3. 为什么 20 个 seed 完全相同？生成器改变的随机部分没有改变规则结构，所以它不是独立市场条件。
4. 120 FP 与 40/240 是什么关系？前者来自正场景匹配后的多余告警；后者是单独负对照场景。
5. 删除 dislocation 为什么 precision 提升、recall 下降？单因子 extreme 通道既能早报，也带来误报。
6. 为什么 activity ablation 无影响？当前六类规则不依赖 relative volume 作为关键完成条件。
7. IEX run 能证明什么？能证明真实输入链路和快照生成；不能证明真实检测效果。
8. 为什么不用旧 ML 结果直接下结论？旧协议、实现和标签来源与当前系统不同。
9. 重启后 baseline 怎么处理？只能选择显式 startup mode，并验证 epoch、checksum 和 offset 一致。
10. 如果导师问哪些代码由 AI 写，怎么回答？按日志和贡献表说明 AI 生成范围、我的约束、复查和测试，不把 Git author 当作纯手写证据。

## 结论

当前材料支持的是一个可检查的研究原型。它有统一事件合同、质量门、三窗口八因子、五维 baseline、六类 CEP、持久化设计和可追溯结果。当前 synthetic 和历史工程实验可以验证实现行为。它们还不能证明真实市场效果。我的技术所有权主要体现在问题识别、设计约束、结果质疑、验证和边界说明，而不是声称所有内容都由我独立完成。
