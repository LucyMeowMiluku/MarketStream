# MarketStream 当前状态

最后更新：2026-09-10

## 已完成

- 单一主链：MarketEvent → Quality Gate → 8 Factors → 6 CEP State Machines。
- 10秒、1分钟、5分钟三种cadence及冻结Median/MAD baseline。
- Replay与live复用相同事件、因子和CEP合同。
- 单一Isolation Forest离线基线，使用同一FactorSnapshot和事件级指标。
- 正式Replay输出trace、metrics、HTML和CEP/IF比较工件。
- 旧四模型ensemble、ML shadow、通用NFA和旧feature链已从当前分支移除。
- live baseline observations、runtime state 和 Kafka offsets 已按 epoch 持久化；
  启动必须显式选择 COLD_START、VERIFIED_BACKFILL 或 RESTORE。
- 每个 baseline cell 同日覆盖并只保留最近 20 个交易日；每日 checkpoint 使用
  Parquet + JSON manifest/checksum，状态损坏时可回退最近完整 revision。

## 尚未完成

- 24个真实标签仍需独立审阅并冻结。
- 冻结标签上的真实Precision、Recall和F1尚不可报告。
- Live只完成工程链路验证，不代表市场检测准确率。

旧实现保存在Git分支 `codex/pre-simplification-snapshot`。
