# MarketStream

**A Multi-Source Streaming Analytics Platform for Financial Trends and Anomaly Detection**

## Architecture

```
[yfinance prices] → price_producer → Kafka "raw.prices" ──┐
                                                            ├→ Quix Streams (5-min tumbling windows)
[yfinance news]   → news_producer  → Kafka "raw.news_sentiment" ┘
                                                     ↓
                                            Kafka "stream.features"
                                                     ↓
                                            online_scorer (IsolationForest)
                                                     ↓
                                              TimescaleDB ←── Streamlit dashboard
```

## Tech Stack

| Layer | Tool |
|---|---|
| Package Management | uv (Python 3.12) |
| Message Queue | Apache Kafka (KRaft mode, Docker) |
| Stream Processing | Quix Streams (tumbling windows, stateful aggregation) |
| Data Ingestion | yfinance (prices + news) |
| Sentiment Analysis | FinBERT (ProsusAI/finbert via HuggingFace Transformers) |
| Anomaly Detection | Isolation Forest (scikit-learn) |
| Storage | TimescaleDB (PostgreSQL + time-series hypertables) |
| Dashboard | Streamlit + Plotly (auto-refresh via `@st.fragment`) |
| Monitoring | Kafka-UI |

## Project Structure

```
├── config/              # Settings (pydantic-settings) and logging
├── producers/           # Data ingestion (prices + news with FinBERT sentiment)
├── processing/          # Quix Streams windowed aggregation + feature engineering
├── ml/                  # Isolation Forest anomaly detection (train + online scoring)
├── storage/             # SQLAlchemy models, TimescaleDB hypertables
├── dashboard/           # Streamlit multi-page app (Price Chart, Sentiment Feed, Alerts)
├── scripts/             # Startup, topic creation, historical data seeding
├── tests/               # Unit tests for feature engine and detector
└── docker-compose.yml   # Kafka + TimescaleDB + Kafka-UI
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker](https://www.docker.com/) with a runtime (Docker Desktop, Colima, etc.)

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Start infrastructure

```bash
docker-compose up -d
bash scripts/create_topics.sh
uv run python -m storage.init_db
```

### 3. Train the baseline model

```bash
uv run python -m ml.train_baseline
```

This downloads 30 days of historical data and trains an Isolation Forest model.

### 4. Run the full pipeline

```bash
bash scripts/start_all.sh
```

Or start components individually:

```bash
uv run python -m producers.price_producer &
uv run python -m producers.news_producer &
uv run python -m processing.stream_app &
uv run python -m ml.online_scorer &
uv run streamlit run dashboard/app.py --server.port 8501
```

### 5. Access the dashboard

- **Dashboard**: http://localhost:8501
- **Kafka UI**: http://localhost:8080

## Kafka Topics

| Topic | Description |
|---|---|
| `raw.prices` | Real-time OHLCV price data per ticker |
| `raw.news_sentiment` | News headlines with FinBERT sentiment scores |
| `stream.features` | 5-min windowed features (price change rate, volume, etc.) |
| `stream.anomalies` | Detected anomaly events |

## Dashboard Pages

- **Price Chart** — Real-time price trends with anomaly markers (red X)
- **Sentiment Feed** — Rolling news headlines with color-coded sentiment scores
- **Anomaly Alerts** — Detected anomalies with expandable feature details

## Testing

```bash
uv run pytest tests/ -v
```
