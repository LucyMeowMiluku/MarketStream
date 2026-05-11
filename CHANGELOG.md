# MarketStream Changelog

## 2026-05-09 — Ensemble Detection + MLOps + Documentation

### Summary

Upgraded from single IsolationForest to a 4-algorithm ensemble anomaly detection system with model maintenance (drift detection + retraining), and added full academic documentation.

---

### New Files

**ML — Detector Infrastructure:**
| File | Purpose |
|------|---------|
| `ml/base_detector.py` | Abstract `BaseDetector` interface: `score()`, `update()`, `name` |
| `ml/detectors/__init__.py` | Package init, re-exports all detectors |
| `ml/detectors/ewma_detector.py` | EWMA detector — per-ticker running mean/variance, z-score based |
| `ml/detectors/hst_detector.py` | Half-Space Trees detector — streaming via `river.anomaly.HalfSpaceTrees` |
| `ml/detectors/lstm_detector.py` | LSTM Autoencoder — PyTorch encoder-decoder, MSE reconstruction error |
| `ml/ensemble.py` | `EnsembleDetector` — weighted voting, warm-up handling for LSTM |

**ML — Model Maintenance:**
| File | Purpose |
|------|---------|
| `ml/data_utils.py` | Shared `download_historical()` and `fetch_historical_sentiment()` — extracted from `train_baseline.py` |
| `ml/train_lstm.py` | LSTM Autoencoder training script (`uv run python -m ml.train_lstm`) |
| `ml/drift_monitor.py` | `DriftMonitor` — ADWIN per feature per ticker, writes `DriftEvent` to DB |
| `ml/retrain.py` | IsolationForest retraining with model versioning (`uv run python -m ml.retrain`) |

**Dashboard:**
| File | Purpose |
|------|---------|
| `dashboard/pages/5_Model_Health.py` | New page: Model Registry, Drift Events, Anomaly Rate, Detector Scores tabs |

**Documentation:**
| File | Purpose |
|------|---------|
| `docs/LITERATURE_REVIEW.md` | Academic literature review with 30+ references, adopted methods tagged |
| `docs/LITERATURE_REVIEW.docx` | Word version with figures, proper formatting |
| `docs/ARCHITECTURE.md` | System architecture: Mermaid flowchart, component table, Kafka schemas, tech rationale |
| `docs/PROJECT_PLAN.md` | 4-phase plan (Jan-Sep), evaluation strategy, risk assessment |
| `docs/MODULE_GUIDE.md` | Module-by-module guide explaining each component's role |
| `docs/fig1_taxonomy.png` | Taxonomy diagram of reviewed anomaly detection methods |
| `docs/fig2_architecture.png` | System architecture diagram with adopted methods highlighted |

**Tests:**
| File | Tests |
|------|-------|
| `tests/test_ewma_detector.py` | cold start, normal-vs-extreme scoring, stat updates (3 tests) |
| `tests/test_hst_detector.py` | name, warmup scoring, incremental update (3 tests) |
| `tests/test_lstm_detector.py` | buffer-not-full, scores-after-full, per-ticker buffers (3 tests) |
| `tests/test_ensemble.py` | weighted average, threshold, update propagation, equal weights (4 tests) |

---

### Modified Files

**`ml/detector.py`**
- `AnomalyDetector` now extends `BaseDetector`
- Added `score()` method (returns `decision_function()` float)
- Added `name` property → `"isolation_forest"`
- Kept backward-compatible `predict()` method

**`ml/online_scorer.py`**
- Replaced single `AnomalyDetector` with `EnsembleDetector` (4 detectors)
- Added `build_ensemble()` function that instantiates all detectors from settings
- Scoring changed: `detector.predict(enriched)` → `ensemble.score(enriched)` returns `(score, detector_scores_dict)`
- Added `ensemble.update(enriched)` call after scoring for online learning
- Added `DriftMonitor` integration — updates after each scoring
- `FeatureVector` and `AnomalyAlert` now include `detector_scores` JSON field
- Kafka anomaly messages now include `detector_scores`

