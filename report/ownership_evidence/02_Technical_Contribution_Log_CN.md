# MarketStream 技术贡献记录

> 状态说明：本文记录的是当前材料可以支持的贡献边界。它不把 Git 提交等同于纯手写证明，也不把公开算法或第三方平台写成个人发明。

## 贡献 1：统一 MarketEvent、质量检查和来源追溯

| 项目 | 说明 |
|---|---|
| 问题 | 实时 trade、quote、bar、news 和历史回放原本可能使用不同格式。这样会让 live 和 replay 分叉，也不容易从告警返回原始输入。 |
| 我的判断 | 我接受并推进“先统一数据合同，再计算因子”的结构。我要求保留事件 ID、事件时间、接收时间、来源、feed、运行 ID、数据集 ID 和 provenance。坏数据先标记，不直接伪造修复值。 |
| AI 作用 | AI 辅助生成和重构 dataclass、序列化、质量门及测试代码。 |
| 代码位置 | `processing/event_models.py`、`processing/data_quality.py`、`tests/test_event_models.py`、`tests/test_data_quality.py`。 |
| 技术决策 | `MarketEvent` 只允许一种 typed payload。没有上游 ID 时，用稳定字段计算确定性哈希。质量门使用有界状态检查 duplicate、out-of-order、stale、invalid price、crossed quote、zero volume 和 feed gap。 |
| 验证 | 当前测试覆盖 typed payload、序列化、数据质量标记和状态上界。2026-09-17 全量测试为 62 passed。 |
| 发现的问题 | Alpaca minute bar 的时间戳表示分钟区间开始时间。如果与逐笔事件共用 30 秒 stale 阈值，正常 bar 会被误判。 |
| 后续修改 | bar 单独增加 60 秒 close grace。实时 IEX 验证中的 5 条 bar 均未被标记为 stale。 |
| 原始证据 | `data/evaluation/alpaca_live_e2e.json`、Codex 任务“核查准确率与数据来源 (2)”、提交 `91d6b8f`。 |
| 可以主张 | 我理解并验证了统一合同、质量标记和 stale bar 修正的原因与行为。 |
| 不能主张 | Alpaca 的字段定义、Kafka 协议或事件流概念由我发明。 |

## 贡献 2：三时间窗口、八因子和五维 baseline

| 项目 | 说明 |
|---|---|
| 问题 | 单一固定价格阈值不能区分股票、交易时段、日内位置和正常波动水平。重启后只保存在内存中的 baseline 也会丢失。 |
| 我的判断 | 使用 10 秒、1 分钟和 5 分钟三个窗口。baseline key 使用 `(ticker, cadence, market_session, intraday_slot, factor_name)`。每个 cell 按交易日保留最近 20 天，并至少需要 5 个严格在先交易日。 |
| AI 作用 | AI 辅助实现窗口状态、因子公式、baseline 数据结构、持久化接口和测试。 |
| 代码位置 | `processing/factor_state.py`、`processing/factor_calculations.py`、`processing/factor_engine.py`、`tests/test_lightweight_factor_engine.py`。 |
| 技术决策 | 先读取历史并评分，再写入当天 observation。测试导入 baseline 后使用 `freeze=True`。signed factor 使用绝对距离；非 signed factor 只检查向上异常。 |
| 阈值 | scale 为 `max(1.4826 × MAD, 1e-6)`。elevated 取经验 0.995 分位和 4×scale 中较严格者；extreme 取 0.999 分位和 6×scale 中较严格者。1.4826 是正态假设下把 MAD 转成标准差一致估计的缩放常数。 |
| 因子 | return surprise、volatility burst、relative volume、spread stress、quote imbalance、signed trade imbalance、market residual、news shock。 |
| 主动买卖方向 | 如果上游提供 side，直接使用。否则用最近 bid/ask 中点推断：成交价不低于中点记为 buy，低于中点记为 sell。没有 side 且没有中点时，该成交量不会进入 buy/sell 分子。 |
| 新闻情绪 | 当前线上路径是透明词表计数，不是 FinBERT。分数为 `(positive_count-negative_count)/(positive_count+negative_count)`；`news_shock` 再乘 `log(1+新闻数)`。 |
| 验证 | 测试覆盖五天 warm-up、session 隔离、当天数据不参与当天评分、冻结 baseline 和重启一致性。 |
| 原始证据 | Codex 任务“冻结median MAD基线”“解释八个因子表达式变量”“baseline cell落库计划”；提交 `b6b9686`、`5f1f856`。 |
| 可以主张 | 我提出并核查了 baseline 维度、暖机、冻结、状态恢复和因子解释。 |
| 不能主张 | MAD、分位数、订单失衡和市场残差是个人原创算法。 |

