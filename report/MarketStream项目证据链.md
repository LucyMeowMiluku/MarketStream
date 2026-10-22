> 历史材料／非主稿（2026-10-22）：本文件保留旧口径，不作为当前结果或提交正文。唯一主稿见[中文修订报告](ownership_evidence/07_Revised_Report_CN.md)；计数解释与运行边界以主稿及其运行台账为准。

# MarketStream 项目证据链

> 用途：作为后续简历项目表述、面试准备和项目材料补证的事实底稿。  
> 核验日期：2026-09-09  
> 当前结论：**完成真实行情端到端验证的研究型技术原型，不属于生产落地。**

## 个人核心贡献概述

我主导 MarketStream 的核心方案选型与开发推进，确定底层优先、核心化与模块化的实施路线，选择八因子／三窗口／六模式主链，并直接提出 baseline 落库、20 日保留、显式启动与恢复约束。我要求真实数据、预先标签、可视化回放和工程复验，同时推动报告定义、引用及指标呈现的修订。AI 用于辅助方案细化、代码实现、测试调试及报告整理；具体技术建议和生成记录单独列明。

[完整个人核心贡献说明](ownership_evidence/09_Core_Contribution_Statement_CN.md)可直接用于项目材料；[五列证据表](ownership_evidence/08_Contribution_Attribution_Matrix_CN.md)逐项连接本人动作、AI 辅助、原始日志和产物。

## 使用说明

本文严格区分以下证据类型：

- **实测结果**：能够从测试输出或本地实验产物直接核验；
- **阶段结果**：能够证明某条工程链路或研究流程已经运行，但不能外推为真实业务效果；
- **技术验证**：来自合成数据、受控注入或基础设施测试；
- **待补证据**：当前材料不足，不能写成已完成事实；
- **个人归属**：区分个人决策与验证、AI 辅助、导师要求、第三方平台和公开方法。

简历中最适合突出的是：**可解释因子设计、状态化 CEP、无泄漏评测、实时数据工程与端到端可追溯性**。不能把合成或注入实验指标写成真实市场效果。

---

## 1. 问题背景

MarketStream 是一个面向金融市场的实时、可解释异常检测系统。早期系统采用 Isolation Forest、EWMA、Half-Space Trees 和 LSTM Autoencoder 四模型集成，但存在以下问题：

1. 多个模型职责重叠，异常分数和告警原因不容易解释；
2. 批量训练、推理和模型维护较重，不利于实时流处理；
3. 模型对事件方向、先后顺序和持续时间的表达较弱；
4. 早期主要使用合成异常，缺少严格冻结的真实历史事件标签；
5. 实时链路还需要同时解决坏数据、重复告警、状态膨胀和结果追溯问题。

2026 年 5 月的项目会议明确要求将研究核心转向轻量、可解释的复杂事件处理（CEP），保留原 ML/DL 系统作为比较基线，并明确区分人工输入和 AI 生成内容。

**目标结果**：将交易、报价、K 线和新闻统一为市场事件，在多个时间尺度计算金融因子，通过时间关系和多信号确认识别异常，同时保留从告警回溯到原始事件的证据。

**证据**：

- [项目会议纪要](../Qichen%20Wang的Zoom会议%202026-05-15%2019_36%28GMT%2B8_00%29.md)
- [项目 README](../README.md)
- [项目状态](../docs/STATUS.md)

---

## 2. 方案决策

### 2.1 核心取舍

- 将四模型 ensemble 从核心实时检测路径降为离线或 shadow baseline；
- 保留 Python、Kafka 和 TimescaleDB 流式架构；
- 定义 `MarketEvent → FactorSnapshot → DetectionResult` 三层稳定数据合同；
- 让 live 和 replay 复用同一数据质量、因子计算和 CEP 检测逻辑；
- 在 10 秒、1 分钟和 5 分钟窗口计算八个轻量金融因子；
- 使用六类具有方向、顺序和时间约束的 CEP 模式；
- 使用按 ticker、cadence、market session 和 intraday slot 划分的 Median/MAD baseline；
- 建立标签冻结、checksum、baseline 隔离和严格向前一对一事件匹配；
- 对 warm-up、坏数据和 cooldown 内重复命中进行告警抑制或合并。

### 2.2 八个因子

