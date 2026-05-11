import json
import signal
import time
from collections import OrderedDict
from datetime import datetime, timezone

import yfinance as yf
from confluent_kafka import Producer
from transformers import pipeline

from config.logging_config import get_logger
from config.settings import settings
from storage.db import get_session
from storage.models import SentimentScore

log = get_logger("news_producer")

running = True

MAX_SEEN = 1000
seen_titles: OrderedDict[str, None] = OrderedDict()


def _mark_seen(title: str) -> bool:
    if title in seen_titles:
        return True
    seen_titles[title] = None
    if len(seen_titles) > MAX_SEEN:
        seen_titles.popitem(last=False)
    return False


def shutdown(sig, frame):
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def delivery_report(err, msg):
    if err:
        log.error("delivery_failed", error=str(err))


def load_sentiment_model():
    log.info("loading_finbert_model")
    model = pipeline(
        "sentiment-analysis",
        model="ProsusAI/finbert",
        tokenizer="ProsusAI/finbert",
    )
    log.info("model_loaded")
    return model


def score_sentiment(model, text: str) -> tuple[str, float]:
    result = model(text, truncation=True, max_length=512)[0]
    label = result["label"]
    score = result["score"]
    if label == "negative":
        return label, -score
    elif label == "positive":
        return label, score
    return "neutral", 0.0


def fetch_news(ticker: str) -> list[dict]:
    tk = yf.Ticker(ticker)
    news = tk.news
    if not news:
        return []

    articles = []
    for item in news:
        content = item.get("content", item)
        title = content.get("title", "")
        if not title or _mark_seen(title):
            continue
        provider = content.get("provider", {})
        articles.append(
            {
                "title": title,
                "publisher": provider.get("displayName", "unknown")
                if isinstance(provider, dict)
                else str(provider),
            }
        )
    return articles


MAX_RETRIES = 3


def _fetch_with_retry(func, *args):
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args)
        except Exception as e:
            wait = min(2**attempt * 5, 60)
            log.warning("retry", attempt=attempt + 1, wait=wait, error=str(e))
            time.sleep(wait)
    log.error("max_retries_exceeded", func=func.__name__)
    return None


def main():
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    sentiment_model = load_sentiment_model()
    log.info("started", tickers=settings.tickers)

    while running:
        for ticker in settings.tickers:
            try:
                articles = _fetch_with_retry(fetch_news, ticker)
                if not articles:
                    continue

                scored = []
                for article in articles:
                    label, score = score_sentiment(
                        sentiment_model, article["title"]
                    )
                    scored.append(
                        {
                            "ticker": ticker,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "headline": article["title"],
                            "source": article["publisher"],
                            "sentiment_score": round(score, 4),
                            "sentiment_label": label,
                        }
                    )

                session = get_session()
                try:
                    for record in scored:
                        session.add(
                            SentimentScore(
                                time=datetime.now(timezone.utc),
                                ticker=ticker,
                                headline=record["headline"],
                                source=record["source"],
                                sentiment_score=record["sentiment_score"],
                                sentiment_label=record["sentiment_label"],
                            )
                        )
                    session.commit()
                except Exception as e:
                    session.rollback()
                    log.error("db_write_failed", ticker=ticker, error=str(e))
                    continue
                finally:
                    session.close()

                for record in scored:
                    producer.produce(
                        "raw.news_sentiment",
                        key=ticker.encode(),
                        value=json.dumps(record).encode(),
                        callback=delivery_report,
                    )
                    log.info(
                        "produced_sentiment",
                        ticker=ticker,
                        label=record["sentiment_label"],
                        score=record["sentiment_score"],
                        headline=record["headline"][:60],
                    )
            except Exception as e:
                log.error("news_fetch_failed", ticker=ticker, error=str(e))

        producer.flush()
        time.sleep(settings.news_poll_interval_seconds)

    producer.flush()
    log.info("stopped")


if __name__ == "__main__":
    main()
