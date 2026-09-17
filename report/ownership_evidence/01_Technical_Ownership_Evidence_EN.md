# MarketStream Technical Ownership Evidence

Prepared: 17 September 2026  
Working branch: `codex/core-simplification`  
Base commit: `bb0df67fad42ef6cf4c544b5e3711d57cd32f3fd`  
Project status: research prototype and technical validation

## 1. Purpose

This document explains my understanding and contribution. It does not claim that I typed every line alone. I used AI, public research, open-source libraries, and third-party data services. My claim is more limited. I identified and checked project problems. I set constraints. I reviewed generated work. I ran tests. I also challenged results that did not have enough evidence.

| Supervisor concern | Main section | Primary evidence |
|---|---|---|
| Literature verification | Section 8 | Paper pages, sections, and official links |
| Architecture understanding | Sections 2–5 | Current code, tests, and design records |
| Technical contribution | Section 6 | Git, code, tests, and AI task records |
| Experiment understanding | Section 7 | Commands and raw JSON outputs |

## 2. Problem and scope

MarketStream processes streaming market events. It does not predict future returns. It does not place trades. Its purpose is to identify unusual event combinations for later human review. It also keeps the evidence behind each result.

A fixed price threshold is not enough. Different stocks have different normal volatility. The market open is also different from the middle of the day. A stock move may follow the whole market. It may not be stock-specific.

The system first calculates eight simple factors. It compares them with the earlier state of the same stock and intraday context. CEP state machines then check direction, order, duration, and cross-asset relations.

The current core flow is:

```text
MarketEvent
  → Quality Gate
  → FactorSnapshot (10 s / 1 min / 5 min)
  → six CEP state machines
  → DetectionResult
  → Kafka / TimescaleDB / Streamlit
```

The current evidence supports three points. The code passes 62 tests and Ruff. Controlled sequences exercise the six patterns. An earlier IEX run shows that real input can enter the pipeline and create all three snapshot cadences.

The evidence does not support real-market Precision, Recall, or F1. Real labels are not independently reviewed and frozen. IEX is not the full SIP market. An 88-second run is not long-term production evidence. The old injected comparison also does not prove that current CEP is better than ML in real markets.

## 3. Data flow and component roles

### 3.1 MarketEvent and Quality Gate

`MarketEvent` gives trade, quote, bar, and news a common contract. It keeps event time, receive time, source, feed, event ID, run ID, and provenance. The Quality Gate marks duplicates, out-of-order events, stale data, invalid prices, crossed quotes, zero volume, and feed gaps.

The system does not silently repair these issues. Severe quality flags suppress alerts. Raw events remain available for review. A minute bar uses the start of its interval as its timestamp. The code therefore gives bars a 60-second close grace. This avoids a false stale flag.

### 3.2 FactorSnapshot

The Factor Engine uses 10-second, 1-minute, and 5-minute windows. It calculates eight factors:

1. return surprise;
2. volatility burst;
3. relative volume;
4. spread stress;
5. quote imbalance;
6. signed trade imbalance;
7. market residual;
8. news shock.

Each snapshot also stores factor states, directions, baseline version, quality status, and source event IDs. A DetectionResult can therefore be traced back to its inputs.

### 3.3 CEP state machines

The current core does not use one large general NFA. It uses six small state machines. They represent stock-specific dislocation, liquidity pressure move, news-confirmed move, flash reversal, sustained pressure, and cross-asset shock.

The state machines handle a limited set of event relations. They do not calculate factors again. The detector also applies warm-up suppression, quality suppression, a 300-second cooldown, deterministic deduplication, severity, and evidence IDs.

### 3.4 Kafka, TimescaleDB, and Streamlit

- Kafka moves events between collection, factor calculation, and detection services.
- TimescaleDB stores raw events, snapshots, results, and baseline state.
- Streamlit displays prices, factors, alerts, and comparisons. It does not make the core decision.

## 4. Main architecture decisions

### 4.1 CEP or the old four-model ensemble

**Problem.** The old path used EWMA, Half-Space Trees, Isolation Forest, and an LSTM autoencoder. It produced several scores, but event order was difficult to explain.

**Options.** Keep the ensemble, add more models, use a general NFA, or use simple factors with a small number of state machines.

**Choice.** The current online path uses factors and six CEP state machines. Old ML results are historical comparisons only.

**Reason.** Rules can directly describe a move after news, pressure across windows, or a cross-asset event. A large NFA was not needed for the present project size.

**Cost.** Rule parameters still need calibration. A single-factor extreme exception can create false alerts. CEP is not automatically more accurate than ML.

**Evidence.** `cep/state_machines.py`, `evaluation/run_synthetic.py`, the current synthetic JSON, and the old comparison JSON.

### 4.2 Three time windows

**Problem.** One window cannot represent a quick shock, short persistence, and slower context at the same time.

**Choice.** Use 10 seconds, 1 minute, and 5 minutes.

**Reason.** These cadences separate quick and sustained behaviour. They also keep the state size manageable.

