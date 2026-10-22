# MarketStream 核心代码来源、个人决策与 AI 实施说明

归属修订：2026-10-22。作者：XI LU。**本人主导核心方案与开发推进，AI 辅助开发。**

我主导 MarketStream 核心方案的选择与开发推进，负责确定实施优先级、开发范围、关键设计约束和验证要求。我决定先完成底层主链，选定八因子、三窗口、六类 CEP 模式作为检测架构，并推动系统核心化与模块化。我直接提出 baseline 落库、每 cell 保留最近 20 个交易日、三种显式启动模式及恢复要求，同时要求评测使用真实数据、预先确定异常区间并提供可视化回放。

AI 作为辅助开发工具，为上述决策提供技术建议，协助细化方案、生成和重构代码、执行测试与调试，并起草和修改报告文字。详细因子／窗口／模式方案及显式状态机重构包含 AI 的具体建议，实施方案经我确认后开展；这些建议和实际生成记录在来源说明中逐项保留。

我的核心贡献体现为方案选型、具体问题与约束设计、开发取舍、验证要求和报告修订决策。贡献表将“我直接提出的要求”和“我选择采纳的建议”分别列证，并将个人决策、AI 辅助工作与最终代码／实验产物连接起来。

## 代码与执行来源

| 模块 | 本人决策 | AI 实施及日志 | 当前代码／验证 |
|---|---|---|---|
| 统一事件与数据质量 | 确认共用合同与底层方案，要求实流复验 | A L81 生成初版；A L467 修复 stale bar。E01、E02、E05 | `processing/event_models.py`、`processing/data_quality.py`；相应 tests |
| 八因子与三窗口 | 选择此检测主线，提出 baseline 持久化约束 | A L67/L69 细化方案→L70 批准；L81 生成初版；B L268/L274 模块化。E01–E03 | `processing/factor_state.py`、`factor_calculations.py`、`factor_engine.py` |
| 六模式状态机 | 要求核心化、模块化并批准显式状态机方案 | B L209→L234/L235；L253/L261 实现。E02 | `cep/state_machines.py`、`cep/cep_detector.py`；golden trace 与模式测试 |
| baseline 持久化 | 直接提出 20 日、DB 恢复、显式三模式与单独模块 | C L3/L30；AI L43 细化→L44 批准，L61/L63/L67 实现。E03 | `baseline/`；persistence tests |
| replay 与指标 | 要求真实数据、预先标签及 HTML，采用冻结协议 | D L3、L66/L67；AI L83/L92 实现。E04；旧事件指标 A L101 | `replay/`、`evaluation/metrics.py`；real replay、label、metric tests |
| 报告与说明 | 直接提出异常定义、逐篇引用、结构与指标呈现修改 | F L52–L56 起草扩写；本人修订决策 E07–E09 | 中文／英文贡献记录和报告 |

以上日志字母、原行号、消息角色及摘录见[决策与执行日志摘录](../report/ownership_evidence/Evidence_Attachments/Decision_Log_Excerpts.md)；完整五列交付表见[中文贡献归属表](../report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md)及[英文版](../report/ownership_evidence/08_Contribution_Attribution_Matrix_EN.md)。

## 原创性与公开来源边界

本项目的定制贡献包括八因子在三个时间尺度的组合、六类金融事件关系、状态与质量抑制、baseline 启动恢复约束及可信评测。个人贡献按本人提出或采纳的具体决策列证，不能仅因代码属于本项目就推断全部由本人手写。

MAD、分位数、订单失衡、市场残差、CEP 和 Isolation Forest 来自公开方法；Kafka、TimescaleDB、Alpaca 和 scikit-learn 是第三方平台或工具。引用方法不等于复制代码；现有证据也不足以保证所有文件都已完成逐行外部来源审计。

## 仍待确认

详细方案全部最初由本人生成、核心代码全部本人手写及本人新增报告文字的具体范围尚未证实，且存在 AI 直接生成记录。需要本人早期草图、具体手改 diff／编辑历史或逐段版本对照才能补充这些归属。当前自述、文件头姓名、Git author、能够解释代码及测试通过分别有其用途，均不能单独替代生成来源证据。Claude 历史缺失保持披露，既有原始日志不改写。

答辩可使用的责任表述：

> 我主导项目需求、方案选择与具体验收要求，选择八因子、三窗口、六模式作为研究架构，并直接提出 baseline 落库与显式启动恢复约束。AI 在我的决策下细化建议、实现和重构代码、运行检查及整理报告；我通过具体问题、约束和修订要求推动方案落地。每项决策与 AI 执行都有对应日志。

核心代码讲解见[CORE_WALKTHROUGH_CN.md](CORE_WALKTHROUGH_CN.md)。


## 验证证据范围（2026-10-22）

工程验证推进的个人决策依据仍为原日志；效果主张统一引用[运行台账](../report/ownership_evidence/Evidence_Attachments/Result_Run_Ledger_20261022.md)。120 条 FP = 正场景的 60 条未匹配告警 + 负对照的 60 条告警；40/240 是触发场景数／负对照场景数，其中 40 个触发场景发出 60 条告警，已包含在总 FP 中。本轮归档工作树通过63项测试与Ruff；历史soak、旧注入与短时IEX分别列证，正式真实回放仍无合格标签和指标。测试与保存产物证明各自协议内的行为，不能代替作者来源证据。
