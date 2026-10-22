> 2026-10-22 重新核验：本文件早期“当前”指2026-09-17，不再代表今天。唯一主稿为[07_Revised_Report_CN.md](07_Revised_Report_CN.md)，英文是译稿；旧草稿／提交副本为历史材料。结果以[运行台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)为准。

# MarketStream 报告修订记录

原始文件：`report/report draft.md`  
修订中文稿：`07_Revised_Report_CN.md`  
修订英文稿：`07_Revised_Report_EN.md`  
修订日期：2026-09-17；贡献归属更新：2026-10-22

## 修订原则

- 2026-09-17 的结果修订保留原始报告；2026-10-22 按作者要求同步更新各报告的贡献归属段落，不改实验结果。
- 当前版本结果与旧版本结果分开。
- synthetic、injected、soak、live 和 formal replay 分开。
- 没有原始输出支持的数字不作为主要结论。
- 文献只作为设计动机，不写成对 MarketStream 的直接验证。
- AI 辅助、人工判断和第三方方法分开说明。

## 关键修订

| ID | 原报告问题 | 修订内容 | 证据 | 状态 |
|---|---|---|---|---|
| R-01 | 摘要把旧 CEP/ML 对比写成显著优势 | 改成旧五分钟、人工注入协议的历史结果。明确不能证明真实市场全面优于 ML | `data/comparison_results_nfa_tuned/`；实验复现文件 | 已修正 |
| R-02 | 摘要使用旧 CEP p99 0.0495 ms | 当前 synthetic 改为 p50 0.0131、p95 0.0188、p99 0.0299 ms | 当前 synthetic JSON | 已修正 |
| R-03 | soak 使用旧 88 alerts、p95 1.718 s | 主要结果改为最近保存的 76 alerts、p95 1.616 s；88 保留为旧 run | `data/evaluation/kafka_db_soak.json` 和各 run 报告 | 已修正 |
| R-04 | 把 88 秒 IEX 写成真实业务稳定运行 | 改成短时真实输入工程验证，只支持接入、存储和三种 cadence | `data/evaluation/alpaca_live_e2e.json` | 已修正 |
| R-05 | `1.4826` 容易被写成无意义常数 | 明确它是正态一致性 MAD 缩放常数；不表示因子服从正态 | `processing/factor_engine.py`；ChatGPT baseline 日志 | 已修正 |
| R-06 | 主动买卖方向缺少边界 | 写明优先使用上游 side，否则用 midpoint；无 side 且无双边报价时不分类 | `processing/factor_state.py` | 已修正 |
| R-07 | 新闻情绪算法不清楚 | 写明正负词表、分数公式和 `log(1+n)`；明确不是 FinBERT | `producers/alpaca_producer.py` | 已修正 |
| R-08 | elevated/extreme 只有模糊描述 | 补充 signed 与 non-negative 因子的具体公式 | `processing/factor_engine.py` | 已修正 |
| R-09 | 把 0.995/0.999 当成可靠尾部概率 | 说明最多 20 样本时 nearest-rank 高分位通常等于最大值 | `processing/factor_state.py`；方法核查任务 | 已修正 |
| R-10 | baseline key 写成六维且持久化状态过时 | 区分五维 cell key 与 `session_date` observation；补充 epoch 和显式启动模式 | `baseline/`；persistence tests | 已修正 |
| R-11 | 原修订错误声称负对照与120 FP互不包含 | 本轮trace证实120=正场景60+负对照60；40是触发场景数，不能当告警条数 | SYN-TRACE-20261022逐场景明细 | 2026-10-22纠正，撤销旧解释 |
| R-12 | 20 个 seed 相同容易被写成稳定性 | 改成生成器结构确定性和脚本重复性，不代表真实市场稳定 | per-seed output | 已修正 |
| R-13 | activity ablation 未解释 | 明确 current rule completion 不依赖 relative volume | pattern definitions and JSON | 已修正 |
| R-14 | dislocation ablation 只强调 F1 提升 | 增加 TP 360→300、FP 120→0 和及时性/确认取舍 | current JSON | 已修正 |
| R-15 | 0.0033 ms 与当前 timing 容易混用 | 0.0033 标为旧兼容协议；0.0131/0.0299 标为当前六状态机 synthetic | 两组不同输出 | 已修正 |
| R-16 | 本机绝对图片路径 | 架构图改为相对路径；缺失的旧图片移除，以表格为准 | 路径扫描 | 已修正 |
| R-17 | Table 7 标题错误 | 从“首次检测延迟”改为“告警负担与重复率” | 当前表格内容 | 已修正 |
| R-18 | 日线数据被写成 intraday baseline 来源 | 改为覆盖检查与候选事件选择；正式 baseline 要用此前的微观事件 | replay protocol | 已修正 |
| R-19 | 文献表述过强 | 修正 NIST deployment、MEDOS trust、ViEWS accuracy、OFI 等说法 | `04_Literature_Verification_CN.md` | 已修正 |
| R-20 | 没有个人贡献与 AI 边界 | 增加 9.4 节；指向 AI Log Index 和贡献表 | AI logs、Git 和 tests | 已修正 |
| R-21 | 个人工作被笼统写成核查，缺少本人决策与 AI 执行的明确对应 | 新增中英文五列表 D01–D10 与原行号摘录；同步中英文贡献、报告、代码来源和提交副本，突出本人决策及具体约束，保留 AI 实施来源与未确认手写范围 | `08_Contribution_Attribution_Matrix_CN.md`、英文版和 `Evidence_Attachments/Decision_Log_Excerpts.md` | 2026-10-22 已修订 |

