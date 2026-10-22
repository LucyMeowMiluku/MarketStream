> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream: Real-Time Market Anomaly Detection with Lightweight Factors and CEP

## Abstract

Market data is noisy and fast. Its quality is also uneven. A fixed price threshold is not enough. It cannot tell whether a move is stock-specific, market-wide, news-related, or caused by weak input data. A large model ensemble can provide several scores, but it can also be difficult to explain and maintain.

This project presents MarketStream. It is a research prototype for real-time market anomaly monitoring. The current flow is:

```text
MarketEvent → Quality Gate → FactorSnapshot → CEP State Machines → DetectionResult
```

Trade, quote, bar, and news events use one data contract. The system calculates eight factors over 10-second, 1-minute, and 5-minute windows. It then applies six explicit CEP patterns. Results keep factor evidence and source event IDs.

The evidence is reported by type. The current synthetic protocol gives Precision 0.750, Recall 1.000, and F1 0.857. Current CEP computation has p50 0.0150 ms and p99 0.0688 ms. Within that same pooled protocol, 40 of 240 negative-control cases emit 60 alerts already included in the 120 FP. An older five-minute injected protocol reported CEP F1 0.785 and ML ensemble F1 0.639. This old result does not prove that current CEP is better on real markets.

The latest saved Kafka and database soak has 240 inputs, 76 alerts, zero duplicates, and p95 latency of 1.616 seconds. An 88-second Alpaca IEX run stored 48,734 real input events and created all three snapshot cadences. It proves integration only. It does not prove detection accuracy. Real labels are not independently reviewed and frozen, so this report does not give real-market Precision, Recall, or F1.

**Keywords:** streaming anomaly detection; complex event processing; market microstructure; event-level evaluation; traceability

## 1. Introduction

### 1.1 Problem

Financial markets produce trades, quotes, bars, and news. A useful monitoring system should do more than show a large price move. It should explain the context. It should also show data quality and the event order.

A three per cent move has different meanings for a stable ETF and a volatile stock. Activity near the market open also differs from activity at midday. A stock can move with SPY or QQQ. In that case, the move may not be stock-specific.

The project therefore defines an anomaly as a contextual event:

\[
A_t=g(F_t,F_{t-k:t},C_t,Q_t)
\]

Here, \(F_t\) is the current factor state. \(F_{t-k:t}\) is recent factor history. \(C_t\) is market, session, and news context. \(Q_t\) is quality and warm-up state. The function \(g\) is the CEP logic.

### 1.2 Research questions

This report asks three questions.

1. Can lightweight factors provide a useful and explainable online path?
2. Can CEP express order, persistence, direction, and cross-asset relations?
3. Can the prototype control delay, duplicates, alert burden, and traceability?

The current work can answer these questions only in part. Controlled experiments test implementation behaviour. They do not establish real-market effectiveness.

### 1.3 Scope

MarketStream does not predict future returns. It does not place trades. It produces investigation signals. The current implementation is a research prototype. Alpaca IEX covers one venue and is not a consolidated SIP feed.

## 2. Related work

The literature gives design motivation. It does not validate MarketStream.

Prytherch et al. [11] showed that a small set of clinical variables can form an interpretable score. The reported 24-hour mortality AUROC was 0.888 in its own clinical dataset. This result cannot be transferred to finance.

Drew et al. [4] reported a very large alarm burden in an ICU study. This motivates reporting alert counts and repeated alarms. It does not provide a financial threshold.

Barrie et al. [1] described MEDOS. It first forms meaningful derived parameters, then compares them with typical values. MarketStream borrows this general idea. It does not implement the MEDOS fuzzy system.

Powell et al. [10] demonstrated behavioural anomaly detection in two industrial test environments. The report supports context-aware monitoring. It is not evidence of a MarketStream deployment.

Gyllstrom et al. [6] showed how CEP can combine low-level RFID readings into higher-level events. This supports sequence, window, and relation logic. The six financial patterns remain project definitions.

Guha et al. [5] presented Robust Random Cut Forest for streaming anomaly detection. It shows that an online method can be updated without a deep sequence model. It does not show that CEP is more accurate.

Liu and Paparrizos [7] reviewed data, metrics, and setup problems in time-series anomaly benchmarks. Their work supports a fair and reproducible protocol. MarketStream does not claim that its event metric is VUS-PR.

