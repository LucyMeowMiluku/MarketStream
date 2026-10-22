> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream: Project Problem, Architectural Decisions, and Validation Status

Date: September 17, 2026

## 1. Problem the Project Addresses

MarketStream processes streaming market events. Its main purpose is to identify unusual combinations of events that deserve manual review while preserving the data behind each decision. At present, the system neither predicts future returns nor executes trades automatically.

Fixed price thresholds are not suitable for this task. Different stocks have different normal ranges of volatility, and even the same stock may behave very differently at market open and around midday. A noticeable price move may also reflect a broader market movement rather than an anomaly in a single stock. To address these differences, the system first calculates eight interpretable factors and compares them with the stock's historical behavior in the corresponding time period. When a factor becomes abnormal, the CEP state machines continue to examine the event's direction, sequence, duration, and relationship with other stocks.

The system currently supports three main conclusions:

1. CHECKS-20261022 passes 63 tests and Ruff on the archived audit working tree, including the new accounting regression.
2. In controlled synthetic data, all six rule types can be triggered, and the false positives and ablation results of each rule can be observed.
3. Historical IEX runs show that real input can enter the system and generate snapshots at 10-second, 1-minute, and 5-minute intervals.

These results also have clear limitations:

- The real-world labels have not yet been independently reviewed and frozen, so Precision, Recall, and F1 on real market data cannot currently be reported.
- IEX represents only one trading venue and is not equivalent to complete SIP market data.
- The existing live-stream run lasted only about 88 seconds, which is not enough to demonstrate long-term system stability.
- The earlier experiments used artificially injected anomalies, so they cannot establish that the current CEP approach is generally better than ML in real markets.

## 2. Overall Design

The system data flow is as follows:

```text
MarketEvent
  → Quality Gate
  → FactorSnapshot (10 s / 1 min / 5 min)
  → six CEP state machines
  → DetectionResult
  → Kafka / TimescaleDB / Streamlit
```

This flow divides the work into three stages. First, input events are standardized and checked. Second, raw events are converted into comparable factor snapshots. Third, detection results are generated from the relationships among events. Kafka, TimescaleDB, and Streamlit handle message delivery, data storage, and result presentation, respectively. The detection logic does not depend on the presentation layer.

## 3. Role of Each Component

### 3.1 MarketEvent and Quality Gate

`MarketEvent` provides a unified format for trade, quote, bar, and news data. Each event retains its event time, received time, source, feed, event ID, run ID, and provenance for later traceability.

The Quality Gate flags duplicate, out-of-order, or overly old events, invalid prices, crossed quotes, zero trading volume, feed gaps, and other data-quality issues. Serious quality problems suppress alerts, but the raw events are still stored for later review. A minute bar's timestamp represents the start of its interval, so judging it directly by arrival time may incorrectly mark a normal bar as stale. The code therefore includes a 60-second close grace period.

### 3.2 FactorSnapshot

The Factor Engine calculates eight factors over 10-second, 1-minute, and 5-minute windows:

1. return surprise;
2. volatility burst;
3. relative volume;
4. spread stress;
5. quote imbalance;
6. signed trade imbalance;
7. market residual;
8. news shock.

Each snapshot also records the factor state, direction, baseline version, quality status, and the event IDs used in the calculation. A `DetectionResult` can therefore be traced back to the corresponding raw events.

### 3.3 CEP State Machines

The current implementation uses six small state machines with clearly defined logic. They detect stock-specific dislocation, liquidity pressure move, news-confirmed move, flash reversal, sustained pressure, and cross-asset shock.

The state machines examine only a limited set of event relationships and do not recalculate factors. The detector centrally handles warm-up suppression, serious-quality suppression, a 300-second cooldown, dedupe keys, severity, and evidence IDs. This separation keeps factor calculation and pattern detection clear and makes them easier to test independently.

### 3.4 Kafka, TimescaleDB, and Streamlit

- Kafka delivers events among the ingestion, factor calculation, and detection components, but it is not the only source of long-term state.
- TimescaleDB stores raw events, factor snapshots, detection results, and baseline states for time-based queries and result tracing.
- Streamlit displays prices, factors, alerts, and comparison results, but it does not participate in the core detection decisions.