1. `return_surprise`：收益相对历史日内基准的偏离；
2. `volatility_burst`：窗口波动范围相对正常水平的放大；
3. `relative_volume`：成交量相对相同日内位置的异常程度；
4. `spread_stress`：bid-ask spread 相对正常价差的压力；
5. `quote_imbalance`：bid/ask size 的报价压力；
6. `signed_trade_imbalance`：主动买卖成交量失衡；
7. `market_residual`：扣除 SPY/QQQ 共同变化后的个股残差；
8. `news_shock`：新闻情绪方向与短时间聚集程度。

### 2.3 六类 CEP 模式

1. `stock_specific_dislocation`；
2. `liquidity_pressure_move`；
3. `news_confirmed_move`；
4. `flash_reversal`；
5. `sustained_pressure`；
6. `cross_asset_shock`。

**证据**：

- [研究算法、作者归属与参考边界](../docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md)
- [核心代码导学](../docs/CORE_WALKTHROUGH_CN.md)
- [实验复现与来源](ownership_evidence/03_Experiment_Reproducibility_CN.md)

---

## 3. 本人主导的核心贡献与 AI 辅助开发证据链

归属修订：2026-10-22。

我主导 MarketStream 核心方案的选择与开发推进，负责确定实施优先级、开发范围、关键设计约束和验证要求。我决定先完成底层主链，选定八因子、三窗口、六类 CEP 模式作为检测架构，并推动系统核心化与模块化。我直接提出 baseline 落库、每 cell 保留最近 20 个交易日、三种显式启动模式及恢复要求，同时要求评测使用真实数据、预先确定异常区间并提供可视化回放。

AI 作为辅助开发工具，为上述决策提供技术建议，协助细化方案、生成和重构代码、执行测试与调试，并起草和修改报告文字。详细因子／窗口／模式方案及显式状态机重构包含 AI 的具体建议，实施方案经我确认后开展；这些建议和实际生成记录在来源说明中逐项保留。

我的核心贡献体现为方案选型、具体问题与约束设计、开发取舍、验证要求和报告修订决策。贡献表将“我直接提出的要求”和“我选择采纳的建议”分别列证，并将个人决策、AI 辅助工作与最终代码／实验产物连接起来。

### 3.1 具体决策及直接依据

| 我的决策 | 本人消息依据 | AI 执行 | 对照表 |
|---|---|---|---|
| 底层优先并采用八因子／三窗口／六模式主线 | A L68、L70 | 详细方案、核心代码 | D01、D02 |
| 收缩为核心链路并模块化，采用六显式状态机 | B L209、L235 | 模块拆分与状态机实现 | D03 |
| baseline 落库、20 日保留、恢复及显式三启动模式 | C L3、L30、L44 | 数据结构细化与持久化实现 | D04、D05 |
| 真实数据、预先标签、HTML 回放与严格冻结协议 | D L3、L67 | 来源核查和评测实现 | D06、D07 |
| 继续完成未通过验证 | A L213、L423 | 工具执行、查库与 stale bar 修复 | D08 |
| 定义、引用、结构与指标呈现 | F L84、L93、L139；G L173、L324；H L3 | 参考稿起草与修改 | D09、D10 |

字母、原行号和消息角色见[日志摘录](ownership_evidence/Evidence_Attachments/Decision_Log_Excerpts.md)；五列交付表见[贡献主张—本人动作—AI 工作—日志定位—代码／实验依据](ownership_evidence/08_Contribution_Attribution_Matrix_CN.md)。本人提出的具体要求与本人确认采纳的 AI 建议分别标注。

### 3.2 原创与来源边界

项目原创性表述应落在 MarketStream 的定制组合、金融事件语义、状态化方案、恢复约束与可信评测，并指出我主导了哪些具体决策。详细架构最初撰写、核心／状态机全部本人手写及大量报告文字本人生成尚未证实，不能由“我决策”自动推出。AI 的核心代码生成与完整参考稿起草记录保留。

导师对轻量 CEP 的方向要求见会议纪要；MAD、CEP、订单失衡和市场残差是公开方法；Kafka、TimescaleDB、Alpaca 是第三方平台。Git 只提供版本证据。当前已有 17 份归档 Codex 会话，旧版“仓库没有 prompt／对话”的说法已过时；Claude 历史仍缺失。

### 3.3 推荐表述

> 我主导需求、优先级、架构选择与具体验收要求，选择八因子、三窗口、六模式作为研究主线，直接提出 baseline 落库与显式启动恢复约束。AI 根据我确认的方案细化实现、运行验证并整理报告；每项个人决策、AI 操作及落地产物均有对应证据。

## 4. 交付状态

### 当前阶段

**原型/技术验证。**

### 已完成