Bhattacharya et al. [2] explained bias in Point Adjustment. MarketStream uses one-to-one event matching to avoid repeated true positives. It does not claim to implement Balanced Adjustment.

Cont et al. [3] found a short-horizon relation between price changes and order flow imbalance. Strict OFI includes limit orders, cancellations, and market orders. The present top-of-book factors are simplified. They are not the same measure.

MacKinlay [8] described event studies and abnormal return. The project uses \(r_i-r_m\) as a lightweight market residual. It is not a formal event-study abnormal return.

Manzoor et al. [9] used bounded sketches for streaming heterogeneous graphs. It motivates bounded state. Its attack-graph accuracy and throughput do not transfer to finance.

Tetlock [12] linked media pessimism with market behaviour. This supports news as context. It does not validate the current small word list or prove news causality.

## 3. System design

### 3.1 MarketEvent and quality

`MarketEvent` is the shared input contract. It supports trade, quote, bar, and news payloads. It stores event time, receive time, source, feed, identifiers, run context, and provenance.

The Quality Gate checks duplicates, out-of-order events, stale input, invalid prices, crossed quotes, zero volume, and feed gaps. Severe quality flags suppress formal alerts. The original input remains available.

A minute bar timestamp marks the start of its interval. A normal bar can therefore look stale under a single 30-second rule. The current code adds a 60-second close grace for bars.

### 3.2 FactorSnapshot

The Factor Engine creates snapshots at three cadences:

- 10 seconds for quick changes;
- 1 minute for short behaviour and bar alignment;
- 5 minutes for slower context.

These windows are engineering choices. They have not been shown to be optimal on frozen real labels.

Each snapshot contains eight factors:

1. return surprise;
2. volatility burst;
3. relative volume;
4. spread stress;
5. quote imbalance;
6. signed trade imbalance;
7. market residual;
8. news shock.

### 3.3 CEP patterns

The current core uses six small state machines:

| Pattern | Main relation |
|---|---|
| Stock-specific dislocation | stock return and market residual agree, or return is extreme |
| Liquidity pressure move | spread and imbalance pressure confirm a price move |
| News-confirmed move | price follows news direction within five minutes |
| Flash reversal | opposite price events occur within two cadences |
| Sustained pressure | pressure appears in three distinct windows among the latest four |
| Cross-asset shock | at least three tickers move in one direction within 60 seconds, including SPY or QQQ |

The detector also checks warm-up and data quality. It applies a 300-second cooldown to the same ticker, pattern, and direction. Results keep evidence IDs and suppression reasons.

### 3.4 Infrastructure roles

Kafka carries events between components. TimescaleDB stores raw events, snapshots, results, and baseline state. Streamlit shows prices, factors, alerts, and experiment views. The dashboard does not make the detection decision.

## 4. Factor and baseline method

### 4.1 Trade direction

The system first uses an upstream `side` if one exists. Otherwise, it compares trade price \(P_t\) with the latest bid/ask midpoint:

\[
M_t=(bid_t+ask_t)/2
\]

A trade at or above the midpoint is counted as estimated buy volume. A lower trade is counted as estimated sell volume. If there is no side and no valid two-sided quote, the trade is not included in the signed numerator.

This is a simple and inspectable approximation. It is not a true aggressor label and not a full Lee–Ready implementation.

### 4.2 News score

The online news path does not use FinBERT. It uses a small positive and negative word list. For one headline:

\[
s=\frac{n_+-n_-}{n_++n_-}
\]

The score is zero when no word matches. The window factor is:

\[
news\_shock_t=\bar{s}_t\log(1+n_t)
\]

The method is easy to inspect. It has weak handling of negation, context, and ambiguous words.

### 4.3 Five-part baseline key

A baseline cell is identified by:

```text
(ticker, cadence, market_session, intraday_slot, factor_name)
```

Each cell stores observations by session date. It keeps at most the latest 20 trading days with data. A cell needs five strictly earlier trading days before it is ready.

This structure avoids mixing different stocks, windows, sessions, and times of day. It also creates many small cells. Some cells may remain in warm-up.

### 4.4 Median, MAD, and thresholds

For historical values \(X\), the robust scale is:

\[
scale=\max(1.4826\times MAD(X),10^{-6})
\]

The value 1.4826 is the normal-consistency scale for MAD. It does not mean that market factors are normally distributed.

For signed factors, the distance is \(|x-median|\). The elevated threshold is the stricter value from the 0.995 empirical quantile distance and \(4\times scale\). The extreme threshold uses the 0.999 quantile distance and \(6\times scale\).

