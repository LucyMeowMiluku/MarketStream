import json
import signal
from collections import defaultdict
from datetime import datetime, timezone

from confluent_kafka import Consumer, Producer

from config.logging_config import get_logger
from config.settings import settings
from ml.detector import AnomalyDetector
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


def get_recent_sentiment(session, ticker: str, window_minutes: int = 5) -> tuple[float, float, int]:
    rows = (
        session.query(SentimentScore)
        .filter(SentimentScore.ticker == ticker)
        .order_by(SentimentScore.time.desc())
        .limit(20)
        .all()
    )
    if not rows:
        return 0.0, 0.0, 0

    recent = [r.sentiment_score for r in rows[:10]]
    older = [r.sentiment_score for r in rows[10:]]

    avg_sentiment = sum(recent) / len(recent)
    prev_avg = sum(older) / len(older) if older else avg_sentiment
    shift = avg_sentiment - prev_avg

    return round(avg_sentiment, 4), round(shift, 4), len(recent)


def build_anomaly_reason(features: dict, score: float) -> str:
    reasons = []
    if abs(features.get("price_change_rate", 0)) > 0.02:
        reasons.append(f"large price move ({features['price_change_rate']:.2%})")
    if features.get("total_volume", 0) > 1_000_000:
        reasons.append(f"high volume ({features['total_volume']:,})")
    if abs(features.get("sentiment_shift", 0)) > 0.3:
        reasons.append(f"sentiment shift ({features['sentiment_shift']:.2f})")
    if not reasons:
        reasons.append(f"anomaly score={score:.4f}")
    return "; ".join(reasons)


def main():
    detector = AnomalyDetector(model_path=MODEL_PATH)
    log.info("model_loaded", path=MODEL_PATH)

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
                avg_sentiment, sentiment_shift, headline_count = get_recent_sentiment(
                    session, ticker
                )

                enriched = {
                    **features,
                    "avg_sentiment": avg_sentiment,
                    "sentiment_shift": sentiment_shift,
                    "headline_count": headline_count,
                }

                score, is_anomaly = detector.predict(enriched)

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
                )
                session.add(fv)

                if is_anomaly:
                    alert = AnomalyAlert(
                        detected_at=datetime.now(timezone.utc),
                        ticker=ticker,
                        anomaly_score=score,
                        features=enriched,
                        reason=build_anomaly_reason(enriched, score),
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
                            }
                        ).encode(),
                    )
                    anomaly_producer.flush()

                    log.warning(
                        "anomaly_detected",
                        ticker=ticker,
                        score=f"{score:.4f}",
                        reason=alert.reason,
                    )

                session.commit()
                log.info("scored", ticker=ticker, score=f"{score:.4f}", anomaly=is_anomaly)
            finally:
                session.close()

        except Exception as e:
            log.error("scoring_failed", error=str(e))

    consumer.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