- 统一市场事件、因子快照和检测结果的数据合同；
- 数据质量检查和有界运行状态；
- 三种时间尺度的八因子计算；
- 六类方向性 CEP 模式及可解释告警；
- live/replay 共用核心处理链；
- 合成、受控注入、负对照、消融和基础设施测试；
- Alpaca IEX 真实行情端到端处理验证；
- Streamlit 调试和展示界面；
- 项目报告、代码说明、演示文稿和运行文档；
- 2026-09-09 重新运行：`160 passed in 5.30s`，Ruff 检查全部通过。

### 尚未达到

- 没有证据表明系统已经生产部署或由真实业务用户持续使用；
- 没有公开部署地址、SLA、持续运行周期或生产运维记录；
- 真实历史事件标签仍未完成独立审阅和冻结；
- 尚无可用于正式声明的真实市场 Precision、Recall 和 F1。

---

## 5. 落地范围

| 维度 | 已核验范围 |
|---|---|
| 开发时间 | Git 记录覆盖 2026 年 5 月至 8 月 |
| 跟踪标的 | AAPL、TSLA、NVDA、QQQ、SPY |
| 实时数据 | Alpaca IEX；不是 consolidated SIP |
| 事件类型 | trade、quote、minute bar、news |
| 时间尺度 | 10 秒、1 分钟、5 分钟 |
| 核心链路 | 数据源 → Kafka → 数据质量 → 八因子 → CEP → TimescaleDB → Dashboard |
| 使用范围 | 研究、开发和演示验证；未证明外部用户采用 |
| 历史数据 | 五标的约 12 个月 OHLCV 与新闻数据，按时间进行 60/20/20 切分 |

历史数据证据：

- [公开数据集 manifest](../data/historical/manifest.json)
- [Alpaca/Benzinga 数据集 manifest](../data/historical/alpaca/manifest.json)

---

## 6. 效果证据

### 6.1 实测：代码质量

- 2026-09-09 在当前工作区执行 `uv run pytest -q`：**160 项测试全部通过，用时 5.30 秒**；
- 执行 `uv run ruff check .`：**All checks passed**。

该结果证明当前代码在本地测试环境中符合既有测试约定，不等同于生产稳定性或真实市场有效性。

### 6.2 实测：真实行情端到端链路

一次 Alpaca IEX 实流运行中：

- 持久化事件总数：**48,734**；
- 覆盖标的：**5**；
- quote：**48,283**；
- trade：**446**；
- bar：**5**；
- 生成快照：10 秒 **40** 个、1 分钟 **5** 个、5 分钟 **5** 个；
- 5 条 minute bar 均未被错误标记为 stale；
- 所有端到端 gate 通过。

**证据性质**：真实输入下的传输和因子链技术验证；没有冻结 ground truth，不能证明检测准确率。

**证据**：[Alpaca 实流 E2E 结果](../data/evaluation/alpaca_live_e2e.json)

### 6.3 技术验证：Kafka/数据库 soak

- 输入合成 soak 事件：**240**；
- 成功持久化：**240/240**；
- 持久化告警：**88**；
- receipt-to-alert-persistence p50：**1.418 秒**；
- p95：**1.718 秒**；
- p99：**1.738 秒**；
- 重复告警：**0**；
- 告警可追溯率：**100%**。

**证据性质**：基础设施链路能够运行；输入是明确标记的合成 soak 数据，不是真实市场效果。

**证据**：[Kafka/数据库 soak 结果](../data/evaluation/kafka_db_soak.json)

### 6.4 失败—修正—复验

第一次 soak：

- 150/150 条事件成功落库；
- 延迟、去重和追溯 gate 通过；
- 但告警样本只有 15 条，未达到实验预期，因此完整 gate 判定失败。

随后扩大并调整测试样本，第二次运行形成 240 条事件和 88 条告警，完整 gate 通过。

**证据**：[第一次未通过的 soak 报告](../data/evaluation/soak-61164fa173/report.json)

### 6.5 技术验证：合成 CEP 实验

实验协议：六类模式 × 20 个随机种子 × 三档强度，共 **360 个预设异常事件**。

| 指标 | 结果 |
|---|---:|
| Precision | 0.750 |
| Recall | 1.000 |
| F1 | 0.857 |
| True Positive | 360 |
| False Positive | 120 |
| False Negative | 0 |
| 检测延迟 p50 | 10 秒 |
| 检测延迟 p95/p99 | 30 秒 |
| CEP 计算 p99 | 0.0495 ms |
| 重复告警率 | 0 |