**Cost.** They have not been shown to be optimal on frozen real labels. Evidence near a boundary may also repeat.

### 4.3 Median, MAD, and empirical quantiles

**Problem.** Mean and standard deviation can be affected by extremes. An empirical quantile alone can be unstable with little data.

**Choice.** Store median, MAD, and the 0.995 and 0.999 quantiles. Use `scale=max(1.4826×MAD,1e-6)`. The elevated level uses the stricter result from the 0.995 quantile and 4×scale. The extreme level uses the stricter result from the 0.999 quantile and 6×scale.

**Reason.** Median and MAD are robust. Quantiles keep information from the observed distribution. The value 1.4826 is the normal-consistency scale for MAD. It is not a meaningless conversion number.

**Cost.** These are engineering settings. They are not proven optimal for real market labels.

### 4.4 Five-part baseline key

**Problem.** A factor has a different normal range for different stocks, cadences, sessions, and times of day.

**Choice.** Use `(ticker, cadence, market_session, intraday_slot, factor_name)`.

**Reason.** This avoids comparing the market open with midday. It also avoids mixing an ETF and a single stock.

**Cost.** There are more cells and fewer samples in each cell. Warm-up and state recovery are therefore required.

### 4.5 Warm-up, score-before-update, and freezing

**Problem.** If a current observation enters the baseline before scoring, it can reduce its own anomaly level.

**Choice.** A cell needs five earlier trading days. The engine scores first and updates later. An evaluation imports the baseline and then uses `freeze=True`.

**Cost.** A new deployment or ticker has a period with no eligible alerts.

### 4.6 Six state machines

**Problem.** A threshold crossing is only a local signal. It may not be a useful market event.

**Choice.** Use six finite patterns. News confirmation keeps news for five minutes. Flash reversal needs two opposite price events within two cadences. Sustained pressure needs three distinct windows in the latest four frames. Cross-asset shock needs at least three tickers within 60 seconds, including SPY or QQQ.

**Cost.** Patterns depend on sampling and missing data. The extreme path in `stock_specific_dislocation` is the main source of current negative-control alerts.

### 4.7 Cooldown, deduplication, and traceability

**Problem.** One event can produce repeated alerts in adjacent snapshots.

**Choice.** The same ticker, pattern, and direction are merged for 300 seconds. The deduplication key also contains the pattern start time. Results keep factor evidence and event IDs.

**Cost.** A second real event inside the cooldown may be merged. The result therefore keeps the suppression reason.

### 4.8 Baseline epoch and recovery

**Problem.** An in-memory baseline is lost after a restart. A partial database recovery can also mix incompatible state.

**Choice.** Startup must state COLD_START, VERIFIED_BACKFILL, or RESTORE. Baseline, runtime, and offsets belong to one epoch and revision. A checkpoint has a manifest and checksum.

**Reason.** Startup state should not be guessed. An inconsistent state should stop or follow an explicit recovery path.

**Cost.** Operations are more complex. There is no long production recovery record yet.

### 4.9 IEX and SIP

**Problem.** An available real-time source is not the same as a consolidated market feed.

**Choice.** Use Alpaca IEX for integration testing and record the feed in provenance.

**Cost.** IEX covers one venue. Its quotes, volume, and event order can differ from SIP.

## 5. Two algorithm details

Trade direction first uses an upstream side when available. Otherwise, the trade price is compared with the latest bid/ask midpoint. A price at or above the midpoint is counted as buy volume. A lower price is counted as sell volume. If there is no side and no midpoint, the volume does not enter the signed numerator. This is a transparent approximation. It is not a full Lee–Ready implementation.

The online news score is not FinBERT. It uses a small positive and negative word list:

```text
sentiment = (positive_count - negative_count)
            / (positive_count + negative_count)
news_shock = sentiment × log(1 + headline_count)
```

The score is zero when there are no matched words. It is easy to inspect, but it has weak context and negation handling.

## 6. My six main contributions

The full records are in `02_Technical_Contribution_Log_CN.md`.

| Area | My judgement or check | AI role | Evidence |
|---|---|---|---|
| Event, quality, traceability | Confirmed the shared contract and provenance; found the stale-bar issue | Helped refactor and test | Event models, quality tests, IEX output |
| Factors and baseline | Checked the five-part key, 20 days, five-day warm-up, thresholds, and freeze | Helped implement | Factor code and tests |
| CEP and alert control | Selected explicit states and examined the false-alert source | Helped implement and run experiments | State machines and synthetic JSON |
| Baseline persistence | Identified restart loss; proposed DB recovery, epochs, and startup constraints | Implemented from these constraints | `baseline/` and seven tests |
| Leakage-safe replay | Challenged metric provenance; required prior labels, freezing, and event matching | Helped implement | Replay validator and draft registry |
| IEX/Kafka/DB chain | Separated integration evidence from accuracy; checked stale bars and soak history | Helped run and diagnose | Live E2E and soak artifacts |

I do not describe these as fully hand-written work. A more accurate account is that I raised or confirmed the problem, gave constraints, checked AI-generated changes, ran tests, challenged weak results, and requested revisions.

