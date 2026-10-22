> 2026-10-22 核验口径：唯一报告主稿为 [07_Revised_Report_CN.md](07_Revised_Report_CN.md)，英文为对应译稿。数字、版本与缺失依据以[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)及[机器清单](reproduction_outputs/audit_20261022/result_registry.json)为准；历史结果不能合并为当前系统结果。

# MarketStream：项目问题、架构选择与验证情况

日期：2026-09-17

## 1. 项目要解决的问题

MarketStream 面向流式市场事件，主要任务是在事件到达后识别值得人工复查的异常组合，同时保留判断所依据的数据。系统目前不预测未来收益，也不执行自动交易。

固定价格阈值很难完成这个任务。不同股票的正常波动范围不同，同一只股票在开盘和午间的状态也可能相差很大。一次明显的价格变化还可能来自市场整体波动，并不一定是个股异常。基于这些情况，系统先计算八个含义比较直观的因子，再将它们与该股票在相应时段的历史状态进行比较。因子出现异常后，CEP 状态机会继续检查事件的方向、先后顺序、持续时间以及不同股票之间的关系。

这套系统目前能支持的结论主要有三项：

1. 本轮 CHECKS-20261022 在归档工作树通过 63 项测试和 Ruff 检查（含新增计数回归测试）。
2. 在受控生成的数据中，六类规则都能被触发，也可以观察各规则的误警情况和消融结果。
3. 历史 IEX 运行表明，真实输入可以进入系统，并生成 10 秒、1 分钟和 5 分钟三种频率的快照。

这些结果仍有清楚的边界：

- 真实标签尚未经过独立审阅和冻结，因此目前不能报告真实市场上的 Precision、Recall 或 F1。
- IEX 只代表一个交易场所，不能等同于完整的 SIP 市场数据。
- 现有实流运行只有约 88 秒，无法说明系统能够长期稳定运行。
- 旧实验使用了人工注入的异常，无法据此判断当前 CEP 在真实市场中整体优于 ML。

## 2. 整体设计思路

系统的数据流如下：

```text
MarketEvent
  → Quality Gate
  → FactorSnapshot (10 s / 1 min / 5 min)
  → six CEP state machines
  → DetectionResult
  → Kafka / TimescaleDB / Streamlit
```

这条数据流把工作分为三步。第一步统一并检查输入事件；第二步把原始事件转成可比较的因子快照；第三步根据事件之间的关系生成检测结果。消息传输、数据存储和结果展示分别交给 Kafka、TimescaleDB 和 Streamlit，检测逻辑不依赖展示层。

## 3. 各组件的作用

### 3.1 MarketEvent 与 Quality Gate

`MarketEvent` 为 trade、quote、bar 和 news 提供统一格式。每条事件保留 event time、received time、source、feed、event ID、run ID 和 provenance，方便后续追溯。

Quality Gate 会标记重复、乱序、过旧、价格无效、crossed quote、零成交量和 feed gap 等情况。严重质量问题会抑制告警，但原始事件仍会保存，便于之后检查。minute bar 的时间戳表示区间开始，直接按到达时间判断容易把正常 bar 标成 stale，因此代码加入了 60 秒的 close grace。

### 3.2 FactorSnapshot

Factor Engine 分别在 10 秒、1 分钟和 5 分钟窗口计算八个因子：

1. return surprise；
2. volatility burst；
3. relative volume；
4. spread stress；
5. quote imbalance；
6. signed trade imbalance；
7. market residual；
8. news shock。

每个快照还会记录 factor state、方向、baseline 版本、质量状态，以及参与计算的 event IDs。DetectionResult 因而可以继续追溯到对应的原始事件。

### 3.3 CEP 状态机

当前实现采用六个较小且逻辑明确的状态机，分别识别 stock-specific dislocation、liquidity pressure move、news-confirmed move、flash reversal、sustained pressure 和 cross-asset shock。

状态机只判断有限的事件关系，不会重复计算因子。检测器统一负责 warm-up 抑制、严重质量抑制、300 秒 cooldown、dedupe key、severity 和 evidence IDs。这样的划分让因子计算和模式判断各自保持清楚，也方便单独测试。

### 3.4 Kafka、TimescaleDB 与 Streamlit

