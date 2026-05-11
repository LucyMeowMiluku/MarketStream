import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Consumer, Producer

from config.logging_config import get_logger
from config.settings import settings
from ml.detector import AnomalyDetector
from ml.detectors.ewma_detector import EWMADetector
from ml.detectors.hst_detector import HSTDetector
from ml.detectors.lstm_detector import LSTMDetector
from ml.ensemble import EnsembleDetector
from ml.drift_monitor import DriftMonitor
from storage.db import get_session
from storage.models import FeatureVector, AnomalyAlert, SentimentScore

log = get_logger("online_scorer")

MODEL_PATH = "data/models/isolation_forest.joblib"

running = True


def shutdown(sig, frame):
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


SENTIMENT_CACHE_TTL = 60
_sentiment_cache: dict[str, tuple[float, float, float, int]] = {}


def get_recent_sentiment_cached(session, ticker: str) -> tuple[float, float, int]:
    now = time.time()
    if ticker in _sentiment_cache:
        cached_time, avg, shift, count = _sentiment_cache[ticker]
        if now - cached_time < SENTIMENT_CACHE_TTL:
            return avg, shift, count
    avg, shift, count = get_recent_sentiment(session, ticker)
    _sentiment_cache[ticker] = (now, avg, shift, count)
    return avg, shift, count


def get_recent_sentiment(session, ticker: str, window_minutes: int = 5) -> tuple[float, float, int]:
    rows = (
        session.query(SentimentScore)
        .filter(SentimentScore.ticker == ticker)
        .order_by(SentimentScore.time.desc())
        .limit(settings.sentiment_recent_limit)
        .all()
    )
    if not rows:
        return 0.0, 0.0, 0

    split = settings.sentiment_split_index
    recent = [r.sentiment_score for r in rows[:split]]
    older = [r.sentiment_score for r in rows[split:]]

    avg_sentiment = sum(recent) / len(recent)
    prev_avg = sum(older) / len(older) if older else avg_sentiment
    shift = avg_sentiment - prev_avg

    return round(avg_sentiment, 4), round(shift, 4), len(recent)


def build_anomaly_reason(features: dict, score: float) -> str:
    reasons = []
    if abs(features.get("price_change_rate", 0)) > settings.anomaly_price_threshold:
        reasons.append(f"large price move ({features['price_change_rate']:.2%})")
    if features.get("total_volume", 0) > settings.anomaly_volume_threshold:
        reasons.append(f"high volume ({features['total_volume']:,})")
    if abs(features.get("sentiment_shift", 0)) > settings.anomaly_sentiment_threshold:
        reasons.append(f"sentiment shift ({features['sentiment_shift']:.2f})")
    if not reasons:
        reasons.append(f"anomaly score={score:.4f}")
    return "; ".join(reasons)


def build_ensemble() -> EnsembleDetector:
    detectors = []
    weights = list(settings.ensemble_weights)

    detectors.append(EWMADetector(span=settings.ewma_span))
    detectors.append(HSTDetector(
        n_trees=settings.hst_n_trees,
        height=settings.hst_height,
        window_size=settings.hst_window_size,
    ))
    detectors.append(AnomalyDetector(model_path=MODEL_PATH))

    lstm_path = Path(settings.lstm_model_path)
    lstm = LSTMDetector(
        model_path=str(lstm_path) if lstm_path.exists() else None,
        sequence_length=settings.lstm_sequence_length,
        hidden_dim=settings.lstm_hidden_dim,
    )
    norm_path = lstm_path.parent / "lstm_norm.npz"
    if norm_path.exists():
        import numpy as np
        norms = np.load(str(norm_path))
        lstm._mean = norms["mean"]
        lstm._std = norms["std"]
    detectors.append(lstm)

    return EnsembleDetector(detectors, weights=weights, threshold=settings.ensemble_threshold)


def main():
    ensemble = build_ensemble()
    log.info("ensemble_loaded", detectors=ensemble.detector_names)

    drift_monitor = DriftMonitor(delta=settings.drift_sensitivity) if settings.drift_detection_enabled else None

    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "online-scorer",
            "auto.offset.reset": "latest",
        }
    )
    consumer.subscribe(["stream.features"])

    anomaly_producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})

    log.info("started")

    msg_count = 0
    last_flush = time.time()

    while running:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            log.error("consumer_error", error=str(msg.error()))
            continue

        try:
            features = json.loads(msg.value().decode())
            ticker = features["ticker"]

            session = get_session()
            try:
                avg_sentiment, sentiment_shift, headline_count = get_recent_sentiment_cached(
                    session, ticker
                )

                enriched = {
                    **features,
                    "avg_sentiment": avg_sentiment,
                    "sentiment_shift": sentiment_shift,
                    "headline_count": headline_count,
                }

                score, detector_scores = ensemble.score(enriched)
                is_anomaly = ensemble.is_anomaly(score)
                ensemble.update(enriched)

                if drift_monitor:
                    drifted = drift_monitor.update(enriched)
                    if drifted:
                        log.warning("drift_detected", ticker=ticker, features=drifted)

                fv = FeatureVector(
                    window_start=datetime.fromtimestamp(
                        enriched["window_start"] / 1000, tz=timezone.utc
                    ),
                    window_end=datetime.fromtimestamp(
                        enriched["window_end"] / 1000, tz=timezone.utc
                    ),
                    ticker=ticker,
                    avg_close=enriched["avg_close"],
                    price_change_rate=enriched["price_change_rate"],
                    total_volume=enriched["total_volume"],
                    avg_sentiment=avg_sentiment,
                    sentiment_shift=sentiment_shift,
                    headline_count=headline_count,
                    anomaly_score=score,
                    is_anomaly=is_anomaly,
                    detector_scores=detector_scores,
                )
                session.add(fv)

                if is_anomaly:
                    alert = AnomalyAlert(
                        detected_at=datetime.now(timezone.utc),
                        ticker=ticker,
                        anomaly_score=score,
                        features=enriched,
                        reason=build_anomaly_reason(enriched, score),
                        detector_scores=detector_scores,
                    )
                    session.add(alert)

                    anomaly_producer.produce(
                        "stream.anomalies",
                        key=ticker.encode(),
                        value=json.dumps(
                            {
                                "ticker": ticker,
                                "anomaly_score": score,
                                "is_anomaly": True,
                                "features": enriched,
                                "reason": alert.reason,
                                "detector_scores": detector_scores,
                            }
                        ).encode(),
                    )

                    log.warning(
                        "anomaly_detected",
                        ticker=ticker,
                        score=f"{score:.4f}",
                        reason=alert.reason,
                        detectors=detector_scores,
                    )

                session.commit()
                msg_count += 1
                if msg_count % 10 == 0 or time.time() - last_flush > 30:
                    anomaly_producer.flush()
                    last_flush = time.time()
                log.info("scored", ticker=ticker, score=f"{score:.4f}", anomaly=is_anomaly)
            finally:
                session.close()

        except Exception as e:
            log.error("scoring_failed", error=str(e))

    consumer.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