For non-negative factors, the elevated threshold is:

\[
\max(q_{0.995}, median+4\times scale)
\]

The extreme threshold replaces 0.995 and 4 with 0.999 and 6.

The code uses nearest-rank quantiles. With at most 20 observations, both high quantiles often equal the sample maximum. They should not be interpreted as reliable 0.5% or 0.1% tail probabilities. They are engineering guards.

### 4.5 No-leakage update

The engine reads earlier dates and scores the current value first. It updates the current date later. A formal evaluation imports the baseline and then freezes it. This avoids a current event changing its own threshold.

### 4.6 Persistence and restart

The current working tree adds baseline persistence. Startup must explicitly use one of three modes:

- COLD_START;
- VERIFIED_BACKFILL;
- RESTORE.

Baseline rows, runtime state, and offsets belong to an epoch and revision. Checkpoints store manifests and checksums. An inconsistent state cannot be silently treated as a first deployment.

This design passes the current persistence tests. It has not been validated through a long production recovery history.

## 5. Evaluation design

### 5.1 Evidence classes

The report uses four evidence classes:

1. current-version measured results;
2. historical results from an older version or protocol;
3. controlled validation with generated or injected input;
4. work not yet demonstrated.

### 5.2 Current synthetic protocol

The current protocol creates the six pattern types at three strengths. It runs 20 seeds. It also includes negative controls, factor-group ablations, pattern ablations, delay, alert burden, duplicate rate, and CEP compute time.

The command is:

```bash
.venv/bin/python -m report.tools.audit_results
```

The generator knows the anomaly type, direction, and start time. This allows controlled matching. It also limits realism.

### 5.3 Old CEP and ML comparison

The old protocol used five-minute OHLCV background with injected price, volume, sentiment, and multi-feature anomalies. It compared the old CEP path with a four-model ML ensemble.

It is historical evidence. It does not use the complete current eight-factor and six-state-machine implementation.

### 5.4 Soak and live input

The soak sends synthetic transport events through Kafka, factor processing, CEP, and the database. It checks persistence, traceability, duplicates, and end-to-end latency. It does not check financial accuracy.

The Alpaca IEX run checks real input integration. It has no reliable anomaly labels.

### 5.5 Formal real replay

Formal replay requires 12 abnormal intervals and 12 normal intervals. An independent reviewer must approve them. The registry must be frozen before detector output is viewed. The data manifest, feed, checksums, baseline period, and evaluation period must also pass validation.

The current label registry is still a draft. The evaluator therefore refuses to create formal metrics.

## 6. Results

Source bindings: 6.1=CHECKS-20261022; 6.2=SYN-TRACE-20261022 (`factor_cep_traced.json`, `scenarios.json`); 6.3=SYN-SUITE-20261022 (`factor_cep_suite.json#/ablations`); 6.4=LEGACY-INJECTED (`methods`); 6.5=the three original `soak-*/report.json`; 6.6=`alpaca_live_e2e.json`. The abstract and conclusion repeat these runs. All seven provenance fields, file hashes and missing historical fields are recorded in the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md).


### 6.1 Tests and static checks

CHECKS-20261022, on the archived audit working tree, produced:

```text
63 passed in 4.67s
All checks passed (Ruff)
```

The September 17 summary reported 62 tests; the new accounting regression adds one. The older 160-test statement has no complete run binding and is not current evidence.

### 6.2 Synthetic detection

| Metric | Result |
|---|---:|
| TP | 360 |
| FP | 120 |
| FN | 0 |
| Precision | 0.750 |
| Recall | 1.000 |
| F1 | 0.857 |
| first detection p50 / p95 / p99 | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0150 / 0.0306 / 0.0688 ms |
| alerts per ticker-hour | 1.604 |
| duplicate rate | 0 |

The system detects all 360 generated target events. It emits 480 alerts, so 120 are unmatched. 

The 120 FP comprise 60 unmatched alerts in positive scenarios and 60 alerts in negative controls. The 360 positive scenarios emit 420 alerts; the 240 controls emit 60 alerts across 40 alerting cases. Thus 40/240 is a case rate, and the 60 control alerts are already included in the 120 FP. This decomposition was verified in the new traced run; old aggregate JSON alone cannot establish historical row membership.

