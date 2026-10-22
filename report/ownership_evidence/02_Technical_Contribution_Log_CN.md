> 2026-10-22 核验口径：唯一报告主稿为 [07_Revised_Report_CN.md](07_Revised_Report_CN.md)，英文为对应译稿。数字、版本与缺失依据以[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)及[机器清单](reproduction_outputs/audit_20261022/result_registry.json)为准；历史结果不能合并为当前系统结果。

# MarketStream 技术贡献记录

归属修订：2026-10-22。**本人主导核心方案与开发推进，AI 辅助开发。** 每项的直接消息、AI 执行和产物见[五列表](08_Contribution_Attribution_Matrix_CN.md)。


## 贡献 1：统一 MarketEvent、质量检查和来源追溯

| 项目 | 说明 |
|---|---|
| 问题 | 实时 trade、quote、bar、news 和历史回放原本可能使用不同格式。这样会让 live 和 replay 分叉，也不容易从告警返回原始输入。 |
| 本人主导的决策与要求 | 我确认实施包含统一事件、质量标记和来源追溯的底层方案，并要求后续验证真实链路；合同细节由 AI 方案细化，见对照表 D02、D08。 |
| AI 辅助开发工作 | AI 提出合同细节，生成和重构 dataclass、序列化、质量门与测试；minute bar 的定位和修复也有 AI 工具记录。 |
| 代码位置 | `processing/event_models.py`、`processing/data_quality.py`、`tests/test_event_models.py`、`tests/test_data_quality.py`。 |
| 技术决策 | `MarketEvent` 只允许一种 typed payload。没有上游 ID 时，用稳定字段计算确定性哈希。质量门使用有界状态检查 duplicate、out-of-order、stale、invalid price、crossed quote、zero volume 和 feed gap。 |
| 验证 | CHECKS-20261022：63 passed、Ruff通过；归档源码和输出见运行台账。2026-09-17的62 passed是历史摘要。 |
| 发现的问题 | Alpaca minute bar 的时间戳表示分钟区间开始时间。如果与逐笔事件共用 30 秒 stale 阈值，正常 bar 会被误判。 |
| 后续修改 | bar 单独增加 60 秒 close grace。实时 IEX 验证中的 5 条 bar 均未被标记为 stale。 |
| 原始证据 | [D02、D08；E01、E02、E05](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我决定采用统一合同方案，并要求真实链路继续复验。 |
| 不能主张 | Alpaca 的字段定义、Kafka 协议或事件流概念由我发明。 |

## 贡献 2：三时间窗口、八因子和五维 baseline

| 项目 | 说明 |
|---|---|
| 问题 | 单一固定价格阈值不能区分股票、交易时段、日内位置和正常波动水平。重启后只保存在内存中的 baseline 也会丢失。 |
| 本人主导的决策与要求 | 我确认采用八因子、10 秒／1 分钟／5 分钟及历史基准方案作为检测主线；20 日 baseline 落库与恢复约束另由我直接提出。见 D02、D04。 |
| AI 辅助开发工作 | AI 提出详细因子／窗口方案，经我批准后生成因子引擎；后续拆出窗口状态、因子公式，并实现 baseline 接口与测试。 |
| 代码位置 | `processing/factor_state.py`、`processing/factor_calculations.py`、`processing/factor_engine.py`、`tests/test_lightweight_factor_engine.py`。 |
| 技术决策 | 先读取历史并评分，再写入当天 observation。测试导入 baseline 后使用 `freeze=True`。signed factor 使用绝对距离；非 signed factor 只检查向上异常。 |
| 阈值 | scale 为 `max(1.4826 × MAD, 1e-6)`。elevated 取经验 0.995 分位和 4×scale 中较严格者；extreme 取 0.999 分位和 6×scale 中较严格者。1.4826 是正态假设下把 MAD 转成标准差一致估计的缩放常数。 |
| 因子 | return surprise、volatility burst、relative volume、spread stress、quote imbalance、signed trade imbalance、market residual、news shock。 |
| 主动买卖方向 | 如果上游提供 side，直接使用。否则用最近 bid/ask 中点推断：成交价不低于中点记为 buy，低于中点记为 sell。没有 side 且没有中点时，该成交量不会进入 buy/sell 分子。 |
| 新闻情绪 | 当前线上路径是透明词表计数，不是 FinBERT。分数为 `(positive_count-negative_count)/(positive_count+negative_count)`；`news_shock` 再乘 `log(1+新闻数)`。 |
| 验证 | 测试覆盖五天 warm-up、session 隔离、当天数据不参与当天评分、冻结 baseline 和重启一致性。 |
| 原始证据 | [D02、D04；E01、E02、E03](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我选择八因子／三窗口研究架构，并直接提出 baseline 落库与恢复要求。 |
| 不能主张 | MAD、分位数、订单失衡和市场残差是个人原创算法。 |

## 贡献 3：六类显式 CEP 状态机与告警控制

| 项目 | 说明 |
|---|---|
| 问题 | 多模型异常分数难以解释事件顺序。单窗口阈值也不能表达“新闻先发生、价格随后确认”或“压力持续多个窗口”。 |
| 本人主导的决策与要求 | 我提出删除无关复杂性、保留核心并模块化，确认采用六个显式状态机；具体状态机拆分和实现由 AI 完成。见 D03。 |
| AI 辅助开发工作 | AI 提出显式状态机方案，按我的核心化目标及批准方案新增 `cep/state_machines.py`、重构调度并编写测试。 |
| 代码位置 | `cep/state_machines.py`、`cep/cep_detector.py`、`tests/test_factor_cep.py`、`tests/test_cep_golden_trace.py`。 |
| 六类模式 | stock-specific dislocation、liquidity pressure move、news-confirmed move、flash reversal、sustained pressure、cross-asset shock。 |
| 关键参数 | 新闻确认保留 5 分钟；flash reversal 要求两个相反方向的价格原子事件，间隔不超过两个 cadence；sustained pressure 在最近 4 个 frame 中至少 3 个不同窗口同向；cross-asset shock 在 60 秒内至少覆盖 3 个 ticker，并包含 SPY 或 QQQ；默认 cooldown 为 300 秒。 |
| 告警控制 | warm-up 或严重质量标记时抑制告警。同 ticker、pattern、direction 在 cooldown 内合并。dedupe key 由 ticker、pattern、direction 和 pattern started_at 生成。 |
| 验证 | synthetic protocol、负对照、pattern ablation、golden trace、cooldown 和质量抑制测试。 |
| 发现的问题 | `stock_specific_dislocation` 允许 extreme return surprise 单因子直接告警，产生了所有 40 个负对照命中。 |
| 后续处理 | 项目保留该规则及其 precision/recall 取舍，等待真实正常期和冻结事件集验证；现有日志不足以把保留规则的最初判断单独归为本人。 |
| 原始证据 | [D03；E02](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我决定核心化、模块化并确认六状态机方案，推动其作为当前检测主线。 |
| 不能主张 | CEP 或状态机概念由我发明；当前规则已在真实市场上证明有效。 |

## 贡献 4：baseline epoch、持久化和恢复

| 项目 | 说明 |
|---|---|
| 问题 | baseline 只存在进程内存时，关机后会丢失。再次启动可能需要多日暖机。数据库被清空或只恢复一部分时，也不能自动当作首次部署。 |
| 本人主导的决策与要求 | 我直接提出重启状态丢失、DB 落库、每 cell 最近 20 个交易日、业务键与恢复流程；随后明确单独模块和 COLD_START、VERIFIED_BACKFILL、RESTORE。AI 补充 registry/revision/offset/checksum 细节后由我确认。见 D04、D05。 |
| AI 辅助开发工作 | AI 根据我明确的持久化和启动约束，细化数据结构，生成 `baseline/`、数据库模型、writer、checkpoint、backfill、协调器和测试。 |
| 代码位置 | `baseline/contracts.py`、`baseline/repository.py`、`baseline/startup.py`、`baseline/checkpoints.py`、`baseline/backfill.py`、`baseline/writer.py`、`tests/test_baseline_persistence.py`。 |
| 技术决策 | 启动模式必须显式设置；状态不一致时拒绝继续或从最近有效 checkpoint 恢复；baseline、runtime、offset 属于同一 epoch/revision；checkpoint 保存 Parquet、JSON、manifest 和 checksum。 |
| 验证 | 当前 7 项 baseline persistence 测试覆盖 epoch、恢复、checksum、同日覆盖和状态一致性。全量测试通过。 |
| 限制 | 当前没有生产环境长期运行证据。Docker 未启动，因此本轮没有重新完成端到端数据库故障恢复演练。 |
| 原始证据 | [D04、D05；E03](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我提出具体的重启风险、20 日落库和显式启动模式设计约束，AI 按批准方案实现。 |
| 不能主张 | 我独立手写了全部持久化实现，或该机制已在生产环境证明可靠。 |

## 贡献 5：无泄漏 replay、标签冻结和事件级评测

| 项目 | 说明 |
|---|---|
| 问题 | 早期 precision/recall 来自生成序列或人工注入异常。真实 live run 没有 ground truth。若看过 detector 结果后再改标签或 baseline，会产生评测偏差。 |
| 本人主导的决策与要求 | 我直接质疑现有 accuracy/recall 的数据来源，要求真实数据、预先异常区间与 HTML 流程；我确认采用 AI 细化的冻结标签、防泄漏和向前匹配协议。见 D06、D07。 |
| AI 辅助开发工作 | AI 核查旧指标来源，细化审核、冻结、manifest/checksum 和严格匹配协议，并生成采集、注册表、评测器、比较基线及 HTML。 |
| 代码位置 | `replay/labels.py`、`replay/validation.py`、`replay/evaluator.py`、`evaluation/comparison.py`、`evaluation/metrics.py`。 |
| 技术决策 | baseline 数据严格早于 evaluation 区间；测试引擎导入 baseline 后冻结；标签 hash 和数据 manifest 必须一致；12 个异常和 12 个正常区间全部批准后才计算真实指标；事件级一对一向前匹配。 |
| 验证 | 测试覆盖标签冻结拒绝、数据来源、时间顺序、baseline 泄漏、live/replay 一致性和事件指标。 |
| 当前状态 | 标签文件仍是 draft，`frozen: false`。因此正式 real replay 被有意阻止。 |
| 原始证据 | [D06、D07；E04](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我质疑指标来源并要求真实数据、预先标签和可视化，决定采纳严格评测协议。 |
| 不能主张 | 系统已经在真实市场上取得 F1 0.857 或 0.785。 |

## 贡献 6：Alpaca IEX、Kafka、TimescaleDB 链路和实流问题核查

| 项目 | 说明 |
|---|---|
| 问题 | 合成数据只能检查规则。还需要确认真实输入能否经过采集、Kafka、因子计算和数据库。 |
| 本人主导的决策与要求 | 我要求继续完成未通过的 Alpaca、历史数据和 Kafka→DB 验证，并确认实流验证与检测指标的边界。运行、数据库查询与 stale bar 诊断由 AI 执行。见 D08。 |
| AI 辅助开发工作 | AI 执行 smoke/E2E、数据库计数和 soak，定位并修复 stale bar，整理结果与限制；我提出复验要求。 |
| 代码位置 | `producers/alpaca_producer.py`、`processing/factor_stream.py`、`cep/online_scorer.py`、`storage/`、`scripts/run_backend_soak.py`。 |
| 验证 | IEX 运行约 88 秒，共持久化 48,734 条真实事件：48,283 quote、446 trade、5 bar；生成 40 个 10 秒、5 个 1 分钟和 5 个 5 分钟快照。 |
| soak | 2026-09-10 最近历史 run 为 240/240 事件、76 告警、p95 1.616 秒、零重复、全部可追溯。2026-08-06 的旧 run 为 88 告警和 p95 1.718 秒。 |
| 限制 | IEX 是单交易所数据，不是 SIP。88 秒运行仍处于 warm-up。soak 输入是 synthetic transport probe。 |
| 原始证据 | [D08；E05](08_Contribution_Attribution_Matrix_CN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| 个人核心贡献 | 我要求继续复验 Alpaca 和 Kafka→DB 链路，并确认结果的工程与效果边界。 |
| 不能主张 | 系统已经在真实业务场景稳定运行，或处理 48,734 条事件证明检测准确。 |


## 报告写作决策

本人明确提出异常定义、逐篇引用、简化结构及指标分表等要求；AI 起草和修改大量参考文字。本人逐段撰写范围待版本记录确认。见五列表 D09、D10 及待确认项。
