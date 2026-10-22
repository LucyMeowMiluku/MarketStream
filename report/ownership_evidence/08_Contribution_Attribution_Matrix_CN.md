> 2026-10-22 核验口径：唯一报告主稿为 [07_Revised_Report_CN.md](07_Revised_Report_CN.md)，英文为对应译稿。数字、版本与缺失依据以[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)及[机器清单](reproduction_outputs/audit_20261022/result_registry.json)为准；历史结果不能合并为当前系统结果。

# 贡献主张—本人动作—AI 工作—日志定位—代码／实验依据

[个人核心贡献说明](09_Core_Contribution_Statement_CN.md)概括本人主导的工作；本表保留逐项证据。

核对日期：2026-10-22。作者：XI LU。归属口径：**本人主导核心方案与开发推进，AI 辅助开发**。

我主导 MarketStream 核心方案的选择与开发推进，负责确定实施优先级、开发范围、关键设计约束和验证要求。我决定先完成底层主链，选定八因子、三窗口、六类 CEP 模式作为检测架构，并推动系统核心化与模块化。我直接提出 baseline 落库、每 cell 保留最近 20 个交易日、三种显式启动模式及恢复要求，同时要求评测使用真实数据、预先确定异常区间并提供可视化回放。

AI 作为辅助开发工具，为上述决策提供技术建议，协助细化方案、生成和重构代码、执行测试与调试，并起草和修改报告文字。详细因子／窗口／模式方案及显式状态机重构包含 AI 的具体建议，实施方案经我确认后开展；这些建议和实际生成记录在来源说明中逐项保留。

我的核心贡献体现为方案选型、具体问题与约束设计、开发取舍、验证要求和报告修订决策。贡献表将“我直接提出的要求”和“我选择采纳的建议”分别列证，并将个人决策、AI 辅助工作与最终代码／实验产物连接起来。

