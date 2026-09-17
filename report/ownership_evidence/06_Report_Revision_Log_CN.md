# MarketStream 报告修订记录

原始文件：`report/report draft.md`  
修订中文稿：`07_Revised_Report_CN.md`  
修订英文稿：`07_Revised_Report_EN.md`  
修订日期：2026-09-17

## 修订原则

- 原始报告不覆盖。
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
| R-11 | 360/480/120 与 40/240 关系不清楚 | 写明 120 是正场景额外未匹配告警，40/240 是独立负对照 | 当前 synthetic JSON | 已修正 |
| R-12 | 20 个 seed 相同容易被写成稳定性 | 改成生成器结构确定性和脚本重复性，不代表真实市场稳定 | per-seed output | 已修正 |
| R-13 | activity ablation 未解释 | 明确 current rule completion 不依赖 relative volume | pattern definitions and JSON | 已修正 |
| R-14 | dislocation ablation 只强调 F1 提升 | 增加 TP 360→300、FP 120→0 和及时性/确认取舍 | current JSON | 已修正 |
| R-15 | 0.0033 ms 与当前 timing 容易混用 | 0.0033 标为旧兼容协议；0.0131/0.0299 标为当前六状态机 synthetic | 两组不同输出 | 已修正 |
| R-16 | 本机绝对图片路径 | 架构图改为相对路径；缺失的旧图片移除，以表格为准 | 路径扫描 | 已修正 |
| R-17 | Table 7 标题错误 | 从“首次检测延迟”改为“告警负担与重复率” | 当前表格内容 | 已修正 |
| R-18 | 日线数据被写成 intraday baseline 来源 | 改为覆盖检查与候选事件选择；正式 baseline 要用此前的微观事件 | replay protocol | 已修正 |
| R-19 | 文献表述过强 | 修正 NIST deployment、MEDOS trust、ViEWS accuracy、OFI 等说法 | `04_Literature_Verification_CN.md` | 已修正 |
| R-20 | 没有个人贡献与 AI 边界 | 增加 9.4 节；指向 AI Log Index 和贡献表 | AI logs、Git 和 tests | 已修正 |

## 当前报告中的结果分层

| 结果 | 分类 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 62 tests + Ruff | 当前版本实测 | 当前测试和静态检查通过 | 生产可靠性 |
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
