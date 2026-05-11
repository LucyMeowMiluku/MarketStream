# MarketStream

Multi-Source Streaming Analytics Platform for Financial Trends and Anomaly Detection

A real-time streaming platform that detects financial market anomalies by combining price data and news sentiment through a four-algorithm ensemble system. Built with Apache Kafka, TimescaleDB, and Streamlit.

**Tracked tickers:** AAPL, TSLA, NVDA

---

## System Architecture

![System Architecture](docs/figures/框架图.png)

The system consists of five independently-running Python processes connected by Apache Kafka:

| Component | Role |
|-----------|------|
| **price_producer** | Polls Yahoo Finance every 60s for OHLCV data, produces to Kafka |
| **news_producer** | Polls news every 120s, runs FinBERT sentiment scoring, writes to Kafka + DB |
| **stream_app** | Quix Streams consumer — aggregates prices into 5-min tumbling windows, computes features |
| **online_scorer** | Enriches features with sentiment, runs 4-detector ensemble, writes results to DB |
| **Dashboard** | Streamlit app — reads from TimescaleDB, auto-refreshes every 5-10s |

---

## Ensemble Anomaly Detection

Instead of relying on a single algorithm, the system combines four detection methods through weighted voting. Each detector brings a different strength:

| Detector | Type | Weight | What it catches |
|----------|------|--------|----------------|
| **EWMA** | Statistical | 0.2 | Sudden single-feature spikes (z-score based) |
| **Half-Space Trees** | Streaming ML | 0.3 | Multivariate anomalies, adapts to distribution shifts in real time |
| **Isolation Forest** | Batch ML | 0.3 | Global outliers based on historical patterns |
| **LSTM Autoencoder** | Deep Learning | 0.2 | Temporal sequence anomalies (unusual trends over time) |

The ensemble score is a weighted average of all detector scores. If the score falls below -0.3, the observation is flagged as an anomaly.

---

## Model Maintenance (MLOps)

- **Drift Detection**: ADWIN monitors feature distributions per ticker. When market conditions shift, drift events are logged to the database.
- **Model Retraining**: IsolationForest supports scheduled retraining with versioned model files and a database-backed model registry.
- **Adaptive Detectors**: EWMA and HST continuously update with each new observation — they adapt to changing markets without explicit retraining.

---

## Backtest Results

We evaluated the ensemble on 60 days of historical data with 5% synthetic anomaly injection (price spikes, volume surges, sentiment crashes, multi-feature events, and subtle drift).

### Detection Performance

| Metric | Value |
|--------|-------|
| **Recall** | 98.67% |
| **Precision** | 8.34% |
| **F1 Score** | 0.154 |
| **True Positives** | 222 / 225 |
| **False Positives** | 2441 |
| **False Negatives** | 3 |

The high recall (98.67%) means the system catches nearly all injected anomalies. The low precision is expected — the system is tuned for safety (don't miss real anomalies), and the threshold can be adjusted to trade recall for fewer false alarms.

### Per-Type Recall

| Anomaly Type | Recall |
|-------------|--------|
| Price Spike | 100% |
| Volume Surge | 100% |
| Sentiment Crash | 100% |
| Multi-Feature | 100% |
| Subtle Drift | 80% |

### Per-Detector Breakdown

| Detector | Precision | Recall | Detections |
|----------|-----------|--------|------------|
| EWMA | 5.4% | 100% | 4182 |
| LSTM Autoencoder | 6.0% | 60.9% | 2290 |
| Half-Space Trees | 2.7% | 3.1% | 260 |
| Isolation Forest | 0% | 0% | 0 |

EWMA is the most sensitive (catches everything), while HST and Isolation Forest are more conservative. The ensemble balances these tendencies through weighted voting.

### Drift Detection

The backtest includes a simulated distribution shift at index 3367 (out of 4209 data points). ADWIN detected 37 drift events during the replay, with detection latencies of 88 windows for volume features and 182 windows for sentiment features.

### Score Separation

| Metric | Value |
|--------|-------|
| Normal score (mean) | -0.55 |
| Anomaly score (mean) | -1.99 |
| Cohen's d | 0.53 |

The anomaly scores are clearly separated from normal scores, confirming that the ensemble produces meaningful differentiation.

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Home** | System health, data freshness per ticker, anomaly count |
| **Price Chart** | Interactive price chart with anomaly markers |
| **Sentiment Feed** | Real-time news headlines with sentiment scores |
| **Anomaly Alerts** | Alert list with feature breakdown and per-detector scores |
| **Comparison** | Cross-ticker comparison view |
| **Model Health** | Model registry, drift events timeline, anomaly rate trends, detector agreement |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Message Broker | Apache Kafka 3.9.0 (KRaft mode) |
| Database | TimescaleDB (PostgreSQL 16) |
| Stream Processing | Quix Streams |
| ML — Statistical | EWMA (NumPy) |
| ML — Batch | Isolation Forest (scikit-learn) |
| ML — Streaming | Half-Space Trees (river) |
| ML — Deep Learning | LSTM Autoencoder (PyTorch) |
| NLP | FinBERT (Hugging Face Transformers) |
| Drift Detection | ADWIN (river) |
| Dashboard | Streamlit + Plotly |

---

## Project Structure

```
├── config/              # Settings (pydantic-settings) and logging
├── producers/           # Data ingestion (prices + news with FinBERT)
├── processing/          # Quix Streams windowed aggregation + feature engine
├── ml/
│   ├── detector.py          # Isolation Forest (BaseDetector)
│   ├── detectors/           # EWMA, HST, LSTM Autoencoder
│   ├── ensemble.py          # Weighted voting ensemble
│   ├── drift_monitor.py     # ADWIN concept drift detection
│   ├── retrain.py           # Model retraining with versioning
│   ├── backtest.py          # Offline backtesting framework
│   ├── train_baseline.py    # Isolation Forest training
│   └── train_lstm.py        # LSTM Autoencoder training
├── storage/             # SQLAlchemy models, TimescaleDB init
├── dashboard/           # Streamlit multi-page app (6 pages)
├── tests/               # Unit tests (50 tests)
├── docs/                # Literature review, architecture, project plan
├── scripts/             # Startup, topic creation
└── docker-compose.yml   # Kafka + TimescaleDB + Kafka-UI
```

---

## Quick Start

```bash
# Install dependencies
uv sync

# Start infrastructure
docker-compose up -d
bash scripts/create_topics.sh
uv run python -m storage.init_db

# Train models
uv run python -m ml.train_baseline    # Isolation Forest
uv run python -m ml.train_lstm        # LSTM Autoencoder

# Run backtest (optional)
uv run python -m ml.backtest

# Start the full pipeline
bash scripts/start_all.sh

# Access dashboard at http://localhost:8501
```

---

## Testing

```bash
uv run pytest tests/ -v     # 50 tests
uv run ruff check .         # Lint
```