- Kafka 在采集、因子计算和检测组件之间传递事件，但不作为长期状态的唯一来源。
- TimescaleDB 保存原始事件、因子快照、检测结果和 baseline 状态，用于时间查询和结果追溯。
- Streamlit 展示价格、因子、告警和对比结果，不参与核心检测判断。

## 4. 主要架构选择及原因

### 4.1 为什么从四模型 ensemble 转向 CEP

旧主线包含 EWMA、Half-Space Trees、Isolation Forest 和 LSTM autoencoder。它可以给出异常分数，但不容易说明事件的先后顺序和组合关系。我比较过继续保留四模型、增加更多模型、使用通用 NFA，以及使用轻量因子配合显式状态机几种方案。

当前在线主线最终采用因子加六个 CEP 状态机，旧 ML 结果仅作为历史对照。像“新闻出现后价格继续确认”“多个窗口持续承压”“多只股票在短时间内同时变化”这类条件，都可以直接写进状态机。项目当前的模式数量有限，也没有必要引入更复杂的通用 NFA。

这一选择也有代价。规则参数需要继续校准，单因子极端值可能带来误警，现有结果也不能说明 CEP 天然比 ML 更准确。相关实现和实验记录见 `cep/state_machines.py`、`evaluation/run_synthetic.py`、当前 synthetic JSON 和旧 comparison JSON。

### 4.2 为什么使用 10 秒、1 分钟和 5 分钟三个窗口

单一窗口很难同时覆盖瞬时冲击、短期持续和较慢的背景变化。窗口过多又会增加状态数量和重复证据。因此当前固定使用 10 秒、1 分钟和 5 分钟三种 cadence，用来区分快速反应与持续行为，同时控制系统复杂度。

这三个窗口属于工程选择，还没有根据冻结后的真实标签做最优参数搜索，窗口边界附近也可能生成重复证据。相关实现和测试见 `processing/factor_engine.py`、`tests/test_lightweight_factor_engine.py` 和 synthetic scenarios。

### 4.3 为什么使用 Median、MAD 和经验分位数

mean 和 standard deviation 容易受到极端值影响；只依赖经验分位数时，小样本下的阈值也不稳定。当前 baseline 同时保存 median、MAD、0.995 分位数和 0.999 分位数，并使用：

```text
scale = max(1.4826 × MAD, 1e-6)
```

elevated 阈值取经验 0.995 分位数与 `4 × scale` 中较严格的一项，extreme 阈值取经验 0.999 分位数与 `6 × scale` 中较严格的一项。median/MAD 对异常值更稳健，经验分位数则保留了实际分布的信息。1.4826 是正态分布下将 MAD 转为标准差一致估计时使用的缩放常数。

这些参数目前仍是工程设定，不能称为真实数据上的最优参数。相关代码和测试见 `processing/factor_state.py`、`processing/factor_engine.py` 和 baseline tests。

### 4.4 为什么 baseline 使用五维 key

同一个因子在不同股票、窗口、交易时段和日内位置上的正常范围可能不同。系统使用下面的五维 key：

```text
(ticker, cadence, market_session, intraday_slot, factor_name)
```

这样可以避免直接比较开盘与午间的波动，也不会把 SPY 和单只股票放进同一基线。相应的代价是 cell 数量增加，单个 cell 的样本会减少，因此系统需要 warm-up 和状态恢复机制。相关证据见 `processing/factor_state.py`、`baseline/contracts.py` 和 baseline persistence tests。

### 4.5 Warm-up、先评分后更新与评测冻结

如果当天观测先进入 baseline，再由更新后的 baseline 对当天评分，异常程度会被削弱，还会造成数据泄漏。当前要求一个 cell 至少具有五个严格在先的交易日。处理新数据时，系统先读取历史状态并评分，再写入当天 observation。评测导入 baseline 后会设置 `freeze=True`。

新部署或新增股票因此会经历一段不产生告警的暖机期。相关行为由 `tests/test_lightweight_factor_engine.py` 和 replay validation tests 覆盖。

### 4.6 为什么设置六类状态机

单个因子越过阈值，只能说明某个局部信号异常，还不足以构成完整的市场事件。六类状态机进一步限制了时间和组合关系：