## 贡献 3：六类显式 CEP 状态机与告警控制

| 项目 | 说明 |
|---|---|
| 问题 | 多模型异常分数难以解释事件顺序。单窗口阈值也不能表达“新闻先发生、价格随后确认”或“压力持续多个窗口”。 |
| 我的判断 | 当前核心使用六个小型显式状态机，不继续保留通用 NFA 作为在线主线。复杂性放在有限的金融事件关系中，而不是继续增加模型数量。 |
| AI 作用 | AI 辅助实现状态机、重构检测器和测试。 |
| 代码位置 | `cep/state_machines.py`、`cep/cep_detector.py`、`tests/test_factor_cep.py`、`tests/test_cep_golden_trace.py`。 |
| 六类模式 | stock-specific dislocation、liquidity pressure move、news-confirmed move、flash reversal、sustained pressure、cross-asset shock。 |
| 关键参数 | 新闻确认保留 5 分钟；flash reversal 要求两个相反方向的价格原子事件，间隔不超过两个 cadence；sustained pressure 在最近 4 个 frame 中至少 3 个不同窗口同向；cross-asset shock 在 60 秒内至少覆盖 3 个 ticker，并包含 SPY 或 QQQ；默认 cooldown 为 300 秒。 |
| 告警控制 | warm-up 或严重质量标记时抑制告警。同 ticker、pattern、direction 在 cooldown 内合并。dedupe key 由 ticker、pattern、direction 和 pattern started_at 生成。 |
| 验证 | synthetic protocol、负对照、pattern ablation、golden trace、cooldown 和质量抑制测试。 |
| 发现的问题 | `stock_specific_dislocation` 允许 extreme return surprise 单因子直接告警，产生了所有 40 个负对照命中。 |
| 后续处理 | 没有为追求漂亮指标直接删除规则，而是记录 precision/recall 取舍，等待真实正常期和冻结事件集验证。 |
| 原始证据 | 当前 synthetic JSON、Codex 任务“比较状态机与NFA框架”、提交 `b112b08`、`67715af`。 |
| 可以主张 | 我能够解释六类模式的事件关系、状态边界、抑制和不利结果。 |
| 不能主张 | CEP 或状态机概念由我发明；当前规则已在真实市场上证明有效。 |

## 贡献 4：baseline epoch、持久化和恢复

| 项目 | 说明 |
|---|---|
| 问题 | baseline 只存在进程内存时，关机后会丢失。再次启动可能需要多日暖机。数据库被清空或只恢复一部分时，也不能自动当作首次部署。 |
| 我的判断 | 我首先提出 baseline cell 应落库、每个 cell 保留最近 20 个交易日、Kafka 负责传输、DB 负责状态。随后把启动方式明确为 COLD_START、VERIFIED_BACKFILL 和 RESTORE，并要求 epoch、checksum、runtime、offset 和不可变 checkpoint 一致。 |
| AI 作用 | AI 根据这些约束实现 `baseline/` 包、数据库模型、writer、checkpoint、backfill、启动协调和测试。这里不声称代码完全由我手写。 |
| 代码位置 | `baseline/contracts.py`、`baseline/repository.py`、`baseline/startup.py`、`baseline/checkpoints.py`、`baseline/backfill.py`、`baseline/writer.py`、`tests/test_baseline_persistence.py`。 |
| 技术决策 | 启动模式必须显式设置；状态不一致时拒绝继续或从最近有效 checkpoint 恢复；baseline、runtime、offset 属于同一 epoch/revision；checkpoint 保存 Parquet、JSON、manifest 和 checksum。 |
| 验证 | 当前 7 项 baseline persistence 测试覆盖 epoch、恢复、checksum、同日覆盖和状态一致性。全量测试通过。 |
| 限制 | 当前没有生产环境长期运行证据。Docker 未启动，因此本轮没有重新完成端到端数据库故障恢复演练。 |
| 原始证据 | Codex 任务“baseline cell落库计划”；当前工作树 diff；`docs/BASELINE_PERSISTENCE.md`。 |
| 可以主张 | 我发现了重启与错误恢复风险，并给出明确设计约束和验收条件。 |
| 不能主张 | 我独立手写了全部持久化实现，或该机制已在生产环境证明可靠。 |