## 4. Main Architectural Decisions and Their Rationale

### 4.1 Why the System Moved from a Four-Model Ensemble to CEP

The earlier main pipeline included EWMA, Half-Space Trees, Isolation Forest, and an LSTM autoencoder. It could produce anomaly scores, but it was less effective at representing event sequences and combinations. I compared several options: retaining the four models, adding more models, using a general-purpose NFA, and combining lightweight factors with explicit state machines.

The current online pipeline ultimately uses the factors and six CEP state machines, while the earlier ML results remain only as a historical comparison. Conditions such as "the price continues to confirm after a news event," "pressure persists across multiple windows," and "several stocks move within a short period" can be represented directly in state machines. The project currently has a limited number of patterns, so a more complex general-purpose NFA is unnecessary.

This choice also involves trade-offs. Rule parameters still require further calibration, extreme values in a single factor may produce false positives, and the existing results do not show that CEP is inherently more accurate than ML. The relevant implementation and experiment records are in `cep/state_machines.py`, `evaluation/run_synthetic.py`, the current synthetic JSON, and the earlier comparison JSON.

### 4.2 Why the System Uses 10-Second, 1-Minute, and 5-Minute Windows

A single window cannot easily cover immediate shocks, short-term persistence, and slower background changes at the same time. Using too many windows would increase the number of states and create duplicate evidence. The system therefore uses fixed cadences of 10 seconds, 1 minute, and 5 minutes to distinguish rapid reactions from persistent behavior while keeping system complexity under control.

These three windows are engineering choices and have not yet been optimized against frozen real-world labels. Events near the window boundaries may also generate duplicate evidence. The relevant implementation and tests are in `processing/factor_engine.py`, `tests/test_lightweight_factor_engine.py`, and the synthetic scenarios.

### 4.3 Why the System Uses the Median, MAD, and Empirical Quantiles

The mean and standard deviation are easily affected by extreme values. Thresholds based only on empirical quantiles may also be unstable when the sample size is small. The current baseline stores the median, MAD, 0.995 quantile, and 0.999 quantile, and uses:

```text
scale = max(1.4826 × MAD, 1e-6)
```

The elevated threshold uses the stricter of the empirical 0.995 quantile and `4 × scale`. The extreme threshold uses the stricter of the empirical 0.999 quantile and `6 × scale`. The median and MAD are more robust to outliers, while the empirical quantiles retain information about the actual distribution. The value 1.4826 is the scaling constant used to make MAD a consistent estimator of the standard deviation under a normal distribution.

These parameters remain engineering settings and should not be described as optimal for real-world data. The relevant code and tests are in `processing/factor_state.py`, `processing/factor_engine.py`, and the baseline tests.

### 4.4 Why the Baseline Uses a Five-Dimensional Key

The normal range of the same factor may differ across stocks, windows, market sessions, and intraday positions. The system uses the following five-dimensional key:

```text
(ticker, cadence, market_session, intraday_slot, factor_name)
```

This prevents direct comparisons between market-open and midday volatility and avoids placing SPY and an individual stock in the same baseline. The trade-off is a larger number of cells and fewer samples in each cell, so the system requires a warm-up process and state-recovery mechanism. Supporting evidence can be found in `processing/factor_state.py`, `baseline/contracts.py`, and the baseline persistence tests.

### 4.5 Warm-Up, Score Before Update, and Evaluation Freezing

If the current day's observations enter the baseline before the same day is scored against the updated baseline, anomalies will appear less significant and data leakage will occur. The current design requires each cell to contain observations from at least five strictly earlier trading days. When new data is processed, the system first loads the historical state and calculates the score, then writes the current day's observation. After a baseline is imported for evaluation, `freeze=True` is set.

As a result, a new deployment or a newly added stock goes through a warm-up period during which no alerts are produced. This behavior is covered by `tests/test_lightweight_factor_engine.py` and the replay validation tests.

### 4.6 Why the System Uses Six State-Machine Patterns

A single factor crossing a threshold only shows that one local signal is unusual. It is not enough to constitute a complete market event. The six state machines add timing and combination constraints:

- news-confirmed move retains news context for no more than five minutes;
- flash reversal requires two price events in opposite directions, separated by no more than two cadences;
- sustained pressure requires three different windows to appear in the four most recent frames;
- cross-asset shock requires at least three tickers within 60 seconds and must include SPY or QQQ.

These patterns are affected by sampling frequency and missing events. The extreme single-factor path in the current `stock_specific_dislocation` pattern is also the main source of false positives. Supporting evidence can be found in `cep/state_machines.py`, the golden trace tests, and the pattern ablation results.

### 4.7 Cooldown, Deduplication, and Traceability

The same anomaly may appear in consecutive snapshots. By default, the system merges results with the same ticker, pattern, and direction if they occur within 300 seconds. The dedupe key also includes the pattern's `started_at` timestamp. Each alert retains its factor evidence and event IDs.

This approach reduces duplicate alerts, although a second real event during the cooldown period may also be merged. To support review, `DetectionResult` still records the suppression reason. The relevant implementation is in `cep/cep_detector.py` and `tests/test_factor_cep.py`.

### 4.8 Baseline Persistence and Recovery

If the baseline exists only in memory, it will be lost when the system restarts. Restoring only part of the state from the database may also produce inconsistent results. The current startup process requires an explicit choice among `COLD_START`, `VERIFIED_BACKFILL`, and `RESTORE`. The baseline, runtime, and offset must belong to the same epoch/revision, and each checkpoint stores a manifest and checksum.

This prevents the system from continuing when the source of its state is unclear, although it adds operational steps. This evaluation cycle has not yet produced evidence from a long-running recovery test. The relevant design and tests are in `baseline/`, `docs/BASELINE_PERSISTENCE.md`, and the seven persistence tests.

### 4.9 Why IEX Is Used for Ingestion Validation

The system currently uses Alpaca IEX to validate real-data ingestion and records the feed in its output. This source was selected mainly because it is reliably available at the current stage of the project. IEX covers only one trading venue. Its quotes, trading volume, and event order may differ from SIP, so these results are used only to validate the pipeline and do not represent the entire market. The relevant records are in `data/evaluation/alpaca_live_e2e.json` and the producer configuration.

## 5. Two Algorithmic Details

### 5.1 Aggressor-Side Classification

The system uses the upstream-provided side when available. If the side is missing, it compares the trade price with the midpoint of the most recent bid and ask. A trade at or above the midpoint is classified as a buy, while a trade below the midpoint is classified as a sell. If neither the side nor a valid midpoint is available, the trade volume is excluded from the numerator used to calculate signed buy/sell imbalance.

This is an inspectable approximation and is not functionally equivalent to a complete Lee–Ready implementation.

### 5.2 News Sentiment

The current news-sentiment calculation uses small positive and negative word lists:

```text
sentiment = (positive_count - negative_count)
            / (positive_count + negative_count)
news_shock = sentiment × log(1 + headline_count)
```

When the denominator is zero, sentiment is set to zero.

This method is simple and transparent, but it has limited ability to handle word meaning, negation, and context.

## 6. Current Experimental Results and Their Meaning

### 6.1 Synthetic Protocol

SYN-TRACE-20261022 ran 20 seeds on the archived audit working tree; output: `reproduction_outputs/audit_20261022/factor_cep_traced.json`.

| Metric | Result |
|---|---:|
| TP / FP / FN | 360 / 120 / 0 |
| Precision / Recall / F1 | 0.750 / 1.000 / 0.857 |
| delay p50 / p95 / p99 | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0150 / 0.0306 / 0.0688 ms |

The 120 FP comprise 60 unmatched alerts in positive scenarios and 60 alerts in negative controls. The 360 positive scenarios emit 420 alerts; the 240 controls emit 60 alerts across 40 alerting cases. Thus 40/240 is a case rate, and the 60 control alerts are already included in the 120 FP. This decomposition was verified in the new traced run; old aggregate JSON alone cannot establish historical row membership.

All 20 seeds produced the same result because the current generator mainly changes identifiers and shifts timestamps without materially changing the pattern structure, magnitude, or rule boundaries. This shows that the script is reproducible, but it does not yet show that the system is stable across different real-world market conditions.

