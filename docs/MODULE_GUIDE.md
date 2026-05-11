# MarketStream Module Guide

This document explains each module in the MarketStream architecture, following the data flow from ingestion to visualization.

```
yfinance ──→ Producers ──→ Kafka ──→ Stream Processing ──→ Online Scoring ──→ TimescaleDB ──→ Dashboard
                                                            (4 detectors)
                                                            (drift monitor)
```

---

## 1. Data Ingestion (Producers)

### 1.1 price_producer

**File:** `producers/price_producer.py`

**What it does:** Pulls real-time stock prices from yfinance every 60 seconds for each configured ticker (AAPL, TSLA, NVDA). Each price record contains OHLCV data (Open, High, Low, Close, Volume) for a 1-minute bar.

**How it works:**
- Polls yfinance API on a 60-second loop
- Serializes each record to JSON
- Produces to Kafka topic `raw.prices`, keyed by ticker symbol
- Includes retry logic with exponential backoff (up to 3 attempts)

**Output:** One JSON message per ticker per poll cycle → `raw.prices`

```json
{
  "ticker": "AAPL",
  "timestamp": "2026-05-09T14:30:00-04:00",
  "open": 198.12, "high": 198.45,
  "low": 197.98, "close": 198.31,
  "volume": 1523400
}
```

---

### 1.2 news_producer

**File:** `producers/news_producer.py`

**What it does:** Fetches financial news headlines from yfinance every 120 seconds and runs each headline through the FinBERT sentiment model to get a sentiment score.

**How it works:**
- Polls yfinance news API on a 120-second loop
- Each headline is passed through ProsusAI/FinBERT for sentiment classification
- FinBERT outputs a score in [0, 1] with a label (positive/negative/neutral); negatives are inverted so the final score falls in [-1, 1]
- Uses an in-memory `OrderedDict` (capacity 1000) to deduplicate headlines across poll cycles
- Writes to **two destinations simultaneously**:
  - Kafka topic `raw.news_sentiment`
  - Directly to TimescaleDB `sentiment_scores` table

**Why dual-write?** The online_scorer needs to query recent sentiment from the database to enrich feature vectors. Writing directly to the DB avoids the complexity of having the scorer also consume sentiment from Kafka.

**Output:** One JSON message per unique headline → `raw.news_sentiment` + DB row

```json
{
  "ticker": "TSLA",
  "timestamp": "2026-05-09T18:32:15+00:00",
  "headline": "Tesla announces new battery technology partnership",
  "source": "Reuters",
  "sentiment_score": 0.8734,
  "sentiment_label": "positive"
}
```

---

## 2. Stream Processing

### 2.1 stream_app

**File:** `processing/stream_app.py`

**What it does:** Consumes raw price ticks from Kafka, groups them into 5-minute time windows, and produces aggregated feature vectors.

**How it works:**
- Quix Streams consumer subscribed to `raw.prices`
- Applies 5-minute **tumbling windows** (non-overlapping, fixed-length time windows)
- Within each window, a reducer accumulates close prices and volumes
- 30-second **grace period** allows late-arriving messages to be included
- When a window closes, passes accumulated data to `feature_engine` for feature computation
- Produces the result to Kafka topic `stream.features`

**Why tumbling windows?** Raw price data arrives every 60 seconds — that's too granular for anomaly detection. The 5-minute window compresses ~5 ticks into a single feature vector with meaningful statistics (price change, total volume), which is what the ML models consume.

**Note:** Window timestamps from Quix Streams are in epoch milliseconds, so they need to be divided by 1000 when converting to Python datetime.

---

### 2.2 feature_engine

**File:** `processing/feature_engine.py`

**What it does:** A pure computation module (no Kafka, no database) that calculates features from windowed price data.

**Features computed:**

| Feature | Formula | What it captures |
|---------|---------|-----------------|
| `price_change_rate` | `(last_close - first_close) / first_close` | How much did the price move in this window? |
| `total_volume` | `sum(volume)` | Total shares traded in the window |
| `tick_count` | `len(ticks)` | How many price updates arrived (data quality indicator) |
| `avg_close` | `mean(close_prices)` | Average price level in the window |

These 4 features form the base feature vector. The online_scorer later enriches it with 3 more sentiment features (`avg_sentiment`, `sentiment_shift`, `headline_count`).