## 贡献 5：无泄漏 replay、标签冻结和事件级评测

| 项目 | 说明 |
|---|---|
| 问题 | 早期 precision/recall 来自生成序列或人工注入异常。真实 live run 没有 ground truth。若看过 detector 结果后再改标签或 baseline，会产生评测偏差。 |
| 我的判断 | 我明确质疑“当前准确率是否来自 live data”，要求建立真实历史 replay、预先知道异常区间、逐窗口 trace 和 HTML 流水线。正式指标只允许使用独立审阅并冻结的标签。 |
| AI 作用 | AI 辅助实现历史采集、label registry、manifest/checksum、严格 replay evaluator、Isolation Forest 公平基线和 HTML 报告。 |
| 代码位置 | `replay/labels.py`、`replay/validation.py`、`replay/evaluator.py`、`evaluation/comparison.py`、`evaluation/metrics.py`。 |
| 技术决策 | baseline 数据严格早于 evaluation 区间；测试引擎导入 baseline 后冻结；标签 hash 和数据 manifest 必须一致；12 个异常和 12 个正常区间全部批准后才计算真实指标；事件级一对一向前匹配。 |
| 验证 | 测试覆盖标签冻结拒绝、数据来源、时间顺序、baseline 泄漏、live/replay 一致性和事件指标。 |
| 当前状态 | 标签文件仍是 draft，`frozen: false`。因此正式 real replay 被有意阻止。 |
| 原始证据 | Codex 任务“核查准确率与数据来源”；`data/replay/labels/iex_benchmark_v1.draft.json`；提交 `ae1373e`。 |
| 可以主张 | 我发现了现有结果的数据来源问题，并推动建立更严格的评测门槛。 |
| 不能主张 | 系统已经在真实市场上取得 F1 0.857 或 0.785。 |

## 贡献 6：Alpaca IEX、Kafka、TimescaleDB 链路和实流问题核查

| 项目 | 说明 |
|---|---|
| 问题 | 合成数据只能检查规则。还需要确认真实输入能否经过采集、Kafka、因子计算和数据库。 |
| 我的判断 | 将真实实流验证与检测效果评测分开。实流只检查连接、事件类型、五个 ticker、三种 cadence、质量标记和持久化。没有 ground truth 就不计算 Precision/Recall。 |
| AI 作用 | AI 辅助运行 smoke/E2E、检查数据库计数、定位 stale bar 原因并整理报告。 |
| 代码位置 | `producers/alpaca_producer.py`、`processing/factor_stream.py`、`cep/online_scorer.py`、`storage/`、`scripts/run_backend_soak.py`。 |
| 验证 | IEX 运行约 88 秒，共持久化 48,734 条真实事件：48,283 quote、446 trade、5 bar；生成 40 个 10 秒、5 个 1 分钟和 5 个 5 分钟快照。 |
| soak | 2026-09-10 最近历史 run 为 240/240 事件、76 告警、p95 1.616 秒、零重复、全部可追溯。2026-08-06 的旧 run 为 88 告警和 p95 1.718 秒。 |
| 限制 | IEX 是单交易所数据，不是 SIP。88 秒运行仍处于 warm-up。soak 输入是 synthetic transport probe。 |
| 原始证据 | `data/evaluation/alpaca_live_e2e.json`、`data/evaluation/kafka_db_soak.json`、三个 `soak-*/report.json`。 |
| 可以主张 | 我检查并区分了真实输入工程链路与检测效果，保留了失败 soak 和版本差异。 |
| 不能主张 | 系统已经在真实业务场景稳定运行，或处理 48,734 条事件证明检测准确。 |

## 总体个人边界

我可以主张：提出和核查研究问题、数据边界、架构约束、规则含义、评测协议、失败结果和测试标准；使用 AI 辅助实现后，对代码、结果和限制进行检查。

我不能主张：完全独立手写全部代码；发明 MAD、CEP、Kafka、Isolation Forest、订单失衡或事件研究；系统已生产部署；合成指标是真实市场指标。