## 当前报告中的结果分层

| 结果 | 分类 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 63 tests + Ruff（CHECKS-20261022） | 本轮归档工作树 | 当前测试和静态检查通过；62是9月17日记录 | 生产可靠性 |
| F1 0.857 | 受控生成验证 | 预设规则可被当前实现检测 | 真实市场 F1 |
| 40/240 negative controls | 受控生成验证 | extreme 单因子通道有误警风险 | 正常市场实际误警率 |
| 旧 CEP F1 0.785 vs ML 0.639 | 旧版本人工注入 | 旧协议内的比较 | 当前方法真实优越性 |
| 76 alerts, p95 1.616 s | 历史受控 soak | 保存的链路 run 通过 gate | 当前环境或生产长期稳定性 |
| 48,734 IEX events | 历史真实输入工程验证 | 接入、存储和 cadence 生成 | 检测准确率 |
| real replay metrics | 尚未完成 | 无 | 标签未冻结前不得报告 |

## 尚待补充

1. 真实标签冻结后，在同一协议下重跑 CEP 和 ML。
2. Docker/Kafka/PostgreSQL 环境恢复后重跑 current soak。
3. 若重新生成图表，只允许从已索引 JSON 生成，并保存脚本和相对路径。
4. 收到 ChatGPT 官方导出后补充日志索引。
5. 导师确认格式后，再决定是否转换为 PDF 或 DOCX。

## 本轮交付定位

- [中文五列交付表](08_Contribution_Attribution_Matrix_CN.md)与[英文版](08_Contribution_Attribution_Matrix_EN.md)。
- [原日志摘录](Evidence_Attachments/Decision_Log_Excerpts.md)与[归属核验结果](Evidence_Attachments/Attribution_Validation_20261022.md)。
- 本轮同步当前 Markdown 源文件及代码来源注释；`report/MarketStream项目描述.zip` 保留为历史提交快照，没有重打包或改写其中旧导出的 Word 文件。


## 核心贡献表述完善

按作者后续要求，将叙述中心进一步统一为“本人主导核心方案与开发推进，AI 辅助开发”。新增中英文 `09_Core_Contribution_Statement`，在项目证据链开头概括本人主导内容，将五列表各项标题及贡献记录字段改为明确的个人核心贡献表述，并同步报告、代码来源说明与提交副本。具体技术建议、AI 代码／文字生成来源和未确认项继续按原始证据披露；没有修改历史日志或实验数值。

## 2026-10-22 数字与结论重新核验（覆盖旧结果口径）

