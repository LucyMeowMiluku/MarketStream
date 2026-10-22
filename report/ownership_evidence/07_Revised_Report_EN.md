> Audit, 22 October 2026: [07_Revised_Report_CN.md](07_Revised_Report_CN.md) is the sole report master; English is a companion translation. Use the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md) and [registry](reproduction_outputs/audit_20261022/result_registry.json) for numbers and missing provenance. Historical runs are not current-system results.

# MarketStream: Real-Time Market Anomaly Detection with Lightweight Factors and CEP

## Abstract

Market data is noisy and fast. Its quality is also uneven. A fixed price threshold is not enough. It cannot tell whether a move is stock-specific, market-wide, news-related, or caused by weak input data. A large model ensemble can provide several scores, but it can also be difficult to explain and maintain.

This project presents MarketStream. It is a research prototype for real-time market anomaly monitoring. The current flow is:

```text
MarketEvent → Quality Gate → FactorSnapshot → CEP State Machines → DetectionResult
```

Trade, quote, bar, and news events use one data contract. The system calculates eight factors over 10-second, 1-minute, and 5-minute windows. It then applies six explicit CEP patterns. Results keep factor evidence and source event IDs.

The evidence is reported by type. Before revision, the synthetic protocol gave Precision 0.750, Recall 1.000, and F1 0.857, and 40 of 240 negative-control cases alerted; every false positive came from a rule letting a single extreme return complete a pattern. Removing that exception before any real replay, as the pre-declared rule change of project-plan item 4 (one pre-declared rule change based on the negative-control false alarms), gives Precision, Recall, and F1 of 1.000 and 0 of 240 alerting controls on the same protocol. Because the change was chosen from those controls, the revised result is an in-sample check of the implementation only. Current CEP computation has p50 0.0132 ms and p99 0.0259 ms. An older five-minute injected protocol reported CEP F1 0.785 and ML ensemble F1 0.639. This old result does not prove that current CEP is better on real markets.

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