The bootstrap resamples truth-hit indicators while holding FP fixed. All truth events are matched, so its interval collapses. It does not estimate normal-period false-alert uncertainty or establish stability across seeds. The 1.604 alerts/ticker-hour includes artificial ten-minute scenario gaps; zero duplicates with detector cooldown=0 does not validate production cooldown.

### 6.3 Ablations

Removing `stock_specific_dislocation` changes TP from 360 to 300 and FP from 120 to 0. Precision becomes 1.000 and Recall becomes 0.833. The system misses 60 generated anomalies. The result shows a trade-off between an early single-factor alert and multi-signal confirmation.

Removing the activity group has no effect. `relative_volume` is not a critical completion condition in the six current patterns. A factor can have a reasonable financial meaning but still have no measured role in the current rules.

Removing price gives no completed detections. Removing liquidity or all microstructure factors lowers F1 to 0.632. Removing news lowers F1 to 0.750. Removing market context lowers F1 to 0.800.

### 6.4 Historical ML comparison

| Method | Precision | Recall | F1 | FPR | Mean compute |
|---|---:|---:|---:|---:|---:|
| ML ensemble | 0.572 | 0.724 | 0.639 | 3.06% | 4.5135 ms |
| CEP full | 0.754 | 0.818 | 0.785 | 1.51% | 0.0033 ms |
| CEP automata-only | 0.611 | 0.049 | 0.091 | 0.18% | 0.0033 ms |

This table is from the old injected protocol. The 0.0033 ms value is not the current six-state-machine timing. The low recall of automata-only also shows a protocol mismatch. Many injected anomalies are point events, while sequence rules need more than one event.

### 6.5 Soak history

The latest saved run is dated 10 September 2026:

| Item | Result |
|---|---:|
| input / persisted events | 240 / 240 |
| traceable alerts | 76 |
| duplicate alerts | 0 |
| p50 / p95 / p99 latency | 1.476 / 1.616 / 1.727 s |

An older 6 August run had 88 alerts and p95 1.718 seconds. The first saved run had only 15 alerts and failed its minimum-sample gate. All three records are kept.

This audit reads saved soak reports only. Docker/Colima unavailability was recorded on September 17; it was not retested as a current environment condition.

### 6.6 Alpaca IEX run

| Item | Count |
|---|---:|
| total events | 48,734 |
| quote / trade / bar | 48,283 / 446 / 5 |
| tickers | 5 |
| 10-second snapshots | 40 |
| 1-minute snapshots | 5 |
| 5-minute snapshots | 5 |
| stale bars after the fix | 0 |

The run lasted about 88 seconds. It remained in warm-up. It proves that the data path and cadence generation worked in that run. It does not provide real detection accuracy.

### 6.7 Formal real replay: no eligible result

The draft and three AI-preannotation files each contain 24 proposed intervals (12 anomaly and 12 normal), all with `frozen=false`. No eligible dataset manifest, formal run ID or formal metric output was found. AI preannotation is not independent approval. Protocol tests do not establish real-market effectiveness.

The separate historical coverage artifact HIST-COVERAGE-20260814 contains Yahoo daily prices (277 rows per ticker, July 9, 2025–August 13, 2026) and Alpaca/Benzinga news (15,148 ticker-linked rows; 10,930 distinct article IDs; actual publication dates June 19, 2025–August 13, 2026). Its 60/20/20 split is a recorded proposal, not a completed micro-event baseline or evaluation.

## 7. Discussion

### 7.1 Where the complexity moved

The project did not replace ML with one fixed threshold. It moved complexity from several models and weighted scores into factor meaning, baseline context, direction, time order, persistence, and alert control.

This makes each result easier to inspect. It does not remove the need for calibration.

### 7.2 Negative results matter

The negative controls show that the extreme dislocation exception is too permissive under some generated inputs. The activity ablation shows that one factor currently has no critical rule role. These results are kept because they affect the next design decision.

### 7.3 Evaluation is the main gap

The current main gap is not another model. It is a frozen and independently reviewed real event set. Without it, real effectiveness claims would be weak.

The next fair comparison should use one dataset, one time split, one label registry, and one event metric. Parameter selection should use validation data. The final test should run once.

### 7.4 IEX limitation

IEX is useful for integration. It is not the consolidated SIP market. Top-of-book pressure, volume, and event order may differ across feeds. A result on IEX should therefore keep the feed in its provenance.

## 8. My leadership of core contributions and AI-assisted development