不利结果：240 个负对照中有 40 个触发告警，false-alert rate 为 **16.7%**。这说明极端单因子例外仍存在误报风险。

**证据性质**：只能证明受控条件下的规则行为和评测链路，不能写成真实市场 F1。

**证据**：[Factor CEP 实验结果](../data/evaluation/factor_cep.json)

### 6.6 阶段结果：CEP 与旧 ML ensemble 对比

在 60 天真实 OHLCV、人工异常注入和合成情绪的受控实验中：

| 方法 | Precision | Recall | F1 | 平均计算时间 |
|---|---:|---:|---:|---:|
| 四模型 ML ensemble | 0.572 | 0.724 | 0.639 | 4.5135 ms |
| 完整 CEP | 0.754 | 0.818 | 0.785 | 0.0033 ms |

**证据性质**：受控注入条件下的算法比较。异常标签部分来自人工注入，不能外推为真实市场表现。

**证据**：[CEP/ML 对比结果](../data/comparison_results_nfa_tuned/comparison_60d_0.05.json)

### 6.7 定性真实事件案例

项目保留了四个真实日线事件案例，但新闻情绪使用占位值，且没有独立审阅的事件级 ground truth。

**证据性质**：只能用于定性展示，不能计算或声称可靠的 Precision、Recall、F1。

**证据**：[真实历史案例结果](../data/comparison_results/event_case_study.json)

---

## 7. 个人责任边界

### 可以主张

- 针对 MarketStream 设计三层数据合同和 live/replay 一致性机制；
- 设计八因子的选择、时间尺度、baseline 状态和输出结构；
- 设计六类 CEP 模式的方向、顺序、窗口、抑制和解释机制；
- 建立事件级评测、标签冻结、防泄漏和 provenance/checksum 门槛；
- 完成第三方行情接入、流处理、存储和可视化集成；
- 通过测试、合成实验、失败复验和真实实流检查系统行为。

### 不能主张

- 发明 Kafka、MAD、CEP、Isolation Forest、LSTM 或订单失衡方法；
- 系统已经投入生产或服务真实客户；
- 在真实市场数据上取得 F1 0.857 或 F1 0.785；
- 所有代码均由本人纯手写或完全独立完成；
- MarketStream 是 LLM Agent 系统；当前没有模型规划、工具调用、Agent memory、模型路由或 Agent eval 证据。

---

## 8. 待补证据

按简历价值和风险排序：

1. 建立人工与 AI 分工表，至少精确到核心模块和任务类型；
2. 说明两个 Git 身份分别对应谁，以及作者信息改写的原因；
3. 补充本人做过的关键调试记录、失败方案和设计修改；
4. 将当前未提交的测试、实流产物和评测材料形成规范 commit/tag；
5. 请独立审阅者完成并冻结真实历史事件标签；
6. 在冻结标签上运行真实 replay，获得正式事件级指标和置信区间；
7. 增加可访问部署地址、持续运行时长、故障记录和用户反馈；
8. 生成自动化测试覆盖率报告；
9. 若投 Agent 开发岗，补充包含模型推理、工具调用、状态/记忆管理和 Agent eval 的项目或模块。

当前标签状态可核对：[真实 replay 标签草稿](../data/replay/labels/iex_benchmark_v1.draft.json)。该文件仍为 `frozen: false`，不能用于正式真实市场效果声明。

---

## 9. 面试追问

1. 为什么四模型 ensemble 不适合作为核心实时链路？
2. 八个因子为什么这样选择？哪些因子在消融实验中最关键？
3. 为什么 baseline 必须先评分、后更新，并在测试期间冻结？
4. `news_confirmed_move` 如何保证新闻先发生、价格随后确认？
5. 第一次 soak 为什么失败？第二次调整为什么不属于为了通过测试而修改结论？
6. 负对照 16.7% 的误报来自哪条规则？如何降低它？
7. 真实 IEX 实流验证能够证明什么，不能证明什么？
8. 如何从一条告警追溯到 FactorSnapshot 和原始 MarketEvent？
9. 哪些代码由 AI 辅助生成？你采用了什么审查和验证方法？
10. 如果扩展到全市场，状态存储、baseline 和数据库哪里会先成为瓶颈？
11. 为什么使用一对一向前事件匹配，而不是逐点准确率或对称时间窗口？
12. IEX 与 SIP 覆盖差异会怎样影响因子和检测结论？

---

## 候选简历表述