- news-confirmed move 最多保留五分钟的新闻上下文；
- flash reversal 要求两个方向相反的价格事件，间隔不超过两个 cadence；
- sustained pressure 要求最近四个 frame 中出现三个不同窗口；
- cross-asset shock 要求 60 秒内至少出现三个 ticker，并包含 SPY 或 QQQ。

这些模式会受到采样频率和事件缺失的影响。当前 `stock_specific_dislocation` 中的 extreme 单因子通道也是主要误警来源。相关证据见 `cep/state_machines.py`、golden trace tests 和 pattern ablation。

### 4.7 Cooldown、去重与追溯

同一异常可能连续出现在相邻快照中。系统默认将 300 秒内 ticker、pattern 和 direction 相同的结果合并，dedupe key 还包含 pattern started_at。每条告警都会保留 factor evidence 和 event IDs。

这种方法可以减少重复告警，但 cooldown 期间出现的第二个真实事件也可能被合并。为便于检查，DetectionResult 仍会记录 suppressed reason。相关实现见 `cep/cep_detector.py` 和 `tests/test_factor_cep.py`。

### 4.8 Baseline 的持久化与恢复

baseline 如果只保存在内存中，系统重启后就会丢失。数据库只恢复一部分状态时，还可能产生相互不一致的结果。当前启动模式需要明确选择 COLD_START、VERIFIED_BACKFILL 或 RESTORE。baseline、runtime 和 offset 必须属于同一 epoch/revision，checkpoint 也会保存 manifest 和 checksum。

这样做可以避免系统在状态来源不明时继续运行，但会增加运维步骤。本轮还没有长期故障恢复的运行证据。相关设计与测试见 `baseline/`、`docs/BASELINE_PERSISTENCE.md` 和 7 项 persistence tests。

### 4.9 为什么使用 IEX 做接入验证

当前使用 Alpaca IEX 验证真实数据接入，并在输出中记录 feed。选择它主要是因为现阶段可以稳定获得该数据源。IEX 只覆盖一个交易场所，其报价、成交量和事件顺序都可能与 SIP 不同，因此这部分结果只用于验证链路，不用于代表整个市场。相关记录见 `data/evaluation/alpaca_live_e2e.json` 和 producer 配置。

## 5. 两项算法细节

### 5.1 主动买卖方向

系统优先采用上游提供的 side。side 缺失时，会比较成交价与最近 bid/ask 的中点：成交价不低于中点时记为 buy，低于中点时记为 sell。如果 side 和有效中点都缺失，这笔成交量不会进入 signed buy/sell 的分子。

这是一个便于检查的近似方法，功能上不等同于完整的 Lee–Ready 实现。

### 5.2 新闻情绪

当前新闻情绪采用小型正负词表：

```text
sentiment = (positive_count - negative_count)
            / (positive_count + negative_count)
news_shock = sentiment × log(1 + headline_count)
```

分母为零时，sentiment 取零。

这个方法简单，过程透明，但对词义、否定关系和上下文的处理较弱。

## 6. 当前实验结果及其含义

### 6.1 Synthetic protocol

本轮SYN-TRACE-20261022在归档工作树运行20个seed；原始输出为`reproduction_outputs/audit_20261022/factor_cep_traced.json`，不是9月17日旧文件。

| 指标 | 结果 |
|---|---:|
| TP / FP / FN | 360 / 120 / 0 |
| Precision / Recall / F1 | 0.750 / 1.000 / 0.857 |
| delay p50 / p95 / p99 | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0150 / 0.0306 / 0.0688 ms |

120 条 FP = 正场景的 60 条未匹配告警 + 负对照的 60 条告警。360 个正场景产生 420 条告警，240 个负对照产生 60 条告警；负对照中有 40 个场景至少触发一次，故 40/240 是场景触发率，不是告警条数。负对照的 60 条已包含在总计 120 条 FP 中，不得再次相加。该分解来自本轮逐场景复跑，不能仅凭旧汇总 JSON 反推旧运行的逐条归属。

20 个 seed 得到相同结果，原因是当前生成器主要改变标识和时间平移，没有实质改变模式结构、幅度和规则边界。这个现象可以说明脚本具有可重复性，暂时无法说明系统在不同真实市场条件下都很稳定。