I led the selection of MarketStream’s core solution and its development priorities, scope, key design constraints, and verification requirements. I prioritised the backend pipeline, selected eight factors across three time windows with six CEP patterns as the detection architecture, and drove core simplification and modularisation. I directly specified baseline persistence, retention of the latest 20 trading days per cell, three explicit startup modes, and recovery requirements. I also required real-data evaluation, anomaly intervals identified in advance, and visual replay.

AI served as an auxiliary development tool: it provided technical advice, helped elaborate proposals, generated and refactored code, executed tests and debugging, and drafted and revised report text. AI contributed specific proposals for the factors, windows, patterns and explicit state-machine refactoring; implementation proceeded after my approval. Those proposals and generation records remain identified in the provenance materials.

My core contributions are solution selection, concrete problem and constraint design, development trade-offs, verification requirements, and report revision decisions. The contribution matrix separately evidences requirements I directly proposed and advice I chose to adopt, linking my decisions, AI assistance, and the resulting code and experiment artifacts.

My directly recorded decisions include backend priority and modular simplification; baseline database storage, 20-day retention and explicit startup modes; challenging metric provenance and requiring prior labels and HTML replay; and report requirements for anomaly definitions, individual citations, metric units, denominators and separate tables. AI proposed the detailed eight-factor / three-window / six-pattern design and six-machine refactoring, which I approved for implementation. AI generated and refactored code, executed tools, debugged issues, and drafted substantial reference-report text.

My personal contribution claim concerns these choices, concrete requirements, and revision decisions. The extent of my manual code and paragraph authorship is not fully established. The [attribution matrix](08_Contribution_Attribution_Matrix_EN.md) D01–D10 links every decision to my messages, AI work and artifacts, and marks unresolved claims. Git records establish versions and tests establish behaviour; neither substitutes for authorship evidence. Public methods and third-party platforms retain their original attribution.

## 9. Conclusion and future work

MarketStream is an inspectable research prototype. It combines a shared event contract, data quality, eight factors over three windows, a five-part baseline, six CEP state machines, persistent baseline design, and traceable results.

Current tests and controlled experiments show that the implementation behaves as designed. They also reveal a false-alert source and an unused factor group. Historical soak and IEX records support the engineering path. They do not show real-market accuracy or production reliability.

The next priority is to finish independent label review and freeze the real replay package. The project should then compare CEP and ML under one protocol. A current soak should also be rerun when Kafka and PostgreSQL are available. Longer real-input runs and SIP data would improve coverage.

## References

[1] Barrie, A. C., et al. (2025). *The Module for Event Driven Operations on Spacecraft (MEDOS)*. NASA Technical Reports Server, 20250002215.

[2] Bhattacharya, D., et al. (2024). *Towards Unbiased Evaluation of Time-series Anomaly Detector*. arXiv:2409.13053.

[3] Cont, R., Kukanov, A., & Stoikov, S. (2014). The Price Impact of Order Book Events. *Journal of Financial Econometrics, 12*(1), 47–88.

[4] Drew, B. J., et al. (2014). Insights into the Problem of Alarm Fatigue with Physiologic Monitor Devices. *PLOS ONE, 9*(10), e110274.

[5] Guha, S., et al. (2016). Robust Random Cut Forest Based Anomaly Detection on Streams. *PMLR 48*, 2712–2721.

[6] Gyllstrom, D., et al. (2006). *SASE: Complex Event Processing over Streams*. arXiv:cs/0612128.

[7] Liu, Q., & Paparrizos, J. (2024). The Elephant in the Room: Towards a Reliable Time-Series Anomaly Detection Benchmark. *NeurIPS 37*.

[8] MacKinlay, A. C. (1997). Event Studies in Economics and Finance. *Journal of Economic Literature, 35*(1), 13–39.

[9] Manzoor, E., Milajerdi, S. M., & Akoglu, L. (2016). Fast Memory-efficient Anomaly Detection in Streaming Heterogeneous Graphs. *KDD 2016*.

[10] Powell, D., et al. (2020). *NISTIR 8219: Securing Manufacturing Industrial Control Systems: Behavioral Anomaly Detection*.

[11] Prytherch, D. R., et al. (2010). ViEWS—Towards a National Early Warning Score for Detecting Adult Inpatient Deterioration. *Resuscitation, 81*(8), 932–937.

[12] Tetlock, P. C. (2007). Giving Content to Investor Sentiment: The Role of Media in the Stock Market. *Journal of Finance, 62*(3), 1139–1168.