After removing `stock_specific_dislocation`, TP decreased from 360 to 300 and FP decreased from 120 to 0, while 60 generated anomalies were missed. This reflects the trade-off between timely single-factor alerts and confirmation from multiple pieces of evidence. Removing activity did not change the results, showing that `relative_volume` is not currently a key completion condition in any of the six rules.

### 6.2 Relationship to the Earlier ML Experiment

The earlier experiment injected artificial anomalies into a real OHLCV background. Under that setup, the full CEP system achieved an F1 score of 0.785, while the ML ensemble achieved 0.639. Under the earlier compatibility protocol, the average CEP computation time was 0.0033 ms.

These figures apply only to the earlier protocol. The earlier experiment and the current system differ in implementation, label source, and evaluation method. They therefore cannot establish that the current six-state-machine system is generally better than ML in real markets. The earlier 0.0033 ms figure also should not be directly combined or compared with the current 0.0150 ms result.

### 6.3 Soak Test and Live Run

The September 17 notes report an unavailable Docker/Colima socket. This audit checks saved artifacts only and does not rerun soak. The most recent usable historical result is from September 10, 2026: 240 inputs, 76 alerts, a p95 latency of 1.616 seconds, and zero duplicates. An earlier record from August 6, 2026, with 88 alerts and a p95 latency of 1.718 seconds, has also been retained. The first failed gate, which produced only 15 alerts, has not been deleted.

The IEX run lasted about 88 seconds and received 48,734 events. It generated 40 ten-second snapshots, five one-minute snapshots, and five five-minute snapshots. This run validated ingestion, storage, and cadence generation. Because there was no ground truth and the system was still in warm-up, it does not demonstrate detection accuracy.

## 7. My Specific Contributions to the Project

I led the selection of MarketStream’s core solution and its development priorities, scope, key design constraints, and verification requirements. I prioritised the backend pipeline, selected eight factors across three time windows with six CEP patterns as the detection architecture, and drove core simplification and modularisation. I directly specified baseline persistence, retention of the latest 20 trading days per cell, three explicit startup modes, and recovery requirements. I also required real-data evaluation, anomaly intervals identified in advance, and visual replay.

AI served as an auxiliary development tool: it provided technical advice, helped elaborate proposals, generated and refactored code, executed tests and debugging, and drafted and revised report text. AI contributed specific proposals for the factors, windows, patterns and explicit state-machine refactoring; implementation proceeded after my approval. Those proposals and generation records remain identified in the provenance materials.

My core contributions are solution selection, concrete problem and constraint design, development trade-offs, verification requirements, and report revision decisions. The contribution matrix separately evidences requirements I directly proposed and advice I chose to adopt, linking my decisions, AI assistance, and the resulting code and experiment artifacts.

| Decision area | My concrete action | AI execution | Direct evidence |
|---|---|---|---|
| Research architecture | Prioritised the backend and approved eight factors, three windows and six patterns as the main path | Proposed details and generated contracts, factors and CEP code | Matrix D01, D02; E01, E02 |
| Core simplification and machines | Requested less complexity and modularisation; approved six-machine refactoring | Split modules and generated machines and orchestration | D03; E02 |
| Baseline persistence | Specified database storage, 20 days, recovery, a separate module and three startup modes | Elaborated consistency details and implemented persistence | D04, D05; E03 |
| Evaluation | Challenged metric sources; required real data, prior labels and HTML; adopted strict freezing | Audited sources and implemented collection, labels, validation and evaluation | D06, D07; E04 |
| Engineering reruns | Required completion and reruns of outstanding checks | Executed tools and database checks; diagnosed and repaired stale bars | D08; E05 |
| Report | Required definitions, citations, structure, metric units/denominators and code mapping | Drafted, explained and revised prose and tables | D09, D10; E06–E09 |

The [five-column attribution matrix](08_Contribution_Attribution_Matrix_EN.md) links each personal action to original log lines. Technical detail is retained in the [contribution log](02_Technical_Contribution_Log_EN.md). Sole initial authorship of the full detailed architecture, all manual core code, and the extent of my report prose are not established and are explicitly marked for further evidence. Git author identity, code existence and test success cannot substitute for authorship evidence.