---

## 3. Anomaly Detection (Online Scoring)

### 3.1 online_scorer

**File:** `ml/online_scorer.py`

**What it does:** The core scoring process. Consumes feature vectors, enriches them with sentiment data, runs them through 4 anomaly detectors, and writes results to the database.

**Three-step pipeline per message:**

**Step 1 — Sentiment enrichment:**
- Queries the last 20 headlines for the ticker from TimescaleDB
- Splits them: first 10 = "recent", next 10 = "older"
- Computes `avg_sentiment` (mean of recent scores) and `sentiment_shift` (recent mean - older mean)
- Uses a 60-second cache to avoid hammering the database

**Step 2 — Ensemble scoring:**
- Passes the enriched feature vector to all 4 detectors
- Each detector returns a score (more negative = more anomalous)
- `EnsembleDetector` computes a weighted average of all scores
- After scoring, calls `update()` on each detector for online learning
- Also updates the ADWIN drift monitor

**Step 3 — Result storage:**
- **Always** writes a `FeatureVector` row (with anomaly score + per-detector scores)
- **If anomaly** (score < -0.3): also writes an `AnomalyAlert` row + produces to Kafka `stream.anomalies`

---

### 3.2 Detector Abstraction

**File:** `ml/base_detector.py`

**What it does:** Defines a common interface (`BaseDetector`) that all detectors implement:

```
BaseDetector (abstract)
├── score(features) → float     # Lower = more anomalous
├── update(features) → None     # Online learning (no-op for batch models)
└── name → str                  # Detector identifier
```

This abstraction lets the ensemble treat all detectors identically — it doesn't care how each detector works internally, only that it returns a score.

---

### 3.3 EWMA Detector

**File:** `ml/detectors/ewma_detector.py`

**What it does:** Statistical anomaly detector based on Exponentially Weighted Moving Average. Tracks running mean and variance for each feature (per ticker), and scores new observations by how far they deviate from the expected distribution.

**How it works:**
1. Maintains a running mean (μ) and variance (σ²) for each of the 4 features, per ticker
2. Each new observation adjusts these statistics using exponential weighting (`α = 2 / (span + 1)`, default span = 20)
3. Score = `-max(z_scores)` across all features, where z = |value - μ| / σ
4. A sudden price spike produces a large z-score → strongly negative score → anomaly

**Strengths:** Fastest detector, zero dependencies (NumPy only), interpretable, naturally adapts over time

**Limitations:** Only looks at one data point at a time (no temporal patterns), each feature scored independently (no multivariate interactions)

**Cold start:** Returns 0.0 until it has seen at least one data point per ticker (the ensemble handles this gracefully)

---

### 3.4 Half-Space Trees (HST) Detector

**File:** `ml/detectors/hst_detector.py`

**What it does:** A streaming version of Isolation Forest from the `river` library. Unlike the batch Isolation Forest which needs to be trained on historical data, HST updates itself incrementally with every new data point.

**How it works:**
- Uses `river.anomaly.HalfSpaceTrees` with 25 trees, height 6, sliding window of 50
- Each data point: first call `score_one()` to get the anomaly score, then `learn_one()` to update the model
- Score is negated so the convention matches other detectors (more negative = more anomalous)

**Strengths:** True streaming — adapts to distribution changes without retraining; captures multivariate interactions between features

**Limitations:** Needs a warm-up period (~50 observations) before scores become reliable

---

### 3.5 Isolation Forest Detector

**File:** `ml/detector.py`

**What it does:** The original batch-trained anomaly detector using scikit-learn's `IsolationForest`. Pre-trained on 30 days of historical data and loaded from a saved model file.

**How it works:**
- Model trained offline via `ml/train_baseline.py` with `contamination=0.05`, `n_estimators=200`
- At runtime, loads the saved model from `data/models/isolation_forest.joblib`
- Uses `decision_function()` to score — positive scores = normal, negative = anomalous
- Does **not** update online — remains static until manually retrained

**Strengths:** Industry-standard algorithm, stable and well-understood, strong baseline performance

**Limitations:** Static — doesn't adapt to market changes unless explicitly retrained; that's what the retraining pipeline (Section 5) is for

---

### 3.6 LSTM Autoencoder Detector

**File:** `ml/detectors/lstm_detector.py`

