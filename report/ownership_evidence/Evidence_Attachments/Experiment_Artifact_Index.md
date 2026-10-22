> 2026-10-22：本索引中的旧 CURRENT/LATEST 名称仅为历史工件ID，不表示本轮版本。完整运行字段与缺失依据见[运行台账](Result_Run_Ledger_20261022.md)及[机器清单](../reproduction_outputs/audit_20261022/result_registry.json)。新合成结果使用SYN-TRACE-20261022，消融使用SYN-SUITE-20261022。

# 实验原始工件索引

| ID | 工件 | 数据性质 | 当前用途 | 主要限制 |
|---|---|---|---|---|
| EXP-CURRENT-SYNTH | `../reproduction_outputs/factor_cep_current_20260917.json` | synthetic factor sequences | 9月17日保存的规则、负对照、消融和计时 | 不能代表真实市场 |
| EXP-OLD-SYNTH | `../../../data/evaluation/factor_cep.json` | synthetic factor sequences | 与旧报告对照 | 计时受运行环境影响 |
| EXP-SOAK-LATEST | `../../../data/evaluation/kafka_db_soak.json` | synthetic transport probe | 最近保存的历史Kafka→DB汇总；非本轮复跑 | 不是检测准确率 |
| EXP-SOAK-FAIL | `../../../data/evaluation/soak-61164fa173/report.json` | synthetic transport probe | 保留失败—修改—复验记录 | 告警样本不足 |
| EXP-SOAK-88 | `../../../data/evaluation/soak-702644010d/report.json` | synthetic transport probe | 旧 88-alert run | 不是最新 run |
| EXP-SOAK-76 | `../../../data/evaluation/soak-b735cff438/report.json` | synthetic transport probe | 最近 76-alert run | 未在本轮重跑 |
| EXP-IEX-LIVE | `../../../data/evaluation/alpaca_live_e2e.json` | real live IEX input | 真实接入与 factor 链验证 | 88 秒、warm-up、无标签 |
| EXP-ML-LEGACY | `../../../data/comparison_results_nfa_tuned/comparison_60d_0.05.json` | real OHLCV + injected anomalies | 历史方向选择和旧协议对比 | 不是当前规则，也不是真实 ground truth |
| EXP-CASE | `../../../data/comparison_results/event_case_study.json` | real daily OHLCV, placeholder sentiment | 定性案例 | 无完整标签，不能算指标 |
| EXP-LABEL-DRAFT | `../../../data/replay/labels/iex_benchmark_v1.draft.json` | proposed real intervals | 后续独立审阅 | 未冻结，禁止正式指标 |

## 结果使用原则

- 主文引用数字时同时写明 artifact ID 和数据性质。
- 同一表格不混合 current-version timing 与 legacy timing，除非明确分列。
- 任何 real-market Precision、Recall、F1 必须来自冻结标签和对应 manifest/hash。
- 实验文件缺少生成脚本或当前代码无法重跑时，标为 historical，不写成 current result。

