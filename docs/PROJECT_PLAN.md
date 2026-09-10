# MarketStream Backend-First Project Plan

The active research direction is an explainable factor-and-CEP system. The previous four-model ensemble is retained as an offline/shadow baseline, not as the production decision path.

## Priority order

1. Freeze the research question and leakage-resistant evaluation protocol.
2. Stabilize unified events, quality flags, live/replay parity, and historical inputs.
3. Compute eight bounded-memory factors at 10-second, 1-minute, and 5-minute cadences.
4. Use six stateful CEP patterns with directional cooldown and deduplication.
5. Validate real events, synthetic sequences, negative controls, latency, and alert burden.
6. Redesign the frontend only after event, factor, pattern, alert, and evaluation interfaces are stable.

## Implemented backend contracts

- `MarketEvent` is the common live/replay wire format.
- `FactorSnapshot` is source-independent and CEP-independent.
- `CEPDetector.process()` returns a traceable `DetectionResult`.
- Kafka topics are `raw.market_events`, `stream.factor_snapshots`, and `stream.anomalies`.
- Five-minute snapshots continue emitting `stream.features` for legacy consumers.
- Database changes are applied through idempotent migrations.

## Evaluation gates

- Chronological 60/20/20 split; thresholds freeze before testing.
- One-to-one forward event matching; no pre-event hit credit.
- Twenty seeds and three intensities across six sequence anomalies.
- Negative controls for isolated volume, orderly broad moves, stale news, and post-market spread.
- Event precision/recall/F1, detection delay, alert burden, duplicate rate, end-to-end p50/p95/p99, and bootstrap intervals.
- Unit/in-process CEP p99 ≤ 5 ms.
- Infrastructure soak-test target: p95 receipt-to-persistence ≤ 15 seconds, ≤ 2 alerts/ticker/hour on normal validation periods, and ≤ 5% cooldown duplicates.

## Frontend gate

Until the backend gates pass, Streamlit receives compatibility-only changes: current method wording, CEP evidence display, and obvious bug fixes. Navigation, theme, layout, and rich interaction remain deferred.

See [PROJECT_GUIDE_CN.md](PROJECT_GUIDE_CN.md) for the detailed Chinese orientation and operating guide.