移除 `stock_specific_dislocation` 后，TP 从 360 降至 300，FP 从 120 降至 0，同时漏掉 60 个生成异常。这反映了及时单因子告警与多证据确认之间的取舍。移除 activity 后结果没有变化，说明 `relative_volume` 目前不是六类规则中的关键完成条件。

### 6.2 与旧 ML 实验的关系

旧实验在真实 OHLCV 背景中人工注入异常。旧 CEP full 的 F1 为 0.785，ML ensemble 为 0.639；在旧兼容协议下，CEP 平均计算时间为 0.0033 ms。

这些数字只适用于旧协议。旧实验与当前系统在实现、标签来源和评测方式上都不同，因此不能用它证明当前六状态机在真实市场中整体优于 ML，0.0033 ms 也不应与当前 0.0150 ms 直接合并比较。

### 6.3 Soak 与 live run

2026-09-17 记录称 Docker/Colima 不可连接；本轮仅核验文件，未重跑 soak。最近可用的历史结果来自 2026-09-10：240 个输入、76 个告警、p95 1.616 秒、零重复。2026-08-06 的 88 个告警和 p95 1.718 秒作为更早的记录保留，第一次仅产生 15 个告警的失败 gate 也没有删除。

IEX run 持续约 88 秒，共接收 48,734 个事件，生成了 40 个 10 秒快照、5 个 1 分钟快照和 5 个 5 分钟快照。这次运行验证了接入、存储和 cadence 生成。由于没有 ground truth，而且系统仍处于 warm-up 阶段，它无法说明检测准确率。

## 7. 我在项目中的具体工作

我主导 MarketStream 核心方案的选择与开发推进，负责确定实施优先级、开发范围、关键设计约束和验证要求。我决定先完成底层主链，选定八因子、三窗口、六类 CEP 模式作为检测架构，并推动系统核心化与模块化。我直接提出 baseline 落库、每 cell 保留最近 20 个交易日、三种显式启动模式及恢复要求，同时要求评测使用真实数据、预先确定异常区间并提供可视化回放。

AI 作为辅助开发工具，为上述决策提供技术建议，协助细化方案、生成和重构代码、执行测试与调试，并起草和修改报告文字。详细因子／窗口／模式方案及显式状态机重构包含 AI 的具体建议，实施方案经我确认后开展；这些建议和实际生成记录在来源说明中逐项保留。

我的核心贡献体现为方案选型、具体问题与约束设计、开发取舍、验证要求和报告修订决策。贡献表将“我直接提出的要求”和“我选择采纳的建议”分别列证，并将个人决策、AI 辅助工作与最终代码／实验产物连接起来。

| 决策范围 | 我的具体动作 | AI 执行 | 直接依据 |
|---|---|---|---|
| 研究架构 | 确定底层优先，确认八因子／三窗口／六模式作为主线 | 提出详细建议，生成合同、因子和 CEP 代码 | 五列表 D01、D02；E01、E02 |
| 核心化与状态机 | 提出删减复杂性、保留核心与模块化，批准六状态机方案 | 拆分模块，生成六状态机及调度 | D03；E02 |
| baseline 持久化 | 直接提出 DB、20 日、恢复流程、单独模块与三种启动模式 | 补充一致性细节并实现持久化包 | D04、D05；E03 |
| 评测要求 | 质疑指标来源，要求真实数据、提前标签与 HTML，并采用严格冻结协议 | 核查来源，实现采集、标签、验证及评测 | D06、D07；E04 |
| 工程复验 | 要求完成未通过验证并继续复验 | 运行工具、查库、诊断并修复 stale bar | D08；E05 |
| 报告 | 要求定义、引用、结构、指标单位／分母和代码映射 | 起草、解释并改写文字与表格 | D09、D10；E06–E09 |

每项本人动作及日志原行号见[贡献主张—本人动作—AI 工作—日志定位—代码／实验依据](08_Contribution_Attribution_Matrix_CN.md)，技术细节见[中文贡献记录](02_Technical_Contribution_Log_CN.md)。详细架构最初撰写、全部核心代码手写及大量报告文字的本人撰写范围尚不能确认，已列为待补证据。Git author、代码存在或测试通过不能替代作者证据。