| ID | 核验发现 | 处理与依据 |
|---|---|---|
| R-22 | 原R-11解释与detections.extend的总体口径冲突 | 撤销“互不包含”；120 FP=正场景60+负对照60；40/240统计触发场景。保留600场景的逐条truth与检测 |
| R-23 | “当前”混用了9月17日计时、旧注入均值和历史soak | 本轮trace计时0.0150/0.0306/0.0688 ms；独立suite另列；旧0.0033与0.0299均仅历史。主稿删除p99低于0.03 ms的结论 |
| R-24 | 76告警run的p50/p99抄错 | 按soak-b735cff438原文件改为1.476217/1.727292 s，p95保持1.615935 s |
| R-25 | 62/160被写成当前测试 | 本轮新增计数回归后63 passed，Ruff通过；历史数字不合并 |
| R-26 | 零重复、退化CI和告警负担解释过强 | cooldown=0且场景人工分隔；bootstrap固定FP；1.604分母含人为间隔。删除生产冷却／真实稳定性推论 |
| R-27 | 真实回放状态只检查draft | 检查draft及3份AI预标注，均frozen=false；无正式结果，不把AI标注当独立批准 |
| R-28 | 历史run缺完整版本和输入绑定 | 七字段台账逐项标缺失；保存工件hash，不虚构历史执行hash或run ID |
| R-29 | 主稿不唯一、贡献文档复述旧口径 | 确定中文修订稿唯一主稿；英文对应译稿；统一贡献材料的运行证据与边界，给旧稿／提交副本加历史声明 |

本轮运行源码及测试快照、逐场景输出、suite消融、检查原文和机器清单位于`reproduction_outputs/audit_20261022/`。真实标签冻结、历史缺失原始行与执行快照仍是缺口，未伪造补齐。9月17日Docker阻塞只作为当时记录，本轮没有重跑基础设施。

## 2026-10-23 规则修订、评测协议与数据语义更新

| ID | 发现 | 处理与依据 |
|---|---|---|
| R-30 | 暖机期 `return_surprise` 被放大约 10^6 并写入自身历史，阈值约 20 个交易日失效 | 原始收益历史满五日前不计值、不写入；约第 11 日 ready；基线算法版本升级（现为 `rolling-mad-v4`） |
| R-31 | CEP 与 IF 计分范围和后处理不同 | 两者只对被审阅标的计分；IF 只用暖机后快照拟合；共用告警策略（质量/暖机门 + ticker/方向 300 秒冷却）；保留逐窗口原始输出与原始指标 |
| R-32 | 单因子极端价格例外是全部生成误警来源；旧稿误把删除整个模式的召回损失归因于该例外 | 真实回放前按预先声明删除例外；生成结果改报 SYN-*-20261023，并注明修订后为样本内检查 |
| R-33 | 分钟线按区间起点归属，回放中提前使用整分钟价格，live 与回放不一致 | bar 以完成时间为事件时间，payload 保存区间，窗口只用区间完全落入的 bar；转换器 v2 |
| R-34 | 零 MAD 时收益尺度退化为 1e-6 | 预先声明的平均绝对偏差回退 + 一跳下限；敏感性检验 ZMAD-20261023，C2 不通过如实报告 |
| R-35 | 真实区间缺少客观标注准则 | 新增并批准 `docs/LABELING_CRITERIA.md`（基于 SIP 数据，volume option 2）与盲审工具；报告 6.7 补充 |
| R-36 | 计时与测试数随代码更新 | CHECKS-20261023（91 passed）与 SYN-TRACE-20261023 计时 0.0132/0.0178/0.0259 ms 替换旧当前值 |

| R-37 | 报告把项目计划第 4 项写成“唯一一次／只允许一次”规则修订，超出原文 | 改为准确引用第 4 项“依据负对照误报做一次预先声明的规则改动”（`docs/PROJECT_PLAN.md`，提交 `e87d19f`）；写明冻结前的修改须有理由、有记录、只用与评测区间不重叠的数据且不使用评测区间检测器输出，冻结后参数固定、后续修改须新版本并在独立保留集验证。检测器实现与评测协议未改动 |