A minute bar's provider timestamp marks the start of its interval, but the bar only completes at the end of the minute and arrives after that. Keying it by its start put the whole minute's open, high, low and close into the first 10-second window of that minute in replay (future information), while live bars arrived late, so the two modes diverged. Bars now carry their interval explicitly in the payload; the event time is the completion time (interval end); the receive time is the observed arrival in live mode and, because the historical API has no publication time, the completion time in replay, marked as assumed in provenance. A bar only contributes to a window that contains its whole interval, so 10-second and 1-minute windows never use minute bars and 5-minute windows use the minutes completed inside them. First and last prices follow observation time (a bar's open at its start, its close at its end), so a late bar cannot overwrite a later trade, and live and replay give the same window. Staleness is measured from completion, with no separate bar grace; the converter version became `alpaca-market-event-v2`.

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
| Stock-specific dislocation | stock return and market residual agree in the same window |
| Liquidity pressure move | spread and imbalance pressure confirm a price move |
| News-confirmed move | price follows news direction within five minutes |
| Flash reversal | opposite price events occur within two cadences |
| Sustained pressure | pressure appears in three distinct windows among the latest four |
| Cross-asset shock | at least three tickers move in one direction within 60 seconds, including SPY or QQQ |

The detector also checks warm-up and data quality. It applies a 300-second cooldown to the same ticker, pattern, and direction. Results keep evidence IDs and suppression reasons. The formal CEP versus Isolation Forest comparison replaces this cooldown with one alert policy shared by both methods (Section 6.7).

An earlier version also completed stock-specific dislocation when the return alone was extreme. Without the market residual, that exception cannot separate a stock-specific move from a market-wide one, and it caused every synthetic false positive (Section 6.3). It was removed before any real replay. A single extreme return now remains an atomic event and an in-progress clue.

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

`return_surprise` is normalised twice: the current return is scaled by the raw-return history, and the resulting score is then compared with its own history. With fewer than five days of raw returns the MAD is usually zero, the scale collapses to its numeric floor, and scores are inflated by up to about 10^6. An earlier version recorded those inflated scores, which then set the factor's threshold for about 20 sessions (from roughly 4 to roughly 508 in a simulation) while snapshots were already marked ready. `return_surprise` is now unobserved, not recorded and kept in warm-up until five days of raw returns exist. It starts its own history on day 6 and is ready on about day 11; the other seven factors still need five days. A 20-day replay baseline therefore leaves 15 days of `return_surprise` history on the evaluation day. Together with the zero-MAD rule (Section 4.4) this is baseline algorithm version `rolling-mad-v4`, so older epochs cannot be restored.

This structure avoids mixing different stocks, windows, sessions, and times of day. It also creates many small cells. Some cells may remain in warm-up.

### 4.4 Median, MAD, and thresholds

For historical values \(X\), the robust scale is:

\[
scale=\max(1.4826\times MAD(X),10^{-6})
\]

The value 1.4826 is the normal-consistency scale for MAD. It does not mean that market factors are normally distributed.

For the raw-return scale behind `return_surprise`, the numeric floor is not enough. IEX trades are sparse, so many 10-second windows contain only quotes and a return of exactly zero. In a disjoint 2023-Q4 calibration set the MAD of the raw-return cell was zero for 56.1% of 10-second, 33.9% of 1-minute and 5.2% of 5-minute windows. The scale then collapsed to 10^-6 (0.01 basis points), a one-tick move scored in the thousands, and 80.5% of CEP alerts came from such windows. The raw-return scale is therefore:

\[
scale_r=\max\Big(s,\ \frac{0.01}{P_{ref}}\Big),\quad s=1.4826\,MAD(X)\ \text{if}\ MAD(X)>0,\ \text{else}\ 1.2533\,\mathrm{mean}|x-\mathrm{median}(X)|
\]

1.2533 (√(π/2)) converts the mean absolute deviation to a normal standard deviation, the usual fallback for modified z-scores when MAD is zero. 0.01/P_ref is one minimum price increment as a return, the smallest observable change, so the floor comes from market rules rather than tuning. The rule was declared before the calibration results (Section 6.8). Per-factor classification keeps the formula above.

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

Source bindings: 6.1=CHECKS-20261023; 6.2=SYN-TRACE-20261023 for current results and SYN-TRACE-20261022 for the pre-revision column (`factor_cep_traced.json`, `scenarios.json`); 6.3=SYN-SUITE-20261023 and SYN-SUITE-20261022 (`factor_cep_suite.json#/ablations`); 6.4=LEGACY-INJECTED (`methods`); 6.5=the three original `soak-*/report.json`; 6.6=`alpaca_live_e2e.json`. The abstract and conclusion repeat these runs. All seven provenance fields, file hashes and missing historical fields are recorded in the [run ledger](Evidence_Attachments/Result_Run_Ledger_20261022.md).


### 6.1 Tests and static checks

CHECKS-20261023, on the archived audit source snapshot, produced:

```text
91 passed in 5.01s
All checks passed (Ruff)
```

CHECKS-20261022 reported 63 passed; the additional tests cover the warm-up fix, the zero-MAD return scale, minute-bar timing, the shared alert policy, cross-asset cadence separation, quality-flag consistency, high-intensity negative controls and the label review tools. The September 17 summary reported 62 tests. The older 160-test statement has no complete run binding and is not current evidence.

### 6.2 Synthetic detection

Two runs use the same generator, seeds, matching rule and cooldown=0 protocol: SYN-TRACE-20261022 before the rule revision and SYN-TRACE-20261023 for the current implementation.

| Metric | Before revision | Current |
|---|---:|---:|
| TP | 360 | 360 |
| FP | 120 | 0 |
| FN | 0 | 0 |
| Precision | 0.750 | 1.000 |
| Recall | 1.000 | 1.000 |
| F1 | 0.857 | 1.000 |
| alerting negative-control cases | 40 / 240 | 0 / 240 |
| first detection p50 / p95 / p99 | 10 / 30 / 30 s | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0150 / 0.0306 / 0.0688 ms | 0.0132 / 0.0178 / 0.0259 ms |
| alerts per ticker-hour | 1.604 | 1.815 |
| duplicate rate | 0 | 0 |

Before revision, the 120 FP comprised 60 unmatched alerts in positive scenarios (high-intensity flash reversal 20, cross-asset shock 40) and 60 alerts in negative controls (high-intensity orderly market move 40, stale news 20). The 240 controls emitted those 60 alerts across 40 alerting cases, so 40/240 is a case rate and the 60 control alerts are already included in the 120 FP. Every one of the 120 came from the single-extreme-return exception: high intensity makes return surprise extreme, and the exception completed stock-specific dislocation on any such snapshot.

The current perfect scores are not evidence of detection ability. The generator and the rules encode the same patterns, the rule change was chosen from these very controls, so the revised control result is in-sample, and the protocol is now saturated and cannot rank rule variants. It serves as an implementation regression check only.

The bootstrap resamples truth-hit indicators while holding FP fixed. All truth events are matched in both runs, so its interval collapses. It does not estimate normal-period false-alert uncertainty or establish stability across seeds. Alerts per ticker-hour divide by the first-to-last time span times the number of tickers involved; the earlier false alerts on SPY enlarged that ticker set, which is why the value rises after the revision. It cannot be read as a real alert burden. Zero duplicates with detector cooldown=0 does not validate production cooldown.

### 6.3 Ablations

| Setting | Precision | Recall | F1 | alerting controls |
|---|---:|---:|---:|---:|
| Before revision, full method (SYN-SUITE-20261022) | 0.750 | 1.000 | 0.857 | 16.7% |
| Before revision, whole dislocation pattern removed | 1.000 | 0.833 | 0.909 | 0.0% |
| Current, only the exception removed (SYN-SUITE-20261023) | 1.000 | 1.000 | 1.000 | 0.0% |

The earlier draft read the 60 misses from removing the whole pattern as the value of the extreme exception. That attribution was wrong. Those 60 are the dislocation scenarios, which complete through return surprise and market residual agreeing at every intensity; they do not need the exception. Removing only the exception keeps all 60 and removes every false alert. In this protocol the exception added no detections and only false alerts. Whether it would find some real events earlier cannot be answered here.

Current group ablations (SYN-SUITE-20261023) produce no false alerts, so Precision stays at 1.000 and only Recall moves. Removing price gives no completed detections. Removing liquidity or all microstructure factors lowers Recall to 0.667 (F1 0.800). Removing news lowers Recall to 0.833 (F1 0.909). Removing market context also gives Recall 0.833: dislocation now requires the residual, whereas before the revision 20 high-intensity dislocation cases completed through the exception (Recall 0.889).

Removing the activity group has no effect. `relative_volume` is not a critical completion condition in the six current patterns. A factor can have a reasonable financial meaning but still have no measured role in the current rules.

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

The replay protocol fixes how the comparison will be run once labels are frozen. Each interval uses a baseline of the 20 prior sessions at the same time of day, frozen before evaluation. Both methods are scored only on the reviewed ticker; context tickers such as SPY and QQQ only feed factors and cross-asset shock. Isolation Forest is fitted per interval on that ticker's post-warm-up baseline snapshots. Both methods first produce raw per-window detections. One shared alert policy then gates out warm-up and critical-quality windows and merges detections for the same ticker and direction within 300 seconds of an emitted alert, so precision differences are not driven by different post-processing; CEP's own per-pattern cooldown is not used here. Every run writes `window_detections.jsonl` with one row per scored window and method (score, fired flag, pattern, direction, policy outcome, raw and alert match), and `detector_comparison.json` reports both policy-level and raw per-window metrics. Zero-MAD handling: the raw-return scale uses the pre-declared, sensitivity-checked rule of Section 4.4, fixed before the protocol is frozen.

Labels follow objective criteria approved before any candidate data was shown (`docs/LABELING_CRITERIA.md`). Consolidated SIP minute bars give each interval's total move, volume and range against the median of the same ticker and clock window over the previous 20 sessions. An anomaly needs a move at least 4× typical, a publicly documented cause, a clear direction and complete data; a normal control needs price, volume and the market within 1.5× typical, no company news and no major macro release. Everything else is excluded and replaced. The review interface hides the draft labels and shows no detector output.

### 6.8 Zero-MAD sensitivity check (unlabelled calibration)

Rule, variants and criteria were committed before the results. Data: Alpaca IEX, 30 sessions from 2023-10-02 to 2023-11-10, five tickers, 09:30–11:00 and 14:00–15:30, disjoint from all candidates, their baselines and the holdout. The first 20 sessions only build the rolling baseline; the last 10 are measured (65,081 windows, 150 ticker-hours) through the full quality gate, factors, CEP, Isolation Forest and the shared alert policy. With no labels, the check asks only whether the scale rule drives or distorts the output.

| Rule | CEP alerts with scale at floor | IF alerts with scale at floor | CEP Jaccard, floor ×0.5 / ×2 | Price-atom rate, MAD=0 vs other windows |
|---|---:|---:|---:|---:|
| Old rule (floor 10^-6) | 80.5% | 29.2% | — | 4.44 |
| Adopted: MeanAD fallback + one-tick floor | 22.6% | 24.3% | 0.91 / 0.85 | 1.54 |
| Declared alternative: no score when MAD=0 | 43.0% | 36.2% | — | 0.00 |

Under the old rule |z| in zero-MAD windows reached 2,159 at the 99th percentile and 83,065 at the maximum. The adopted rule passed the stability criterion (alert counts change by at most 1.4% between half and double the floor) and the distortion criterion (1.54 ≤ 2), but failed the floor-dominance criterion: about a quarter of alerts come from windows where the floor is the binding bound (limit 5%). The floor's value barely changes alerts within a plausible range, but it is the active bound there, and that failure is reported as is. The declared alternative also failed it, switched the price factor off in over half of the 10-second windows and removed 42% of CEP alerts, so the project lead chose the primary rule under the pre-declared procedure. Without minute bars the conclusion holds (atom-rate ratio 4.09 → 1.41). In the calibration period, CEP produced about 5.6 and Isolation Forest about 5.9 alerts per ticker-hour under the shared policy; without labels these are an alert-burden reference only and change no detection rule.

## 7. Discussion

### 7.1 Where the complexity moved

The project did not replace ML with one fixed threshold. It moved complexity from several models and weighted scores into factor meaning, baseline context, direction, time order, persistence, and alert control.

This makes each result easier to inspect. It does not remove the need for calibration.

### 7.2 Negative results matter

The negative controls showed that the single-extreme-return dislocation exception was too permissive; it was removed before any real replay as the pre-declared rule change of project-plan item 4. The plan does not limit other rule changes before the protocol is frozen. Before the freeze, any further change must be justified, documented and based only on data disjoint from the evaluation intervals, without detector outputs from those intervals. Once the protocol is frozen, all detector parameters stay fixed for that evaluation run, and any later change requires a new version and validation on an independent holdout. Real evaluation may therefore still reveal events that only show one extreme return without a residual; those must be reported as misses rather than fixed on the same test set. The activity ablation shows that one factor currently has no critical rule role. These results are kept because they affect the next design decision.

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