| 贡献主张 | 本人动作 | AI 工作 | 日志定位 | 代码／实验依据 |
|---|---|---|---|---|
| D01 我主导研究路线的实施优先级【直接提出】 | 在导师要求轻量方法的背景下，明确“前端后面再说，先把底层搭好”，随后确认底层优先实施。 | 检索与梳理方法，提出并细化实施计划，按批准顺序开发。 | [日志摘录 E01](Evidence_Attachments/Decision_Log_Excerpts.md#e01)；A L3、L68（本人）；L67、L69（AI）；L70（确认实施）。 | [因子引擎](../../processing/factor_engine.py)、[CEP 调度](../../cep/cep_detector.py)、[项目计划](../../docs/PROJECT_PLAN.md)。 |
| D02 我主导八因子／三窗口／六模式的架构选型【方案采纳】 | 确认实施包含八因子、10 秒／1 分钟／5 分钟快照、六类 CEP 和统一事件合同的底层方案，决定将其作为检测主线。 | 先在方案中列出详细因子、窗口和模式；按确认方案生成事件、因子与检测代码。 | [日志摘录 E01](Evidence_Attachments/Decision_Log_Excerpts.md#e01)、[日志摘录 E02](Evidence_Attachments/Decision_Log_Excerpts.md#e02)；A L67、L69→L70；L81、L85。 | [三窗口配置](../../config/settings.py)、[八因子](../../processing/factor_calculations.py)、[六模式](../../cep/state_machines.py)、[受控实验](../../data/evaluation/factor_cep.json)。 |
| D03 我主导核心化、模块化与状态机重构取舍【提出目标＋采纳方案】 | 提出删除无关复杂边界、保留核心链路并模块化；确认采用六个显式状态机及单一离线基线的方案。 | 提出具体模块拆分与状态机方案，新增六状态机、重写 CEP 调度，拆出窗口状态和因子计算。 | [日志摘录 E02](Evidence_Attachments/Decision_Log_Excerpts.md#e02)；B L209（本人目标）；L234→L235（方案与确认）；L253–L254、L261、L268、L274（AI 实施）。 | [状态机](../../cep/state_machines.py)、[窗口状态](../../processing/factor_state.py)、[golden trace 测试](../../tests/test_cep_golden_trace.py)。 |
| D04 我主导 baseline 持久化关键约束设计【直接提出】 | 指出进程重启会丢失历史并导致重新暖机；提出 DB 保存每 cell 最近 20 个交易日、业务键和启动时恢复内存，Kafka 负责传输。 | 把要求转化为数据库、repository、writer、运行状态和测试实现。 | [日志摘录 E03](Evidence_Attachments/Decision_Log_Excerpts.md#e03)；C L3（本人完整问题与流程）；L61、L69（AI 实施）。 | [持久化说明](../../docs/BASELINE_PERSISTENCE.md)、[repository](../../baseline/repository.py)、[持久化测试](../../tests/test_baseline_persistence.py)。 |
| D05 我主导启动与恢复流程的约束设计【直接提出＋确认细化】 | 要求单独模块、显式配置 COLD_START／VERIFIED_BACKFILL／RESTORE；提出可信 live、禁止旧聚合直接复制、checkpoint 一致及区分首次部署和数据丢失。 | 补充 registry 字段、revision、offset、checksum 和不可变工件等实施细节，经确认后编码。 | [日志摘录 E03](Evidence_Attachments/Decision_Log_Excerpts.md#e03)；C L30（本人约束）；L43→L44（AI 细化与本人批准）；L63、L67（AI 实施）。 | [启动协调](../../baseline/startup.py)、[checkpoint](../../baseline/checkpoints.py)、[持久化测试](../../tests/test_baseline_persistence.py)。 |
| D06 我主导真实数据评测与可视化回放要求【直接提出】 | 质疑 accuracy/recall 的数据来源，要求真实 live 或历史回放、提前确定异常区间，以及逐时刻因子、CEP、告警的 HTML 展示。 | 核查旧结果来源，设计严格回放方案，生成采集、标签、评测和 HTML 实现。 | [日志摘录 E04](Evidence_Attachments/Decision_Log_Excerpts.md#e04)；D L3（本人）；L66→L67（AI 方案与确认）；L83、L92（AI 实施）。 | [回放评测](../../replay/evaluator.py)、[标签](../../replay/labels.py)、[HTML](../../replay/html_report.py)、[草稿标签](../../data/replay/labels/iex_benchmark_v1.draft.json)。标签仍未冻结，无正式真实准确率。 |
| D07 我主导评测协议的选择与采用【方案采纳】 | 确认严格历史回放方案，将冻结标签、baseline 隔离和同协议评测作为接受结果的条件。 | 细化审核、hash、manifest、向前匹配和拒绝未冻结标签的技术规则，并编码测试。 | [日志摘录 E04](Evidence_Attachments/Decision_Log_Excerpts.md#e04)；D L66（AI 严格协议）；L67（本人确认）；L83、L92（AI 实施）。 | [输入验证](../../replay/validation.py)、[真实回放测试](../../tests/test_real_replay.py)、[事件指标](../../evaluation/metrics.py)。 |
| D08 我推动工程验证与问题复验【直接要求】 | 要求继续完成 Alpaca 实流、历史数据和 Kafka→DB soak 的验证，并发出继续复验指令。 | 运行工具、检查数据库和工件，定位并修复 minute bar stale，记录复验与限制。 | [日志摘录 E05](Evidence_Attachments/Decision_Log_Excerpts.md#e05)；A L213、L423（本人要求）；L467–L468、L491（AI 修复与记录）；D L292（本人事后询问修复含义）。 | [IEX 记录](../../data/evaluation/alpaca_live_e2e.json)、[soak 记录](../../data/evaluation/kafka_db_soak.json)、[质量测试](../../tests/test_data_quality.py)。 |
| D09 我主导报告中的异常定义与引用要求【直接提出】 | 要求在介绍中明确异常模式定义，综述写清具体作者、论文、发现与结论，并添加对应引用编号。 | 按要求补充定义、组织综述与引用文字；此前已生成完整报告参考稿。 | [日志摘录 E07](Evidence_Attachments/Decision_Log_Excerpts.md#e07)；F L84、L93、L139；报告起草来源见 [日志摘录 E06](Evidence_Attachments/Decision_Log_Excerpts.md#e06) F L52–L56。 | [完整参考稿](../MarketStream完整报告参考稿.md)、[当前报告](../report%20draft.md)、[文献核对](04_Literature_Verification_CN.md)。 |
| D10 我主导报告结构与结果呈现的修订要求【直接提出】 | 要求简化架构与实验章、解释指标用途、将计数／百分比／延迟分表并写单位和分母；要求核查方向推断、新闻分数、阈值、状态转换与代码映射。 | 解释代码，按要求改写章节、表格及文字，执行方法核对。 | [日志摘录 E08](Evidence_Attachments/Decision_Log_Excerpts.md#e08) G L173、L178、L210、L220、L272、L324；[日志摘录 E09](Evidence_Attachments/Decision_Log_Excerpts.md#e09) H L3。 | [报告结果章](../report%20draft.md)、[中文修订稿](07_Revised_Report_CN.md)、[英文修订稿](07_Revised_Report_EN.md)。 |

## 尚不能确认的归属

- **详细架构全部最初由本人生成：未确认。** 现有 A L67、L69 是 AI 方案，L70 是本人确认实施；可主张架构选择和实施决策，不能把批准等同于最初撰写。
- **核心实现和状态机代码全部由本人手写：未确认，且有 AI 生成记录。** A L81、L85 与 B L253、L268、L274 记录直接编码。若有本人后续手改，需补具体 diff／编辑历史，不能用 Git author 或当前自述替代。
- **大量报告文字由本人生成：本人自述，具体范围未确认。** F L52–L56 记录 AI 起草和扩写完整参考稿；D09、D10 可直接支持本人写作与修订决策。当前没有足够的逐段版本对照量化本人新增字数。

## 原创性与证据边界

本项目可以突出本人主导的具体问题、方案取舍和要求，以及针对 MarketStream 的因子—窗口—模式组合、baseline 恢复约束、可追溯告警和评测方案。项目定制贡献不等于公开统计方法或 CEP 概念的首次发明，也不能由合成结果证明真实市场优越性。MAD、订单失衡、市场残差、CEP、Isolation Forest 是公开方法；Kafka、TimescaleDB、Alpaca 是第三方平台。

本表每项个人决策都指向 user 记录；AI 方案和实际工具操作同时披露。代码／实验只作为决策落地或行为依据。缺失 Claude 历史、逐段人工写作记录和归档 JSON 转义缺陷保持可见，原始日志与既有 hash 清单不改写。

## 同步位置

本口径同步到中英文贡献记录、ownership statement、报告贡献段落、代码来源说明、AI 日志索引和 `report/提交1/` 的相应材料。文件间事实冲突以原始日志及本表的证据等级为准；历史对话中的旧表述作为历史保留。


## 验证证据范围（2026-10-22）

工程验证推进的个人决策依据仍为原日志；效果主张统一引用[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)。120 条 FP = 正场景的 60 条未匹配告警 + 负对照的 60 条告警；40/240 是触发场景数／负对照场景数，其中 40 个触发场景发出 60 条告警，已包含在总 FP 中。本轮归档工作树通过63项测试与Ruff；历史soak、旧注入与短时IEX分别列证，正式真实回放仍无合格标签和指标。测试与保存产物证明各自协议内的行为，不能代替作者来源证据。
