# Live Baseline 持久化与启动模式

live Factor Engine 的 baseline 是 PostgreSQL 中的版本化状态，不从 Kafka 或旧聚合表
自动推断。部署必须设置以下公共参数：

```bash
FACTOR_BASELINE_STARTUP_MODE=COLD_START|VERIFIED_BACKFILL|RESTORE
FACTOR_ENGINE_VERSION=marketstream-0.1.0
FACTOR_CHECKPOINT_DIR=/absolute/path/on/a/persistent-volume
```

`FACTOR_CHECKPOINT_DIR` 必须是绝对路径，并应与 PostgreSQL 数据卷位于不同故障域。

## COLD_START

首次上线时 registry 和所有 baseline 子表必须为空：

```bash
FACTOR_BASELINE_STARTUP_MODE=COLD_START
```

协调器创建新的 ACTIVE epoch，并以创建时间作为 activation cutoff。只有 cutoff 之后的
live 事件会进入该 epoch。每个 cell 独立累计历史；当前窗口不会参与自身评分，八个输出
因子都拥有至少五个严格在先交易日后，snapshot 才是 `ready`。`return_surprise` 是对原始
收益的二阶标准化：原始收益历史不足五日时其 robust scale 尚未建立，该因子不计值、不写入
自身 baseline，因此它在第 6 个交易日开始积累，约第 11 个交易日才 `ready`。
`rolling-mad-v3` 起采用此规则；v2 epoch 的 baseline 含暖机期放大值，需重新 COLD_START。

若旧 epoch 已变成 CORRUPT 且没有可信历史，可显式创建恢复型 cold start：

```bash
FACTOR_BASELINE_STARTUP_MODE=COLD_START
FACTOR_BASELINE_REPLACES_EPOCH_ID=<corrupt-epoch-uuid>
FACTOR_BASELINE_RECOVERY_REASON="checkpoint and raw history unavailable"
```

这会创建新 epoch；不会在旧 epoch 中伪造或静默修补状态。

## RESTORE

普通重启必须指定准确 epoch 和算法版本：

```bash
FACTOR_BASELINE_STARTUP_MODE=RESTORE
FACTOR_BASELINE_EPOCH_ID=<active-epoch-uuid>
FACTOR_BASELINE_ALGORITHM_VERSION=rolling-mad-v3
```

协调器在订阅 Kafka 前核对 registry、配置 hash、factor schema hash、行数、逐行 checksum、
runtime 和 offsets。当前 DB 状态损坏时，会按 revision 倒序检查 COMMITTED checkpoint；
完整 checkpoint 被原子恢复后再从其 offset 重放。没有有效 checkpoint 时 epoch 会进入
CORRUPT，进程拒绝消费。

## VERIFIED_BACKFILL

此模式只接受专用 `marketstream-baseline-backfill-v1` manifest：

```bash
FACTOR_BASELINE_STARTUP_MODE=VERIFIED_BACKFILL
FACTOR_BASELINE_MANIFEST=/absolute/path/manifest.json
FACTOR_BASELINE_MANIFEST_SHA256=<sha256>
FACTOR_BASELINE_ACTIVATION_CUTOFF=2026-09-11T13:00:00+00:00
```

manifest 最小结构：

```json
{
  "schema_version": "marketstream-baseline-backfill-v1",
  "provider": "alpaca",
  "source": "alpaca",
  "collection_version": "collector-v1",
  "engine_version": "marketstream-0.1.0",
  "activation_cutoff": "2026-09-11T13:00:00+00:00",
  "provenance": {"phase": "baseline_backfill"},
  "event_count": 1000,
  "time_range": {
    "start": "2026-08-01T13:30:00+00:00",
    "end": "2026-09-10T20:00:00+00:00"
  },
  "artifacts": [{
    "path": "events.jsonl",
    "sha256": "<sha256>",
    "events": 1000,
    "feeds": ["iex", "benzinga_news"],
    "event_types": ["trade", "quote", "bar", "news"]
  }]
}
```

每条 JSONL 事件必须是标准 `MarketEvent`，满足 `source=alpaca`、
`mode=verified_backfill` 和 `provenance.phase=baseline_backfill`，并严格早于 cutoff。
synthetic、soak、普通 replay 和 formal evaluation 输入会被拒绝。协调器使用当前代码离线
重算，生成初始 checkpoint 后才激活 epoch；回填 snapshot 不发送到实时 CEP。

## 持久化与 checkpoint

- baseline 业务键是 `(ticker, cadence, market_session, intraday_slot, factor_name,
  session_date)`，物理主键在前面增加 `epoch_id`。
- 同一 cell/date 使用 upsert 覆盖；事务内删除该 cell 日期排名超过 20 的记录。
- event、snapshot、baseline、runtime、registry revision 和 DB offset 使用一个后台事务。
- FactorSnapshot Kafka 发送与 DB 事务都成功后才提交 consumer offset。
- DB 故障时 writer 重试；队列满后暂停 Kafka partitions，恢复至半容量后继续。
- regular session 结束后生成 `baseline.parquet`、`runtime.json`、`offsets.json` 和
  `manifest.json`，默认保留最近七个校验通过的 checkpoint。
