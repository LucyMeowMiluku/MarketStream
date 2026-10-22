> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream Technical Contribution Log

Attribution revised: 22 October 2026. **I led the core solution and development priorities; AI assisted development.** Direct messages, AI execution and artifacts are mapped in the [five-column matrix](08_Contribution_Attribution_Matrix_EN.md).


## Contribution 1: Unified MarketEvent, Quality Checks, and Source Traceability

| Item | Description |
|---|---|
| Problem | Real-time trade, quote, bar, and news data, as well as historical replay data, could originally use different formats. This could cause the live and replay paths to diverge and make it difficult to trace an alert back to its original input. |
| Decisions and requirements I led | I approved the backend plan containing shared events, quality flags and provenance, and required real-pipeline verification. AI elaborated contract details. See D02 and D08. |
| AI assistance | AI proposed contract details, generated and refactored dataclasses, serialisation, the quality gate and tests, and diagnosed and repaired stale bars. |
| Code locations | `processing/event_models.py`, `processing/data_quality.py`, `tests/test_event_models.py`, and `tests/test_data_quality.py`. |
| Technical decisions | `MarketEvent` allows only one typed payload. When an upstream ID is unavailable, a deterministic hash is calculated from stable fields. The quality gate uses bounded state to check for duplicates, out-of-order events, stale events, invalid prices, crossed quotes, zero volume, and feed gaps. |
| Validation | CHECKS-20261022: 63 tests and Ruff passed on the archived source. The September 17 count of 62 is historical. |
| Issue found | The timestamp of an Alpaca minute bar represents the start of the minute interval. If it shares the same 30-second stale threshold as tick-level events, a normal bar may be incorrectly marked as stale. |
| Follow-up change | A separate 60-second close grace period was added for bars. None of the five bars in the real-time IEX validation was marked as stale. |
| Original evidence | [D02、D08；E01、E02、E05](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I adopted shared contracts and required continued real-pipeline verification. |
| Unsupported claim | I invented Alpaca's field definitions, the Kafka protocol, or the concept of event streams. |

## Contribution 2: Three Time Windows, Eight Factors, and a Five-Dimensional Baseline

| Item | Description |
|---|---|
| Problem | A single fixed price threshold cannot account for differences among stocks, trading sessions, intraday positions, and normal volatility levels. A baseline stored only in memory is also lost after a restart. |
| Decisions and requirements I led | I approved eight factors over 10-second / 1-minute / 5-minute windows and historical baselines as the main path. I separately specified 20-day baseline persistence and recovery. See D02 and D04. |
| AI assistance | AI proposed detailed factors and windows and generated the approved factor engine; later it split window state and formulas and implemented persistence interfaces and tests. |
| Code locations | `processing/factor_state.py`, `processing/factor_calculations.py`, `processing/factor_engine.py`, and `tests/test_lightweight_factor_engine.py`. |
| Technical decisions | The engine first reads the historical state and calculates the score, then writes the current day's observation. After a baseline is imported for testing, `freeze=True` is used. Signed factors use absolute distance, while unsigned factors check only upward anomalies. |
| Thresholds | The scale is `max(1.4826 × MAD, 1e-6)`. The elevated threshold uses the stricter of the empirical 0.995 quantile and `4 × scale`; the extreme threshold uses the stricter of the 0.999 quantile and `6 × scale`. Under a normality assumption, 1.4826 is the scaling constant that makes MAD a consistent estimate of the standard deviation. |
| Factors | return surprise, volatility burst, relative volume, spread stress, quote imbalance, signed trade imbalance, market residual, and news shock. |
| Aggressor-side classification | If the upstream source provides a side, the system uses it directly. Otherwise, it infers the side from the latest bid/ask midpoint: a trade price at or above the midpoint is treated as a buy, while a lower price is treated as a sell. If neither a side nor a midpoint is available, the trade volume is excluded from the buy/sell numerator. |
| News sentiment | The current online path uses a transparent word-list count rather than FinBERT. The score is `(positive_count-negative_count)/(positive_count+negative_count)`, and `news_shock` is then multiplied by `log(1+headline_count)`. |
| Validation | The tests cover the five-day warm-up, session isolation, exclusion of current-day data from current-day scoring, baseline freezing, and consistency after restart. |
| Original evidence | [D02、D04；E01、E02、E03](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I selected the eight-factor / three-window research architecture and directly specified baseline persistence and recovery. |
| Unsupported claim | MAD, quantiles, order imbalance, and market residual are my original algorithms. |

## Contribution 3: Six Explicit CEP State Machines and Alert Controls

| Item | Description |
|---|---|
| Problem | Anomaly scores from multiple models do not clearly explain event order. A single-window threshold also cannot express conditions such as “news occurs first and the price confirms later” or “pressure continues across multiple windows.” |
| Decisions and requirements I led | I requested removal of unnecessary complexity, retention of the core and modularisation, then approved six explicit state machines. AI proposed the concrete decomposition and implemented it. See D03. |
| AI assistance | AI proposed explicit state machines and, following my simplification goal and approval, added cep/state_machines.py, rewrote orchestration and generated tests. |
| Code locations | `cep/state_machines.py`, `cep/cep_detector.py`, `tests/test_factor_cep.py`, and `tests/test_cep_golden_trace.py`. |
| Six patterns | stock-specific dislocation, liquidity pressure move, news-confirmed move, flash reversal, sustained pressure, and cross-asset shock. |
| Key parameters | News confirmation retains context for five minutes. Flash reversal requires two price atomic events in opposite directions no more than two cadences apart. Sustained pressure requires at least three different windows in the same direction among the four latest frames. Cross-asset shock must cover at least three tickers within 60 seconds and include SPY or QQQ. The default cooldown is 300 seconds. |
| Alert controls | Alerts are suppressed during warm-up or when serious quality flags are present. Results with the same ticker, pattern, and direction are merged during the cooldown. The dedupe key is generated from the ticker, pattern, direction, and pattern `started_at`. |
| Validation | Synthetic protocol, negative controls, pattern ablation, golden trace, cooldown, and quality-suppression tests. |
| Issue found | `stock_specific_dislocation` allows an extreme return-surprise signal to raise an alert by itself. This path produced all 40 negative-control alerts. |
| Follow-up action | The project retains the rule and its precision/recall trade-off pending real normal-period and frozen-label validation. Available logs do not independently attribute the initial retention judgment to me. |
| Original evidence | [D03；E02](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I chose core simplification and modularisation and approved six explicit state machines as the current detection path. |
| Unsupported claim | I invented CEP or state machines, or the current rules have already been proven effective in real markets. |

## Contribution 4: Baseline Epochs, Persistence, and Recovery

| Item | Description |
|---|---|
| Problem | A baseline that exists only in process memory is lost after shutdown. A restart may then require several days of warm-up. If the database is cleared or only partly restored, the system also cannot automatically treat the situation as a first deployment. |
| Decisions and requirements I led | I directly identified restart loss and specified database storage, 20 trading days per cell, the business key and recovery; I then required a separate module and COLD_START, VERIFIED_BACKFILL and RESTORE. I approved AI elaboration of registry, revisions, offsets and checksums. See D04 and D05. |
| AI assistance | AI elaborated data structures and generated baseline/, database models, writer, checkpoints, backfill, startup coordination and tests from my persistence and startup requirements. |
| Code locations | `baseline/contracts.py`, `baseline/repository.py`, `baseline/startup.py`, `baseline/checkpoints.py`, `baseline/backfill.py`, `baseline/writer.py`, and `tests/test_baseline_persistence.py`. |
| Technical decisions | The startup mode must be set explicitly. When state is inconsistent, the system refuses to continue or recovers from the latest valid checkpoint. The baseline, runtime, and offset belong to the same epoch/revision. A checkpoint stores Parquet, JSON, a manifest, and a checksum. |
| Validation | The current seven baseline-persistence tests cover epochs, recovery, checksums, same-day replacement, and state consistency. The full test suite passes. |
| Limitations | There is currently no evidence from long-term production operation. Docker was not running, so an end-to-end database failure-recovery exercise was not repeated in this evaluation cycle. |
| Original evidence | [D04、D05；E03](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I specified concrete restart, 20-day persistence and explicit startup requirements; AI implemented the approved solution. |
| Unsupported claim | I independently wrote the complete persistence implementation, or this mechanism has been proven reliable in production. |

## Contribution 5: Leakage-Free Replay, Frozen Labels, and Event-Level Evaluation

| Item | Description |
|---|---|
| Problem | Early precision and recall figures came from generated sequences or artificially injected anomalies. A real live run has no ground truth. Changing labels or the baseline after seeing detector results would introduce evaluation bias. |
| Decisions and requirements I led | I challenged accuracy/recall provenance and required real data, prior anomaly intervals and an HTML trace; I approved AI elaboration of frozen labels, leakage safeguards and forward matching. See D06 and D07. |
| AI assistance | AI audited metric sources, elaborated review, freezing, manifests/checksums and strict matching, and generated collection, labels, evaluation, a comparison baseline and HTML. |
| Code locations | `replay/labels.py`, `replay/validation.py`, `replay/evaluator.py`, `evaluation/comparison.py`, and `evaluation/metrics.py`. |
| Technical decisions | Baseline data must strictly precede the evaluation interval. The test engine freezes the baseline after import. The label hash and data manifest must match. Real metrics are calculated only after all 12 anomalous and 12 normal intervals have been approved. Evaluation uses one-to-one forward event matching. |
| Validation | The tests cover rejection of unfrozen labels, data provenance, chronological ordering, baseline leakage, live/replay consistency, and event-level metrics. |
| Current status | The label file is still a draft with `frozen: false`. Formal real-data replay is therefore intentionally blocked. |
| Original evidence | [D06、D07；E04](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I challenged metric provenance, required real data, prior labels and visualisation, and adopted strict evaluation. |
| Unsupported claim | The system has achieved an F1 score of 0.857 or 0.785 in real markets. |

## Contribution 6: Alpaca IEX, Kafka, TimescaleDB Pipeline, and Live-Stream Investigation

| Item | Description |
|---|---|
| Problem | Synthetic data can test only the rules. It is also necessary to confirm that real input can pass through ingestion, Kafka, factor calculation, and the database. |
| Decisions and requirements I led | I requested completion and reruns of Alpaca, historical-data and Kafka-to-database checks, and approved the boundary between integration and detection metrics. AI executed tools and diagnosed stale bars. See D08. |
| AI assistance | AI executed smoke/E2E, database and soak checks, diagnosed and repaired stale bars, and documented results and limits in response to my rerun requests. |
| Code locations | `producers/alpaca_producer.py`, `processing/factor_stream.py`, `cep/online_scorer.py`, `storage/`, and `scripts/run_backend_soak.py`. |
| Validation | The IEX run lasted about 88 seconds and persisted 48,734 real events: 48,283 quotes, 446 trades, and five bars. It generated 40 ten-second snapshots, five one-minute snapshots, and five five-minute snapshots. |
| Soak test | The latest historical run on September 10, 2026, processed 240/240 events, produced 76 alerts, had a p95 latency of 1.616 seconds, produced no duplicates, and was fully traceable. The earlier run on August 6, 2026, produced 88 alerts with a p95 latency of 1.718 seconds. |
| Limitations | IEX is data from a single trading venue, not SIP. The 88-second run was still in warm-up. The soak input was a synthetic transport probe. |
| Original evidence | [D08；E05](08_Contribution_Attribution_Matrix_EN.md)；[Decision log excerpts](Evidence_Attachments/Decision_Log_Excerpts.md)。 |
| My core contribution | I required continued Alpaca and Kafka-to-database verification and approved the boundary between engineering and effectiveness evidence. |
| Unsupported claim | The system has already operated reliably in a real business environment, or processing 48,734 events proves detection accuracy. |

## Report-writing decisions

I explicitly required anomaly definitions, individual citations, simpler structure and separate metric tables. AI drafted and revised substantial reference text. My paragraph-level prose authorship remains to be established from version records. See D09, D10 and unresolved claims in the matrix.
