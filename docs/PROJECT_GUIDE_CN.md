# MarketStream 项目导读（底层优先版）

## 1. 现在这个项目究竟在做什么

MarketStream 的目标不是再堆一个更复杂的异常检测模型，而是构建一套可以实时运行、解释清楚、可靠回放和公平评测的市场异常检测系统。

项目早期的核心是 EWMA、Half-Space Trees、Isolation Forest 和 LSTM Autoencoder 四模型加权。这个版本保留了可用的离线基线，但存在三个研究问题：模型职责互相重叠，分数和阈值难解释；生产链路受训练、模型文件和推理成本影响；旧评测主要使用点异常和对称容忍窗口，容易高估真实事件识别能力。

新的主线是：先把行情和新闻变成统一事件，再用少量有金融含义的因子表达“发生了什么”，最后用 CEP 表达“这些事情以什么顺序、持续多久、是否互相确认”。

```text
真实流 / 历史回放
      ↓
MarketEvent + 数据质量标记
      ↓
8 个轻量因子（10s / 1m / 5m）
      ↓
6 类有方向的 CEP 模式
      ↓
可追溯 DetectionResult 与去重告警
      ↓
事件级评测、延迟与告警负担
```

## 2. 为什么先不重构前端

当前 Streamlit 页面依赖旧的五分钟特征和四模型分数。如果现在重做页面，因子字段、模式名称、告警时间语义和评测接口每变化一次，前端都要返工。

所以当前只做三件必要修改：主页方法说明改成因子加 CEP；告警页能展示模式、方向、因子证据和数据质量；旧图表继续从五分钟兼容输出读取。真正的专业前端要等 `MarketEvent`、`FactorSnapshot`、`DetectionResult`、数据库告警结构和评测输出稳定后再做。

## 3. 数据平面

### 3.1 实时数据

`producers/alpaca_producer.py` 同时订阅 AAPL、TSLA、NVDA、QQQ、SPY 的 trades、quotes、bars 和新闻。股票流默认使用 Alpaca `iex` feed，代码和日志明确标注“仅 IEX，不是完整 SIP”。这点很重要：IEX 可以支持原型和方法验证，但不能把它包装成全市场盘口覆盖。[Alpaca real-time data](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data)

新闻保留数据源提供的 `created_at`，不再用抓取时间冒充新闻发生时间。线上新闻冲击使用一个透明、固定词表的轻量情绪分数，不在实时主链加载深度模型；FinBERT 仍可用于离线比较。

### 3.2 历史微观结构

