# MarketStream 实验核对与复现记录（2026-10-22）

唯一主稿：[07_Revised_Report_CN.md](07_Revised_Report_CN.md)。完整七字段运行记录、原始输出和缺失项统一见[数字—运行—结论台账](Evidence_Attachments/Result_Run_Ledger_20261022.md)及[机器清单](reproduction_outputs/audit_20261022/result_registry.json)。本记录取代2026-09-17把保存结果称为“当前”的口径。

| 证据层 | 运行／工件 ID | 本轮可支持的结论 |
|---|---|---|
| 代码检查 | CHECKS-20261022 | 63 passed in 4.67s；Ruff通过。62是9月17日摘要，160是未完整绑定的旧材料 |
| 合成规则验证 | SYN-TRACE-20261022 | TP/FP/FN=360/120/0；Precision/Recall/F1=0.750/1.000/0.857；计时p50/p95/p99=0.0150/0.0306/0.0688 ms |
| 独立合成消融 pass | SYN-SUITE-20261022 | 删除dislocation：300/0/60；activity删除无变化；不与trace pass混用计时 |
| 旧版注入比较 | LEGACY-INJECTED（索引ID，原run ID缺失） | 仅保存的旧协议汇总：CEP F1 0.7846、ML F1 0.6392；完整执行快照缺失 |
| Kafka／数据库 | 三个soak原run ID | 15/88/76告警分别绑定各自run，最近保存run的p95=1.615935 s；未在本轮复跑 |
| 短时真实输入 | alpaca-live-20260819T144908Z | 48,734事件、约88.289秒；warm-up，无标签，仅工程验证 |
| 正式真实回放 | 无run ID／无结果 | 4个标签文件均未冻结；禁止真实效果指标 |

## 计数关系更正

120 条 FP = 正场景的 60 条未匹配告警 + 负对照的 60 条告警；40/240 是触发场景数／负对照场景数，其中 40 个触发场景发出 60 条告警，已包含在总 FP 中。

明细：[scenarios.json](reproduction_outputs/audit_20261022/scenarios.json) 与 [reconciliation.json](reproduction_outputs/audit_20261022/reconciliation.json)。正场景420告警、负对照60告警，合计480；负对照不是总FP之外的第二组错误。旧汇总JSON不足以证明旧运行的逐条归属，精确分解只主张本轮有快照的复跑。

## 复现及原始输出

项目根目录执行 `.venv/bin/python -m report.tools.audit_results`；这会更新audit_20261022输出目录，如需比较应先复制保存。脚本先归档源文件，再执行trace与suite两次pass，并核对全局匹配和逐场景匹配一致。代码、测试及依赖锁文件的hash见[provenance.json](reproduction_outputs/audit_20261022/provenance.json)，归档见[source_snapshot.tar.gz](reproduction_outputs/audit_20261022/source_snapshot.tar.gz)。HEAD本身不代表未提交工作树。

检查命令为 `.venv/bin/pytest -q` 和 `.venv/bin/ruff check .`，原始文本输出位于同目录。旧测试摘要保留于[Test_Outputs.md](Evidence_Attachments/Test_Outputs.md)，不能复用为当前结果。

## 解释边界

合成输入直接构造因子状态，只验证预设规则。1.604 alerts/ticker-hour包含人为十分钟场景间隔；cooldown=0和零重复不证明生产冷却。bootstrap重采样truth命中且固定FP，不能估计真实正常期误警不确定性。不同pass及历史计时分别保留。历史soak、注入比较和IEX缺准确执行快照及部分逐条输入／输出，均降为保存的历史汇总；本轮未宣称恢复服务或完成正式真实回放。