## 7. Experiments and limitations

### 7.1 Current synthetic protocol

I reran 20 seeds on 17 September 2026. The raw file is `reproduction_outputs/factor_cep_current_20260917.json`.

| Metric | Result |
|---|---:|
| TP / FP / FN | 360 / 120 / 0 |
| Precision / Recall / F1 | 0.750 / 1.000 / 0.857 |
| Delay p50 / p95 / p99 | 10 / 30 / 30 s |
| CEP compute p50 / p95 / p99 | 0.0131 / 0.0188 / 0.0299 ms |

The 120 false positives are extra unmatched alerts in positive scenarios. The `40/240` result is from a separate set of negative controls. They are not the same set.

All 20 seeds have the same result because the current generator mostly changes identifiers and time shifts. It does not materially change pattern shape or amplitude. This shows repeatability of the script. It does not show real-market stability.

Removing `stock_specific_dislocation` changes TP from 360 to 300 and FP from 120 to 0. The detector misses 60 generated anomalies. This is a trade-off between early single-factor alerts and multi-signal confirmation. Removing activity has no effect because `relative_volume` is not a critical completion condition in the six current rules.

### 7.2 Old ML comparison

The old comparison used real OHLCV background with injected anomalies. CEP full had F1 0.785 and the ML ensemble had F1 0.639. The old compatibility protocol measured 0.0033 ms mean CEP compute time. These values describe an older protocol. They do not prove that current CEP is generally better on real markets. They also should not be combined with the current 0.0131 ms result.

### 7.3 Soak and live input

I could not rerun the soak in this work session. The local Docker/Colima socket was unavailable. The latest saved run is dated 10 September 2026. It has 240 inputs, 76 alerts, p95 latency of 1.616 seconds, and no duplicates. The older 6 August run has 88 alerts and p95 latency of 1.718 seconds. The first failed 15-alert gate is also kept.

The IEX run lasted about 88 seconds. It stored 48,734 events. It created forty 10-second snapshots, five 1-minute snapshots, and five 5-minute snapshots. This supports integration and cadence generation. It had no ground truth and remained in warm-up. It does not support detection accuracy.

### 7.4 Formal real replay

Formal replay requires 12 abnormal and 12 normal intervals to be independently reviewed and frozen. It also verifies the data manifest, checksums, feed, baseline period, and evaluation period. The current registry is still a draft. The system therefore refuses to create formal real Precision, Recall, and F1. This is an intended evaluation guard.

## 8. Literature, AI, and responsibility

I verified the twelve report references against their source pages and sections. They support design motivation. They do not prove MarketStream. For example, Cont et al.'s OFI is not the same as the present simplified imbalance. MacKinlay's formal abnormal return is not the same as `r_i-r_m`. The detailed table is in `04_Literature_Verification_CN.md`.

AI helped with code generation, debugging, experiments, structure, and language. My responsibility was to state problems and acceptance conditions, then check the outputs. The project AI task index is in `05_AI_Log_Index_CN.md`. Claude history is not currently available and is not reconstructed. Private chats and unrelated projects are outside this submission.

Public papers provide method background. Alpaca provides the IEX interface. Kafka, PostgreSQL/TimescaleDB, Streamlit, and Python packages are third-party tools. My supervisor requested clearer ownership evidence, but has not approved this exact package format.

## 9. Remaining work

1. Complete independent review and freezing of the real event labels.
2. Rerun the current soak with a working Kafka and PostgreSQL stack.
3. Test the IEX path across more days and longer sessions.
4. Compare CEP and ML on one frozen real dataset and one shared protocol.
5. Add the full available account export when it arrives.

## 10. Questions I should be able to answer

1. Why is 1.4826 used? It is the normal-consistency scale for MAD. It is still an engineering approximation here.
2. Why score before updating? It prevents a current observation from changing its own threshold.
3. Why are 20 seeds identical? The varying parts do not change the rule structure. This is not independent market evidence.
4. How are 120 FP and 40/240 different? One is unmatched alerts in positive cases. The other is a separate negative-control suite.
5. Why does removing dislocation increase precision and reduce recall? The extreme single-factor path gives early alerts but also false alerts.
6. Why does the activity ablation have no effect? Relative volume is not a required completion condition in the six rules.
7. What does the IEX run prove? It proves input integration and snapshot generation, not real detection accuracy.
8. Why is the old ML result insufficient? It used another implementation, protocol, and injected labels.
9. What happens after restart? Startup must use an explicit mode and verify epoch, checksum, and offset state.
10. Which code did AI write? I should answer from the log and contribution table. Git authorship alone is not proof of manual typing.

## Conclusion

The current work is an inspectable research prototype. It has a shared event contract, a quality gate, eight factors over three windows, a five-part baseline, six CEP patterns, persistent baseline design, and traceable results. Synthetic and historical engineering experiments test implementation behaviour. They do not yet prove real-market effectiveness. My technical ownership is mainly in problem identification, design constraints, challenge of results, validation, and clear limits.