**`ml/train_baseline.py`**
- Removed inline `download_historical()` and `_fetch_historical_sentiment()` functions
- Now imports from `ml.data_utils` instead
- Training logic unchanged

**`storage/models.py`**
- `FeatureVector`: added `detector_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)`
- `AnomalyAlert`: added `detector_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)`
- Added `ModelVersion` model: id, model_name, version, trained_at, training metrics, model_path, is_active, metadata
- Added `DriftEvent` model: id, detected_at, ticker, feature_name, drift_type, details

**`storage/init_db.py`**
- Added `drift_events` to hypertable list (with `detected_at` partition column)
- Note: drift_events fails hypertable creation due to PK constraint — works as regular table

**`config/settings.py`**
- Added ensemble config: `ensemble_weights`, `ensemble_threshold`
- Added EWMA config: `ewma_span`
- Added HST config: `hst_n_trees`, `hst_height`, `hst_window_size`
- Added LSTM config: `lstm_sequence_length`, `lstm_hidden_dim`, `lstm_model_path`
- Added drift config: `drift_detection_enabled`, `drift_sensitivity`

**`pyproject.toml`**
- Added dependencies: `river>=0.21`, `matplotlib>=3.10.9`

**`dashboard/shared.py`**
- Added `fetch_model_versions()` — queries `model_versions` table
- Added `fetch_drift_events(hours)` — queries `drift_events` table
- Added `fetch_detector_scores(ticker, hours)` — queries `feature_vectors` with `detector_scores IS NOT NULL`
- Added `fetch_anomaly_rate(hours)` — hourly anomaly rate per ticker
- Modified `fetch_anomaly_data()` — now includes `detector_scores` in SELECT

**`dashboard/pages/3_Anomaly_Alerts.py`**
- Added per-detector score breakdown inside each anomaly expander
- Shows detector name + score when `detector_scores` JSON is present

---

### Database Schema Changes

Applied via `storage.init_db` + manual ALTER:

```sql
-- New columns on existing tables
ALTER TABLE feature_vectors ADD COLUMN detector_scores JSONB;
ALTER TABLE anomaly_alerts ADD COLUMN detector_scores JSONB;

-- New tables
CREATE TABLE model_versions (id SERIAL PK, model_name, version, trained_at, training_data_start, training_data_end, sample_count, anomaly_rate, score_mean, score_std, model_path, is_active, metadata JSONB);
CREATE TABLE drift_events (id SERIAL PK, detected_at, ticker, feature_name, drift_type, details JSONB);
```

---

### Test Results

All 50 tests pass. Lint clean (`ruff check .` passes).

```
tests/test_db.py             4 passed
tests/test_detector.py       3 passed
tests/test_ensemble.py       4 passed
tests/test_ewma_detector.py  3 passed
tests/test_feature_engine.py 11 passed
tests/test_hst_detector.py   3 passed
tests/test_lstm_detector.py  3 passed
tests/test_news_producer.py  7 passed
tests/test_online_scorer.py  12 passed
```

---

### Configuration Defaults

```python
# Ensemble
ensemble_weights = [0.2, 0.3, 0.3, 0.2]  # EWMA, HST, IF, LSTM
ensemble_threshold = -0.3

# EWMA
ewma_span = 20

# Half-Space Trees
hst_n_trees = 25
hst_height = 6
hst_window_size = 50

# LSTM Autoencoder
lstm_sequence_length = 12
lstm_hidden_dim = 32
lstm_model_path = "data/models/lstm_autoencoder.pt"

# Drift
drift_detection_enabled = True
drift_sensitivity = 0.002
```

---

### Pending / Not Yet Done

- [ ] Step 1 from plan: Restructure git history into modular commits (new repo)
- [ ] LSTM model not yet trained (`uv run python -m ml.train_lstm` needed)
- [ ] Backtesting framework for evaluation (mentioned in PROJECT_PLAN Phase 3)
- [ ] Synthetic anomaly injection for evaluation metrics
- [ ] Sensitivity analysis on hyperparameters
