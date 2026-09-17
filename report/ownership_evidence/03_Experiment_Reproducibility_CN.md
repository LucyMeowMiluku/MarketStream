# MarketStream 实验核对与复现记录

## 1. 复现环境

| 项目 | 值 |
|---|---|
| 日期 | 2026-09-17 |
| 分支 | `codex/core-simplification` |
| 基准提交 | `bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd` |
| Python | 3.12.10（来自 pytest 输出） |
| 依赖入口 | `uv.lock`、`pyproject.toml` |
| 当前工作树 | 大规模 core simplification 和 baseline persistence 尚未形成最终快照提交 |

当前工作树不是 clean checkout。因此，本文同时记录 base commit 和最终待补的 evidence snapshot。所有本轮输出放在 `reproduction_outputs/`，避免覆盖原始实验文件。

## 2. 当前测试与静态检查

### 命令

```bash
uv run pytest -q
uv run ruff check .
```

### 输出

- 62 collected，62 passed，4.85 秒；
- Ruff：`All checks passed!`。

### 能证明什么

当前代码满足现有 62 项测试约定，且通过 Ruff 静态检查。

### 不能证明什么

不能证明生产可靠性、测试覆盖完整性或真实市场有效性。旧材料中的 160 passed 属于简化前版本，不能作为当前测试数。

## 3. 当前 generated factor CEP protocol

### 命令

```bash
uv run python -m evaluation.run_synthetic \
  --seeds 20 \
  --output report/ownership_evidence/reproduction_outputs/factor_cep_current_20260917.json
```

### 数据与参数

- 数据类型：`synthetic`；
- ground truth：`generated_factor_sequences`；
- 用途：`pipeline_validation_only`；
- 20 个 seed；
- 三档 intensity：low、medium、high；
- 六类正场景；
- 四类 negative control；
- synthetic evaluator 内部将 cooldown 设为 0，避免 cooldown 影响场景计数。

正场景数量：

```text
20 seeds × 3 intensities × 6 patterns = 360 truth events
```

负对照数量：

```text
20 seeds × 3 intensities × 4 negative-control types = 240 cases
```

### 本轮结果

| 指标 | 结果 |
|---|---:|
| TP | 360 |
| FP | 120 |
| FN | 0 |
| Alerts | 480 |
| Precision | 0.750 |
| Recall | 1.000 |
| F1 | 0.857 |
| Detection delay p50 | 10 s |
| Detection delay p95/p99 | 30 s |
| CEP compute p50 | 0.013083 ms |
| CEP compute p95 | 0.018752 ms |
| CEP compute p99 | 0.029878 ms |
| Alerts per ticker-hour | 1.604 |
| Duplicate alert rate | 0 |

计算检查：

```text
Precision = 360 / (360 + 120) = 0.75
Recall = 360 / (360 + 0) = 1.00
F1 = 2 × 0.75 × 1.00 / (0.75 + 1.00) = 0.8571
```

### 120 FP 与 40/240 的关系

这两个数字来自不同输入集合，不能当成同一批告警。

- 120 FP：六类正异常场景中，系统除了匹配预设 pattern 外，还产生了额外 pattern 告警。这些告警没有与对应 truth 做一对一匹配。
- 40/240：单独生成的 240 个负对照场景中，有 40 个场景至少触发一条正式告警。

它们都说明规则会产生额外告警，但 40 不是 120 的子集。

### 为什么 20 个 seed 得到相同指标

seed 会改变生成场景中的数值扰动，但场景结构、状态标签和阈值跨越关系是固定设计的。每个 seed 中，同一 pattern 仍然跨过相同的 elevated/extreme 边界，所以每个 seed 的 TP/FP/FN 结构相同。bootstrap 只是对这些结构相同的场景重复抽样，因此区间退化成一个点。

这说明 generator 对 seed 不敏感，不说明真实市场结果没有不确定性。报告不应把退化置信区间写成系统“非常稳定”。

## 4. 负对照和消融

### 负对照

| 指标 | 结果 |
|---|---:|
| Cases | 240 |
| Alerting cases | 40 |
| False-alert rate | 16.7% |

### 删除 stock-specific dislocation

| 设置 | Precision | Recall | F1 | TP | FP | FN | 负对照告警 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 完整方法 | 0.750 | 1.000 | 0.857 | 360 | 120 | 0 | 40/240 |
| 删除该模式 | 1.000 | 0.833 | 0.909 | 300 | 0 | 60 | 0/240 |

原因：该模式允许 extreme `return_surprise` 在缺少第二项证据时直接完成。删除后，极端单因子负对照不再告警，但六类 truth 中属于该模式的 60 个事件也全部漏掉。

这不是“删除后一定更好”。它反映两种风险之间的取舍：立即提示极端价格，或等待市场残差、流动性、新闻等第二项证据。

### 删除 activity

结果与完整方法完全相同。当前 `relative_volume` 属于 activity 组，但六个状态机没有把它作为完成条件。因此，删除该组不会改变结果。这个负面结果说明“因子有金融意义”不等于“规则库实际使用了它”。

