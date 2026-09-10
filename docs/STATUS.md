# MarketStream — 当前状态

**最后更新：2026-08-06**  
**当前主线：统一事件 → 八个轻量因子 → 六类 CEP → 可追溯告警**

## 一句话结论

底层优先重构已经落地，旧四模型仅保留为离线基线或可选 shadow。12 个月历史数据、Kafka→数据库 p95 soak，以及 Alpaca IEX 真实事件端到端落库门槛均已通过。

## 已通过

- `MarketEvent`、`FactorSnapshot`、`DetectionResult` 三个稳定合同。
- 重复、乱序、过期、零量、无效价格、跨价报价和断流质量标记。
- 10 秒、1 分钟、5 分钟八因子增量计算，按 ticker/session/日内位置做 median/MAD/quantile 基线。
- 五日暖机、阈值冻结导入导出、有界 ticker/窗口/CEP 状态。
- 六类方向性 CEP、冷却合并、人类可读证据与原始事件追踪。
- live/replay 共用 Kafka 与检测链路；五分钟兼容旧图表和 ML 回测。
- 事件级一对一向前匹配、20 seed × 3 强度、负对照和消融。
- 12 个月数据：五标的 OHLCV 1,380 行、新闻 6,418 条，覆盖 397–400 天，固定 60/20/20 切分。证据见 `data/historical/manifest.json`。
- Alpaca 官方历史版本：OHLCV 1,385 行、Benzinga 新闻 15,148 条，五标的均覆盖 400 天。证据见 `data/historical/alpaca/manifest.json`。
- Alpaca IEX 实流：五标的 48,734 条事件全部经 Kafka 落库，包括 quote 48,283、trade 446、bar 5；同时生成 40 个 10 秒、5 个 1 分钟和 5 个 5 分钟快照。证据见 `data/evaluation/alpaca_live_e2e.json`。
- Kafka→数据库 soak：240/240 事件持久化，88 个可追踪告警，p50 1.418s、p95 1.718s、p99 1.738s，重复为 0。证据见 `data/evaluation/kafka_db_soak.json`。
- 第一次 soak 因告警样本仅 15 条未通过，失败报告仍保留在 `data/evaluation/soak-61164fa173/report.json`。

## Alpaca 实流复验结论

真实 Alpaca IEX 股票流与新闻流复验命令：

```bash
export ALPACA_API_KEY="..."
export ALPACA_API_SECRET="..."
uv run python -m producers.alpaca_smoke
```

凭据可用，股票流与新闻流认证及订阅成功。2026-08-19 的活跃时段复验已收到并持久化真实 IEX `trade/quote/bar`，严格 gate 与端到端 gate 均为 true。IEX 覆盖仍明确标注为单交易所数据，不冒充 SIP。

实流发现旧 stale 规则会误判正常 minute bar，因为 bar 时间戳表示窗口起点。修复后为 bar 增加 60 秒窗口结束宽限；复验中的 5 条 bar 全部为非 stale，相关回归测试已加入。

## 数据口径说明

公开版本仍使用预先固定的逐月 Google News RSS 查询窗口，并记录被 100 条 RSS 上限截断的窗口。凭据到位后已另行生成 Alpaca/Benzinga 版本，两个数据集都保留，不覆盖来源差异。

## 关键复验命令

```bash
uv run python -m scripts.collect_historical_dataset
uv run python -m scripts.run_backend_soak
uv run python -m producers.alpaca_smoke
uv run python -m ml.evaluate_factor_cep
uv run pytest -q
uv run ruff check .
```

前端仍只承担兼容和调试。等 Alpaca 真流及后端接口最终冻结后，再围绕 Live Overview、Alert Investigation、Research Evaluation、System Health 单独重构。
