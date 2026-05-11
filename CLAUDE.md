# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # Install all dependencies
uv run pytest tests/ -v               # Run all tests
uv run pytest tests/test_feature_engine.py -v  # Run a single test file
uv run ruff check .                   # Lint
docker-compose up -d                  # Start Kafka + TimescaleDB + Kafka-UI
bash scripts/create_topics.sh         # Create Kafka topics (required before producers)
uv run python -m storage.init_db      # Create tables + hypertables
uv run python -m ml.train_baseline    # Train IsolationForest on 30-day historical data
uv run python -m ml.train_lstm        # Train LSTM Autoencoder on historical data
uv run python -m ml.retrain           # Retrain IsolationForest with model versioning
uv run python -m ml.backtest          # Run offline backtest with synthetic anomaly injection
bash scripts/start_all.sh             # Start full pipeline (infra + all processes)
uv run streamlit run dashboard/app.py --server.port 8501 --server.headless true
```

## Architecture

Data flows through five independently-running Python processes connected by Kafka:

1. **price_producer** — polls yfinance every 60s, produces OHLCV to `raw.prices`
2. **news_producer** — polls yfinance news every 120s, runs FinBERT sentiment, produces to `raw.news_sentiment` AND writes directly to TimescaleDB `sentiment_scores` table
3. **stream_app** — Quix Streams consumer on `raw.prices`, 5-min tumbling windows with 30s grace period, computes features via `feature_engine.py`, produces to `stream.features`
4. **online_scorer** — consumes `stream.features`, enriches with sentiment by querying DB (last 20 headlines), runs **4-detector ensemble** (EWMA, HST, IsolationForest, LSTM AE), writes `FeatureVector` to DB always and `AnomalyAlert` + Kafka `stream.anomalies` on anomaly. Also runs ADWIN drift monitor.
5. **Streamlit dashboard** — queries TimescaleDB directly, auto-refreshes via `@st.fragment` (5-10s intervals). 6 pages: Home, Price Chart, Sentiment Feed, Anomaly Alerts, Comparison, Model Health.

The dashboard does NOT consume Kafka — it reads from TimescaleDB only.

### Ensemble Anomaly Detection

The online_scorer uses `EnsembleDetector` which combines 4 detectors via weighted voting:

| Detector | Module | Weight | Online |
|----------|--------|--------|--------|
| EWMA | `ml/detectors/ewma_detector.py` | 0.2 | Yes |
| Half-Space Trees | `ml/detectors/hst_detector.py` | 0.3 | Yes |
| Isolation Forest | `ml/detector.py` | 0.3 | No (batch) |
| LSTM Autoencoder | `ml/detectors/lstm_detector.py` | 0.2 | No (buffer) |

All detectors implement `BaseDetector` (in `ml/base_detector.py`) with `score()`, `update()`, and `name`. Scores follow: lower (more negative) = more anomalous. Threshold default: -0.3.

LSTM returns 0.0 during warm-up (first 12 observations per ticker); the ensemble excludes it from the weighted average until ready.

### Model Maintenance

- **Drift detection**: `ml/drift_monitor.py` uses ADWIN (river library) per feature per ticker. Writes `DriftEvent` rows on drift.
- **Retraining**: `ml/retrain.py` retrains IsolationForest, saves versioned model, records in `model_versions` table.
- **Data utils**: `ml/data_utils.py` has shared `download_historical()` used by both `train_baseline.py` and `retrain.py`.

### Database Tables

| Table | Type | Key columns |
|-------|------|-------------|
| `price_ticks` | Hypertable (time) | time, ticker, OHLCV |
| `sentiment_scores` | Hypertable (time) | time, ticker, headline, sentiment_score |
| `feature_vectors` | Hypertable (window_end) | window_end, ticker, features, anomaly_score, detector_scores (JSON) |
| `anomaly_alerts` | Regular | detected_at, ticker, anomaly_score, features, reason, detector_scores (JSON) |
| `drift_events` | Regular | detected_at, ticker, feature_name, drift_type |
| `model_versions` | Regular | model_name, version, trained_at, metrics, model_path, is_active |

## Key Gotchas

- **Kafka address**: Must use `127.0.0.1:9092` not `localhost:9092` — macOS Colima doesn't support IPv6, and `localhost` resolves to `[::1]`
- **Database URL prefix**: Must be `postgresql+psycopg://` not `postgresql://` — the latter defaults to psycopg2, but we use psycopg v3
- **Dashboard page imports**: Every file in `dashboard/pages/` needs `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` at the top because Streamlit runs pages from their own directory
- **Kafka topics are NOT auto-created**: `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` in docker-compose; must run `create_topics.sh` first
- **Hypertable primary keys**: TimescaleDB requires the time-partitioning column in the PK. `price_ticks` uses `(time, ticker)`, `feature_vectors` uses `(window_end, ticker)`
- **Quix Streams window timestamps**: Returned as epoch milliseconds, must divide by 1000 for Python datetime
- **IsolationForest scoring**: `decision_function()` returns positive for normal, negative for anomalies — check the `is_anomaly` boolean, not the score sign
- **FinBERT sentiment range**: Raw score is [0,1]; `news_producer` inverts negatives so final `sentiment_score` is [-1, 1]
- **Headline deduplication**: `seen_titles` set is in-memory only, resets on producer restart
- **First data delay**: Dashboard shows "No data yet" until the first 5-min window closes (~5 min after pipeline start)
- **LSTM cold start**: Returns 0.0 until 12 observations per ticker (~60 min). Ensemble handles this via warm-up exclusion.
- **Schema migration**: If adding columns to existing hypertables, use `ALTER TABLE ... ADD COLUMN` directly — SQLAlchemy `create_all` won't add columns to existing tables.
- **drift_events not a hypertable**: Its PK is auto-increment `id`, which conflicts with TimescaleDB partitioning. Works fine as a regular table.

## Infrastructure

- **Kafka**: `apache/kafka:3.9.0` in KRaft mode (no Zookeeper). External listener on port 9092, internal on 19092
- **TimescaleDB**: `timescale/timescaledb:latest-pg16`, credentials `marketstream:marketstream`, port 5432, data persisted in `pg_data` volume
- **Kafka-UI**: port 8080, connects to Kafka via internal address `kafka:19092`

## Plotly Chart Styling

All dashboard charts use a shared dark layout dict matching the Streamlit theme:
```python
PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk, sans-serif", color="#e2e8f0"),
    xaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
    yaxis=dict(gridcolor="#314158", zerolinecolor="#314158"),
)
```
When overriding `yaxis` (e.g., for fixed range), copy the dict first to avoid duplicate keyword errors with `**PLOTLY_LAYOUT`.