> 以下内容必须在个人责任边界与你的真实经历一致后再使用。合成和注入实验必须保留数据性质限定。

### 项目标题与技术栈

**MarketStream｜可解释实时金融异常检测系统**  
Python、Kafka、TimescaleDB/PostgreSQL、Alpaca、Streamlit、CEP、PyTorch、scikit-learn、River

### 数据科学岗位版本

- 设计价格、成交、流动性、市场残差与新闻等八类可解释因子，采用分时段 Median/MAD baseline、时间顺序切分和冻结阈值，降低日内季节性及测试泄漏风险。
- 构建严格向前的一对一事件评测、负对照和消融实验；在真实 OHLCV＋人工异常注入的受控实验中，CEP F1 达 0.785，对比四模型 ensemble 的 0.639。
- 分析负对照中 16.7% 的误报，定位极端单因子告警带来的 Precision–Recall 取舍，并将其保留为真实标签验证问题。

### AI 应用岗位版本

- 构建融合实时行情、新闻情绪和状态化规则的可解释异常检测应用，将 trade、quote、bar 和 news 统一为可追溯事件协议。
- 将 Isolation Forest、HST、EWMA、LSTM Autoencoder 集成降为离线比较基线，以轻量 CEP 作为实时检测路径；受控实验平均单次计算时间为 0.0033 ms，对比旧 ensemble 的 4.5135 ms。
- 打通 Kafka—因子计算—异常检测—TimescaleDB—Streamlit 链路，并用 160 项自动化测试验证数据合同、质量门、状态边界和 live/replay 一致性。

### Agent 开发岗位版本

MarketStream 不是 LLM Agent 项目，适合作为事件驱动、状态管理和可观测性能力的旁证：

- 设计事件驱动的有状态决策系统，通过确定性事件 ID、有限状态、幂等告警、cooldown 和 provenance trace 实现可回放、可审计的实时控制流。
- 构建 live/replay 共用执行链和冻结输入评测机制；真实 IEX 实流验证中完成 48,734 条事件持久化及三时间尺度状态生成。

### 通用三点精简版本

- 负责 MarketStream 实时金融异常检测系统的研究重构，将四模型集成调整为三时间尺度八因子＋六类状态化 CEP，增强异常方向、时序关系与原因解释能力。
- 构建 Kafka、TimescaleDB 和 Alpaca 驱动的可追溯流处理链；真实 IEX 实流验证中处理并持久化 48,734 条五标的事件，生成 10 秒、1 分钟和 5 分钟因子快照。
- 建立无泄漏事件级评测、负对照和消融协议；在受控异常注入实验中取得 F1 0.785，并识别 16.7% 负对照误报所反映的规则取舍。

---

## 升维迁移

**原始事实**：项目把四模型集成改成了八因子和 CEP。

**高密度表达**：

> 针对多模型实时性与解释性不足，我推动将检测主链重构为三时间尺度八因子＋状态化 CEP，并通过受控对比、负对照和真实实流分别验证检测表现、误报边界与工程可运行性。

**升维动作**：将“使用了哪些技术”提升为“发现问题—作出取舍—建立机制—分层验证—明确边界”。

**可选重写题**：用一句话说明 minute bar stale 问题如何在真实数据中暴露、定位、修复并通过回归测试验证。

---

## 核心证据索引

| 证据 | 文件 |
|---|---|
| 系统定义、架构和实验边界 | [README](../README.md) |
| 当前实现及实流状态 | [STATUS](../docs/STATUS.md) |
| 研究算法与作者/参考边界 | [CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN](../docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md) |
| 研究方向调整与 AI 使用要求 | [项目会议纪要](../Qichen%20Wang的Zoom会议%202026-05-15%2019_36%28GMT%2B8_00%29.md) |
| 合成 CEP、负对照与消融 | [factor_cep.json](../data/evaluation/factor_cep.json) |
| Kafka/数据库 soak | [kafka_db_soak.json](../data/evaluation/kafka_db_soak.json) |
| 真实 Alpaca IEX E2E | [alpaca_live_e2e.json](../data/evaluation/alpaca_live_e2e.json) |
| CEP 与旧 ML 受控对比 | [comparison_60d_0.05.json](../data/comparison_results_nfa_tuned/comparison_60d_0.05.json) |
| 真实事件定性案例 | [event_case_study.json](../data/comparison_results/event_case_study.json) |
| 真实 replay 标签草稿 | [iex_benchmark_v1.draft.json](../data/replay/labels/iex_benchmark_v1.draft.json) |