**What it does:** A deep learning detector that learns what "normal" sequences of feature vectors look like. When it sees a sequence it can't reconstruct well (high reconstruction error), it flags it as anomalous.

**How it works:**
1. Maintains a sliding buffer of the last 12 feature vectors per ticker
2. When the buffer is full, feeds the sequence through the LSTM Autoencoder
3. The model tries to reconstruct the input sequence; score = `-MSE(input, reconstruction)`
4. Normal patterns → low MSE → score near 0; unusual patterns → high MSE → strongly negative score

**Architecture:**
- Encoder: LSTM(input=4 features, hidden=32)
- Decoder: LSTM(hidden=32, output=32) → Linear(32, 4)
- Trained via `ml/train_lstm.py` on historical data

**Cold start:** Returns 0.0 until it has collected 12 data points per ticker (~60 minutes of data). The ensemble skips this score during warm-up and redistributes the weight (0.2) to other detectors.

**Strengths:** Only detector that captures **temporal patterns** — e.g., "the last 12 windows show an unusual trend that no single window would trigger"

**Limitations:** Slowest detector; needs training data; cold start period

---

### 3.7 Ensemble Detector

**File:** `ml/ensemble.py`

**What it does:** Combines the scores from all 4 detectors into a single anomaly decision using weighted voting.

**Default weights:** EWMA = 0.2, HST = 0.3, Isolation Forest = 0.3, LSTM = 0.2

**How it works:**
1. Calls `score()` on each detector
2. Computes weighted average of all scores
3. If LSTM returns 0.0 (still warming up), it's excluded from the average and the remaining weights are renormalized
4. If the final score < -0.3 (configurable threshold) → classified as anomaly
5. Returns both the ensemble score and a dict of per-detector scores for transparency

**Why these weights?** The two tree-based detectors (HST + Isolation Forest) get 60% of the weight because they capture multivariate feature interactions. EWMA and LSTM each get 20% — EWMA is fast but univariate, LSTM is powerful but slow to warm up.

---

## 4. Model Maintenance

### 4.1 Drift Monitor

**File:** `ml/drift_monitor.py`

**What it does:** Watches for concept drift — when the statistical distribution of features changes significantly over time. This happens when market conditions shift (e.g., calm market → volatile market).

**How it works:**
- Uses ADWIN (Adaptive Windowing) from the `river` library
- Maintains one ADWIN instance per feature per ticker (4 features × 3 tickers = 12 monitors)
- ADWIN automatically adjusts its window size based on the data — it shrinks the window when it detects a statistically significant distribution change
- When drift is detected, writes a `DriftEvent` record to the database
- Sensitivity controlled by `drift_sensitivity` parameter (default: 0.002)

**Why it matters:** If the market enters a new regime and the Isolation Forest was trained on old data, its scores become unreliable. Drift detection tells us **when** the model needs retraining.

---

### 4.2 Retraining Pipeline

**File:** `ml/retrain.py`

**What it does:** Retrains the Isolation Forest on fresh data and manages model versioning.

**Steps:**
1. Downloads the last 30 days of historical price data for all tickers (via `ml/data_utils.py`)
2. Computes features using the same logic as the live pipeline
3. Trains a new `IsolationForest(contamination=0.05, n_estimators=200)`
4. Saves with a versioned filename (e.g., `isolation_forest_v3.joblib`)
5. Records training metadata in `model_versions` table (sample count, anomaly rate, score stats)
6. Marks the previous active model as inactive
7. Copies the new model to the canonical path so the online scorer picks it up on next restart

**Usage:** `uv run python -m ml.retrain`

---

### 4.3 Data Utilities

**File:** `ml/data_utils.py`

**What it does:** Shared module for downloading and preparing historical training data. Extracted from `train_baseline.py` so both `train_baseline.py` and `retrain.py` use the same data logic.

**Functions:**
- `download_historical(tickers, period)` — downloads OHLCV data, slides 5-minute windows, computes features, generates synthetic sentiment
- `fetch_historical_sentiment(ticker, period)` — fetches news headlines to seed synthetic sentiment distribution for training

---

### 4.4 LSTM Training Script

**File:** `ml/train_lstm.py`

**What it does:** Trains the LSTM Autoencoder on historical feature data.