`producers/databento_history.py` 只允许下载 `bbo-1s`、`trades` 和 `mbp-10`。其中 MBP-10 每次最多三天，目的是把额度用在预先登记的真实事件日，而不是无边界下载。[Databento MBP schemas](https://databento.com/docs/schemas-and-data-formats/market-by-price)

### 3.3 统一事件

`processing/event_models.py` 的 `MarketEvent` 是 live 与 replay 的共同合同：

- `event_id/source/feed/event_type/ticker`
- `event_time/received_at`
- trade、quote、bar、news 四选一载荷
- `quality_flags`

`processing/data_quality.py` 显式标记重复、乱序、陈旧、零量、无效价格、跨价报价和断流。重复和乱序事件仍被记录进质量证据，但不重复累加成交量或改变价格状态。

Replay 不是一条“简化版离线路径”。`producers/replay_producer.py` 把 JSONL 中的同一个 `MarketEvent` 发到 `raw.market_events`，后续仍经过 Kafka、质量门、因子引擎和 CEP。

## 4. 因子平面

`processing/factor_engine.py` 不依赖 Alpaca、Databento、Kafka 或 CEP。它只认 `MarketEvent`，维护固定长度状态并输出 `FactorSnapshot`。

| 组 | 因子 | 含义 |
|---|---|---|
| 价格 | `return_surprise` | 当前收益相对同一日内位置历史分布的偏离 |
| 价格 | `volatility_burst` | 窗口内高低振幅相对正常振幅的放大 |
| 活跃度 | `relative_volume` | 当前成交量相对同一时段历史中位数 |
| 流动性 | `spread_stress` | 买卖价差相对正常价差的扩大 |
| 流动性 | `quote_imbalance` | 买一挂单量与卖一挂单量的方向性差异 |
| 流动性 | `signed_trade_imbalance` | 主动买入量与主动卖出量的方向性差异 |
| 市场上下文 | `market_residual` | 个股收益减去最近的 QQQ/SPY 基准收益 |
| 新闻 | `news_shock` | 新闻方向乘以同一窗口新闻聚集强度 |

每个基线按 ticker、cadence、盘前/正常/盘后和日内槽位分别维护。当前窗口先用历史基线评分，再写入基线，避免“拿测试点参与自己的阈值”。中心位置用中位数，尺度用 MAD，并同时保留经验 99.5% 和 99.9% 分位信息。

`FactorSnapshot` 有 10 秒、1 分钟和 5 分钟三种 cadence。前两种用于实时 CEP，5 分钟快照附带旧 `stream.features` 字段，继续支持旧图表和 ML backtest。少于五个严格在先的交易日时，快照为 `warming_up`，因子状态不允许升级成正式告警。

## 5. CEP 检测平面

生产接口是：

```python
CEPDetector.process(snapshot: FactorSnapshot) -> DetectionResult
```

旧 `score(features: dict)` 没有删除，它只负责兼容原来的回测和四模型比较。

六类模式都是有方向的：

1. `stock_specific_dislocation`：价格异常并相对市场基准发生偏离；极端单一价格因子也可进入这一类，但解释会说明上下文尚未确认。
2. `liquidity_pressure_move`：价差压力、盘口/成交压力与价格方向一致。
3. `news_confirmed_move`：有时间戳的新闻冲击在五分钟内被价格确认。
4. `flash_reversal`：极短时间内出现方向相反的价格异常。
5. `sustained_pressure`：至少三个窗口持续同向压力，随后价格确认。
6. `cross_asset_shock`：一分钟内基准 ETF 与至少两个资产同向异常。

单个普通因子只会产生原子事件或进行中模式，不直接告警。正式告警要求两个正交因子组、持续条件，或单因子达到极端状态。告警按 ticker、pattern、direction 设置冷却；冷却内相同模式标为 `merged`，不写第二条正式告警。

`DetectionResult` 保存总分、严重度、原子事件、完成/进行中模式、因子证据、模式开始与完成时间、检测时间、原始事件 ID、数据质量、解释和去重键。数据库中的告警因此可以从告警追到因子快照，再追到原始事件引用。

## 6. 存储与运行

新增 TimescaleDB 表 `factor_snapshots`；`anomaly_alerts` 增加 pattern、direction、severity、事件时间范围、首次检测时间、因子证据、原始事件引用、数据质量和 dedupe key。

`storage/migrations.py` 使用 `ADD COLUMN IF NOT EXISTS` 和 `CREATE INDEX IF NOT EXISTS`，旧数据库不再需要手工改表。

独立启动命令：

```bash
scripts/run_component.sh data-source
scripts/run_component.sh factor-engine
scripts/run_component.sh cep
scripts/run_component.sh ml-shadow
scripts/run_component.sh replay data/replay/events.jsonl --speed 20
scripts/run_component.sh dashboard
```

API key 只从环境变量读取。`SecretStr` 避免它们在配置对象、异常或日志里以明文展示。

## 7. 正确的评测顺序

### 7.1 先冻结协议，再看测试结果

OHLCV 与新闻数据按时间做 60/20/20 划分。训练段建立基线，验证段选择阈值，阈值冻结后测试段只运行一次。测试异常幅度和测试标签不能进入阈值选择。

### 7.2 事件匹配

`ml/event_metrics.py` 使用一对一、向前匹配：检测时间必须不早于事件开始；一条检测最多匹配一个真实事件。旧的 ±2 窗口指标只能作为敏感性对照。

### 7.3 合成序列与负对照

`ml/sequence_anomalies.py` 为六类模式生成完整序列，并提供四个负对照：高成交量但价格不动；只有少量资产的有序市场共同变化；六分钟以前的陈旧新闻；盘后单独扩大价差。

`ml/evaluate_factor_cep.py` 默认运行 20 个 seed 和 low/medium/high 三档强度，输出事件 precision、recall、F1、首次检测延迟、每 ticker 每小时告警数、重复率、CEP p50/p95/p99 和 bootstrap 95% 区间。

真实事件研究不再在目标日期前后反选最大波动。`ml/event_case_study.py` 使用预先登记日期，并映射到当日或之后第一个交易日。微观结构事件日也应在下载前登记。

## 8. 跨领域综述给本项目的结论

- 医疗预警说明：少量指标、分段风险和持续条件通常比黑箱总分更容易校准和使用。
- 工业与航天说明：应优先构造有领域含义的派生量，并围绕运行基准、残差和置信度解释异常。[NASA MEDOS](https://ntrs.nasa.gov/citations/20250002215)
- 网络安全说明：流式检测必须控制内存；计数、比例、sketch 和事件关联可以在很小状态下发现复杂行为。[StreamSpot](https://www.kdd.org/kdd2016/subtopic/view/fast-memory-efficient-anomaly-detection-in-streaming-heterogeneous-graphs)
- 通用时序基准说明：复杂深度模型并不会稳定优于简单方法，数据集、标注和评测协议的影响可能更大。[TSB-AD](https://proceedings.neurips.cc/paper_files/paper/2024/hash/c3f3c690b7a99fba16d0efd35cb83b2c-Abstract-Datasets_and_Benchmarks_Track.html)
- 金融异常不能只看价格：相对成交量、流动性、买卖压力、市场共同因子和新闻时间关系共同决定一条告警是否有解释力。

完整英文综述见 `LITERATURE_REVIEW_V2.docx`，旧 `LITERATURE_REVIEW.docx` 保留不动。

## 9. 当前已经完成与仍需实证的部分

已经完成：统一事件、质量门、Alpaca IEX/新闻接入代码、Databento 额度约束、live/replay 同路由、八因子快照、六类 CEP、冷却/合并、数据库迁移、兼容 Kafka 输出、事件级评测、序列异常、负对照、20-seed runner、Streamlit CEP 兼容。

2026-08-06 已完成两项基础设施验收：

- `data/historical/manifest.json` 验证五个标的各有 400 天 OHLCV 覆盖，共 1,380 行；新闻共 6,418 条，每个标的覆盖 397–400 天，并固定了 60/20/20 时间切分。当前无 Alpaca key，因此新闻来源明确标记为逐月 Google News RSS 查询语料，不冒充完整 Benzinga 归档；有 key 时可用 `--news-provider alpaca` 重采。
- `data/evaluation/kafka_db_soak.json` 验证 240 条 `mode=soak` 事件全部经过独立 Kafka topic、因子引擎、CEP 并写入数据库，得到 88 个可追踪告警样本；p95 为 1.718 秒，p99 为 1.738 秒，无重复告警。第一次只有 15 个告警样本、未达到样本门槛的失败记录也保留在对应 run 目录。

2026-08-14 已补入真实 Alpaca 凭据。IEX 股票流和 Alpaca 新闻流均已完成认证与订阅；`FAKEPACA` 官方测试流以及 15 分钟延迟 SIP 都取得并成功解析了 WebSocket 行情消息。Alpaca/Benzinga 历史版本也已采集 15,148 条新闻并通过 400 天覆盖验收。

2026-08-19 在美股常规交易时段重新复验后，最后一条 IEX 实时门槛已经通过。严格 smoke 在 12 秒内收到真实 IEX quote；随后正式 producer 经 Kafka 和因子引擎运行约 88 秒，五个标的共持久化 48,734 条真实 IEX 事件，其中 quote 48,283、trade 446、bar 5，并生成 10 秒、1 分钟和 5 分钟因子快照。证据见 `data/evaluation/alpaca_live_e2e.json`。

实流还暴露并修复了一个数据质量语义问题：minute bar 的时间戳是窗口起点，通常在一分钟结束后才送达，旧规则会将正常 bar 误标为 stale。现在 bar 有独立的 60 秒窗口结束宽限，并有回归测试；复验中的 5 条 bar 均不再被误标。

当前合成协议也会如实保留不利结果：high 强度下，极端单因子规则可能在某些负对照上发警。这不是应该隐藏的失败，而是验证阶段需要用真实正常期决定是否收紧“极端单因子”例外的依据。

### 9.1 真实历史回放的严格评估入口

现在已经新增 `replay/` 独立链路：从 Alpaca 历史 trades、quotes、1-minute bars 和 Benzinga news 分页采集真实记录，转换为带 dataset/interval/phase provenance 的 `MarketEvent`，再确定性复用 `EventQualityGate → LightweightFactorEngine → CEPDetector`。每个区间使用之前 20 个交易日同一日内时段建立 median/MAD 基线；导入测试引擎后阈值冻结，测试窗口不会回写 baseline。

`data/replay/labels/iex_benchmark_v1.draft.json` 是 12 个异常候选和 12 个正常对照的预登记草案，目前全部为 `proposed`，所以不能用它生成真实 precision/recall。独立审阅人必须在不查看 detector 输出的前提下补齐 `approved`、`reviewed_by`、`reviewed_at` 和 confidence，之后才能执行 freeze。评估器会拒绝未冻结/未完整批准标签、labels hash 变化、分页不完整、文件 checksum 或事件计数不一致、synthetic/soak ID、baseline 泄漏、provenance 不一致以及任何仍处于 warm-up 的因子窗口。

完整流程见 README 的 “Reviewed real historical replay”。合法运行会生成 `run_manifest.json`、`trace.jsonl`、`metrics.json` 和自包含 `replay_report.html`。主指标只使用事件级一对一向前匹配，不把 accuracy 当 headline，也不要求 CEP pattern 名与人工事件类别相同；pattern 一致率、延迟、每小时误警、重复率、质量覆盖率和 traceability 单独报告。HTML 持续标注 Alpaca IEX 仅代表单交易所、不是 consolidated SIP。

## 10. 下一次重新打开项目时，从哪里开始

1. 先读本文件，确认研究问题和数据限制。
2. 看 `processing/event_models.py`，理解三个稳定合同。
3. 看 `processing/factor_engine.py`，逐个核对八个因子的计算与基线。
4. 看 `CEPDetector.process()`，核对六个模式和告警抑制。
5. 跑 `uv run pytest -q` 与 `uv run ruff check .`。
6. 跑 `uv run python -m ml.evaluate_factor_cep`，保留输出，即使结果不理想。
7. 独立审阅并冻结 `data/replay/labels/iex_benchmark_v1.draft.json`，再采集和运行真实历史回放；不得根据 detector 输出反向改标签。
8. 若要调参，创建新 detector 版本并换用另一个冻结 holdout 集重新评估。
