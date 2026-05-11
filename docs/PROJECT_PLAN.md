# MarketStream Project Plan

**Project Title:** Multi-Source Streaming Analytics Platform for Financial Trends and Anomaly Detection

**Submission Deadline:** November 2026

## Overview

| Phase                    | Period    | Deliverables                                                 |
| ------------------------ | --------- | ------------------------------------------------------------ |
| 1: Foundation & Baseline | Jan-Mar   | Working streaming pipeline with single-algorithm detection and dashboard |
| 2: Ensemble Detection    | Apr-May   | Four-algorithm ensemble with weighted voting and per-detector interpretability |
| 3: MLOps & Evaluation    | June-July | Drift detection, model retraining, and quantitative evaluation |
| 4: Final Report          | Aug-Sep   | Project thesis, benchmarking results, and submission-ready deliverables |



---

## 1. Project Description

To build a low-latency streaming platform that detects financial market anomalies in real-time by evaluating both price movements and news sentiment through a multi-model ensemble system.

---

## 2. Plan

### Phase 1: Setup & Baseline (January -- March)

**Focus:** Get the basic infrastructure running and establish a baseline model.

- Finalize literature review, project plan, and system architecture
- Set up the data pipeline using Kafka and TimescaleDB
- Write producers that pull real-time price data (OHLCV, every 60s) and news headlines from yfinance, and run FinBERT to get sentiment scores for each headline
- Use Quix Streams to aggregate price data into 5-minute windows and compute features like price change rate, total volume, and sentiment statistics
- Train a baseline Isolation Forest on 30 days of historical data and connect it to the feature stream so it scores each window as it arrives
- Build a Streamlit dashboard with pages for price charts, sentiment feed, and anomaly alerts
- Write up initial documentation: literature review, architecture diagram, and this plan

---

### Phase 2: Advanced Anomaly Detection & Ensemble (April -- May)

**Focus:** Add more detection algorithms and combine them into an ensemble.

- Create a common interface (BaseDetector) so all detectors share the same `score()` and `update()` methods — this makes it easy to swap or add detectors later
- Build an EWMA detector that tracks a running mean and variance for each feature, and flags data points with unusually high z-scores
- Build a Half-Space Trees detector using the `river` library — this one learns incrementally from each new data point, so it doesn't need batch retraining
- Build an LSTM Autoencoder in PyTorch that learns what "normal" sequences look like, and flags sequences it can't reconstruct well (high reconstruction error = anomaly)
- Combine all four detectors (EWMA, HST, Isolation Forest, LSTM) into a weighted voting ensemble — each detector votes on whether something is anomalous, and we take a weighted average
- Hook the ensemble into the existing scoring pipeline and save per-detector scores to the database so we can see which detector flagged what

---

### Phase 3: Model Maintenance & Evaluation (June -- July)

**Focus:** Keep the models up-to-date and measure how well the system actually works.

**MLOps:**

- Use ADWIN (from the `river` library) to monitor whether the distribution of features is changing over time — if the market shifts to a new regime, we want to know
- Build a retraining script that downloads fresh data and retrains the Isolation Forest when drift is detected (or on a schedule)
- Keep track of model versions in the database: which model is active, when it was trained, how it performed
- Add a "Model Health" page to the dashboard showing drift events, model history, and how often each detector agrees/disagrees

**Evaluation:**

- **Backtesting:** Run historical data (including known events like earnings surprises and flash crashes) through the pipeline and check if the system catches them
- **Synthetic anomalies:** Inject fake anomalies (price spikes, volume surges, sentiment flips) into real data to create a labeled test set, then measure precision, recall, and F1
- **Ablation study:** Turn off detectors one at a time to see how much each one contributes to the ensemble's overall performance
- **Sentiment vs. no sentiment:** Compare detection results with and without sentiment features to see if news data actually helps
- **Latency test:** Measure how long it takes from data arriving to an anomaly alert showing up on the dashboard

---

### Phase 4: Benchmarking & Report Writing (August -- September)

**Focus:** Write up the results and prepare everything for submission.

- Collect all evaluation results into tables and charts
- Compare our results against baselines from the literature where possible
- Test how sensitive the system is to hyperparameter choices (ensemble weights, anomaly threshold, EWMA span, etc.)
- Write the final report, structured as: Introduction, Literature Review, Architecture, Methodology, Results, Discussion, Conclusion
- Prepare a live demo and presentation slides
- Clean up the code and documentation for submission

**Deliverables:**
- Final project report
- Presentation materials and live demo
- Clean, documented codebase

---

## 3. Evaluation Strategy (draft)

There's no standard "correct answer" for financial anomalies — they're subjective and context-dependent. So we need multiple ways to test the system:

### 3.1 Historical Event Backtesting

Feed historical market data from periods with known big events (earnings announcements, sell-offs, flash crashes) into the pipeline and see if the system flags them. This is more of a sanity check than a precise measurement, but it tells us if the detectors are picking up on the right kind of signals.

### 3.2 Synthetic Anomaly Injection

Create fake anomalies (price spikes, volume surges, sentiment flips) with controlled magnitudes and inject them into real data. Since we know exactly where the anomalies are, we can compute precision, recall, and F1-score properly. We can also test at different magnitudes to see how sensitive each detector is.

### 3.3 Ablation Analysis

Test the ensemble with different combinations of detectors to understand what each one contributes:
- Full ensemble vs. each detector alone
- Price-only features vs. price + sentiment
- Batch-only (Isolation Forest) vs. streaming-only (EWMA + HST) vs. all together

### 3.4 Drift and Adaptivity

Check if the model maintenance pipeline actually helps. Compare detection performance before and after a drift event, and see how quickly the system recovers after retraining.

---

## 4. Risk Assessment

| Risk | Why it matters | How to handle it |
|------|---------------|-----------------|
| No ground truth for anomaly labels | Financial anomalies don't have a standard definition — we can't directly compute accuracy without labeled data | Use synthetic anomaly injection to create labeled test sets; validate against known historical events (flash crashes, earnings surprises) |
| Model degradation over time | Market behavior changes; a model trained on calm markets won't work well during volatile periods | ADWIN monitors feature distributions for drift; automated retraining refreshes the Isolation Forest when drift is detected |
| Data source reliability | yfinance is a free API with no uptime guarantees — it can go down or rate-limit us | Retry with backoff; cache recent data locally; producers are independent so one failing doesn't block the others |

---

## 5. Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Message Broker | Apache Kafka (KRaft mode) | Event streaming |
| Time-Series Database | TimescaleDB (PostgreSQL) | Storage with hypertable partitioning |
| Stream Processing | Quix Streams | Tumbling window aggregation |
| ML — Statistical | EWMA (NumPy) | Running mean/variance deviation detection |
| ML — Batch | Isolation Forest (scikit-learn) | Batch-trained anomaly detection |
| ML — Streaming | Half-Space Trees (river) | Incremental streaming anomaly detection |
| ML — Deep Learning | LSTM Autoencoder (PyTorch) | Temporal sequence reconstruction |
| NLP | FinBERT (Hugging Face Transformers) | Financial sentiment classification |
| Drift Detection | ADWIN (river) | Feature distribution shift detection |
| Data Source | yfinance | Market data and news |
| Dashboard | Streamlit + Plotly | Interactive visualization |
| Containerization | Docker Compose | Infrastructure orchestration |

---