**Steps:**
1. Downloads historical data via `data_utils.download_historical()`
2. Creates overlapping sequences of length 12 per ticker
3. Normalizes features (saves mean/std to `data/models/lstm_norm.npz`)
4. Trains the autoencoder for 30 epochs with MSE loss
5. Saves model weights to `data/models/lstm_autoencoder.pt`

**Usage:** `uv run python -m ml.train_lstm`

---

## 5. Storage (TimescaleDB)

TimescaleDB extends PostgreSQL with automatic time-based partitioning (hypertables). All hypertables use 1-day chunk intervals.

**File:** `storage/models.py` (SQLAlchemy ORM models), `storage/init_db.py` (table creation), `storage/db.py` (connection management)

| Table | Type | What it stores | Written by | Read by |
|-------|------|---------------|------------|---------|
| `price_ticks` | Hypertable (time) | Raw 1-min OHLCV bars | price_producer (via Kafka → stream_app) | Dashboard (Price Chart) |
| `sentiment_scores` | Hypertable (time) | Headlines + FinBERT sentiment scores | news_producer (direct write) | online_scorer (sentiment query), Dashboard (Sentiment Feed) |
| `feature_vectors` | Hypertable (window_end) | 5-min windowed features, anomaly scores, per-detector scores (JSON) | online_scorer | Dashboard (Price Chart, Anomaly Alerts, Model Health) |
| `anomaly_alerts` | Regular table | Anomaly events with reason text and feature snapshot | online_scorer (only on anomaly) | Dashboard (Anomaly Alerts) |
| `drift_events` | Hypertable (detected_at) | ADWIN drift detection events | drift_monitor | Dashboard (Model Health) |
| `model_versions` | Regular table | Model training history and metadata | retrain.py | Dashboard (Model Health) |

---

## 6. Dashboard (Streamlit)

**Files:** `dashboard/app.py` (home), `dashboard/shared.py` (shared queries and layout), `dashboard/pages/*.py`

The dashboard reads **only from TimescaleDB** — it never consumes Kafka directly. Each page auto-refreshes every 5-10 seconds using `@st.fragment` decorators. All charts use a shared Plotly dark theme defined in `shared.py`.

| Page | File | What it shows |
|------|------|--------------|
| **Home** | `app.py` | System overview: data freshness per ticker (LIVE/STALE/DOWN), features per hour, headlines per hour, anomaly count in last hour |
| **Price Chart** | `pages/1_Price_Chart.py` | Interactive price chart with anomaly markers overlaid on the price line |
| **Sentiment Feed** | `pages/2_Sentiment_Feed.py` | Real-time scrolling list of news headlines with their sentiment scores and labels |
| **Anomaly Alerts** | `pages/3_Anomaly_Alerts.py` | List of detected anomalies; each can be expanded to show feature values and per-detector score breakdown |
| **Comparison** | `pages/4_Comparison.py` | Side-by-side comparison of multiple tickers' anomaly scores and features |
| **Model Health** | `pages/5_Model_Health.py` | Four tabs: Model Registry (version history), Drift Events (timeline), Anomaly Rate (rolling chart per ticker), Detector Scores (per-detector score timelines and agreement analysis) |

---

## 7. Configuration

**File:** `config/settings.py`

All runtime parameters are managed via Pydantic Settings with `.env` file support. Key parameter groups:

| Group | Parameters | Purpose |
|-------|-----------|---------|
| Data sources | `tickers`, poll intervals | Which stocks to track, how often to poll |
| Infrastructure | `kafka_bootstrap_servers`, `database_url` | Where Kafka and TimescaleDB are running |
| Anomaly thresholds | `anomaly_price_threshold`, `anomaly_volume_threshold`, `anomaly_severity_threshold` | When to generate human-readable anomaly reasons |
| Ensemble | `ensemble_weights`, `ensemble_threshold` | How to combine detector scores and when to flag anomalies |
| EWMA | `ewma_span` | How quickly EWMA adapts to new data (lower = faster) |
| Half-Space Trees | `hst_n_trees`, `hst_height`, `hst_window_size` | HST model complexity and memory |
| LSTM | `lstm_sequence_length`, `lstm_hidden_dim`, `lstm_model_path` | LSTM architecture and model file location |
| Drift | `drift_detection_enabled`, `drift_sensitivity` | Whether to run ADWIN and how sensitive it should be |
