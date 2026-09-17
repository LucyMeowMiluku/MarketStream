# MarketStream

MarketStream 是一个实时、可解释的市场异常检测原型。当前项目只有一条在线主链：

```text
Alpaca / Replay
→ MarketEvent
→ EventQualityGate
→ LightweightFactorEngine（8 factors，10s / 1m / 5m）
→ CEPDetector（6 explicit state machines）
→ DetectionResult
→ TimescaleDB / Dashboard / Evaluation
```

Isolation Forest 只作为离线对比基线，直接读取同一批 `FactorSnapshot`，不拥有第二套特征工程或在线进程。

## 核心数据合同

- `MarketEvent`：trade、quote、bar、news 四种事件的统一输入。
- `FactorSnapshot`：八个因子、历史状态、数据质量和原始事件引用。
- `DetectionResult`：完成/等待中的CEP模式、方向、证据、严重度和dedupe key。

## 八因子

`return_surprise`、`volatility_burst`、`relative_volume`、`spread_stress`、
`quote_imbalance`、`signed_trade_imbalance`、`market_residual`、`news_shock`。

## 六类CEP模式

`stock_specific_dislocation`、`liquidity_pressure_move`、
`news_confirmed_move`、`flash_reversal`、`sustained_pressure`、
`cross_asset_shock`。

每种模式由一个小型显式状态机实现。通用NFA、negation、repeat和meta-pattern不再属于项目范围。

## 运行

环境要求：Python 3.12、Docker、Alpaca凭据（只有live模式需要）。

```bash
uv sync
docker-compose up -d
bash scripts/create_topics.sh
uv run python -m storage.init_db
```

Replay主演示：

```bash
MARKETSTREAM_SOURCE=replay \
MARKETSTREAM_REPLAY_PATH=/absolute/path/events.jsonl \
bash scripts/start_all.sh
```

实时链路验证：

```bash
export FACTOR_BASELINE_STARTUP_MODE=COLD_START
export FACTOR_ENGINE_VERSION=marketstream-0.1.0
export FACTOR_CHECKPOINT_DIR=/absolute/persistent/baseline-checkpoints
bash scripts/start_all.sh
```

live Factor Engine 不会猜测 baseline 启动方式。首次上线使用 `COLD_START`；
后续重启必须显式使用 `RESTORE` 并提供 `FACTOR_BASELINE_EPOCH_ID`；只有具备
独立 manifest 和 checksum 的 Alpaca 原始数据才允许使用 `VERIFIED_BACKFILL`。
三种模式、epoch registry、20 日保留和 checkpoint 恢复规则见
[Baseline 持久化说明](docs/BASELINE_PERSISTENCE.md)。普通 Kafka replay 使用独立的
临时 Factor Engine，不读取或修改 live baseline epoch。

受控合成实验：

```bash
uv run python -m evaluation.run_synthetic
```

正式真实回放：

```bash
bash scripts/run_component.sh evaluate-reviewed-replay \
  --dataset-manifest /absolute/path/manifest.json \
  --labels /absolute/path/frozen-labels.json
```

正式回放会输出 `metrics.json`、`trace.jsonl`、`replay_report.html` 和
`detector_comparison.json`。标签未独立审阅并冻结时，评测器拒绝运行。

## 验证

```bash
uv run pytest -q
uv run ruff check .
```

测试覆盖核心合同、质量边界、八因子、baseline epoch/恢复、六类状态机、live/replay一致性、
Isolation Forest训练隔离、标签冻结、checksum和严格向前一对一事件匹配。

## 证据边界

- 单元测试证明代码符合已声明行为，不证明真实市场效果。
- 合成实验用于验证规则、负对照和评测链路。
- Alpaca live用于证明真实输入能够通过工程链路。
- 只有冻结标签上的reviewed replay才有资格报告真实市场Precision、Recall和F1。

中文源码阅读与答辩练习见 [核心导学](docs/CORE_WALKTHROUGH_CN.md)。