## 5. 旧 CEP 与 ML 对比

原始文件：`data/comparison_results_nfa_tuned/comparison_60d_0.05.json`。

| 项目 | 说明 |
|---|---|
| 数据 | 60 天真实 5 分钟 OHLCV，加人工注入异常和合成情绪 |
| Ticker | AAPL、TSLA、NVDA |
| Split | train ratio 0.7 |
| Injection rate | 0.05 |
| Seed | 42 |
| Test windows | 4,209 |
| Ground truth | 225 个程序化注入异常 |

| 方法 | Precision | Recall | F1 | Mean compute |
|---|---:|---:|---:|---:|
| 四模型 ensemble | 0.5719 | 0.7244 | 0.6392 | 4.5135 ms |
| 旧 CEP full | 0.7541 | 0.8178 | 0.7846 | 0.0033 ms |

### 解释边界

该结果只能说明旧共同协议中的计算和匹配差异。它不是当前八因子和六状态机的公平真实市场对比。旧对比代码已从当前简化分支删除，当前工作树不能直接重新生成该 JSON。文件必须标记为 historical controlled comparison。

`0.0033 ms` 属于旧五分钟比较实现。本轮 current synthetic suite 的 p50 是 0.0131 ms。两者使用的实现、输入和计时协议不同，不能合并成同一个速度结论。

## 6. Kafka 到数据库 soak

### 运行记录

| Run | 日期 | 输入/持久化 | 告警 | p95 | Gate |
|---|---|---:|---:|---:|---|
| `soak-61164fa173` | 2026-08-06 | 150/150 | 15 | 1.484 s | Failed：告警样本不足 |
| `soak-702644010d` | 2026-08-06 | 240/240 | 88 | 1.718 s | Passed |
| `soak-b735cff438` | 2026-09-10 | 240/240 | 76 | 1.616 s | Passed |

最近一次可用结果是 76 alerts。88-alert 结果是较早的历史运行，不应继续作为“当前最新结果”。两次 run 的告警数量不同，说明实现或运行状态变化会影响输出，也说明报告必须绑定 run ID。

### 本轮复跑状态

计划命令：

```bash
uv run python -m scripts.run_backend_soak \
  --output report/ownership_evidence/reproduction_outputs/kafka_db_soak_current_20260917.json
```

实际阻塞：`docker compose` 子命令不可用；`docker-compose ps` 又无法连接 `/Users/.../.colima/default/docker.sock`。因此本轮没有启动 Kafka/PostgreSQL，也没有生成新的 soak 数字。

### 能证明什么

历史 synthetic transport probe 能进入 Kafka、factor、CEP 和 PostgreSQL；对应 run 中事件全部落库、没有 dedupe 重复，告警可以追溯。

### 不能证明什么

不能证明真实市场准确率、生产 SLA 或长期稳定性。

## 7. Alpaca IEX 实流

原始文件：`data/evaluation/alpaca_live_e2e.json`。

| 项目 | 结果 |
|---|---:|
| 时间范围 | 2026-08-19 14:49:10Z 至 14:50:38Z，约 88 秒 |
| 总事件 | 48,734 |
| Quote | 48,283 |
| Trade | 446 |
| Minute bar | 5 |
| Ticker | 5 |
| 10s snapshots | 40 |
| 1m snapshots | 5 |
| 5m snapshots | 5 |
| Stale bar | 0 |

该实验是 `real_live_soak`，但 `metric_eligible=false`。它证明 IEX WebSocket、事件转换、Kafka、存储和因子快照可以在真实输入上运行。由于运行仍处于 warm-up，且没有冻结 ground truth，它不能计算或证明 real-market Precision、Recall、F1。

IEX 只覆盖一个交易场所。quote、trade imbalance 和流动性因子不能外推为 consolidated SIP 全市场状态。

## 8. 正式真实 replay

当前标签：`data/replay/labels/iex_benchmark_v1.draft.json`。

当前状态：未冻结。正式 evaluator 要求：

- 12 个异常和 12 个正常区间全部独立批准；
- manifest 标记 `real_historical`、provider=alpaca、feed=iex；
- labels hash 与 dataset manifest 一致；
- baseline 严格早于 evaluation；
- evaluation 阶段 baseline hash 不变化；
- 所有快照结束 warm-up；
- 不含 synthetic 或 soak 来源。

因此，本次材料不报告真实历史 Precision、Recall、F1。拒绝输出是评测设计的一部分，不是实验成功。

## 9. 原始输出索引

- 本轮 synthetic：`reproduction_outputs/factor_cep_current_20260917.json`；
- 旧 synthetic：`../../data/evaluation/factor_cep.json`；
- 最近 soak：`../../data/evaluation/kafka_db_soak.json`；
- 三次 soak：`../../data/evaluation/soak-*/report.json`；
- IEX 实流：`../../data/evaluation/alpaca_live_e2e.json`；
- 旧 ML 对比：`../../data/comparison_results_nfa_tuned/comparison_60d_0.05.json`；
- 标签草稿：`../../data/replay/labels/iex_benchmark_v1.draft.json`。
