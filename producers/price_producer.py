import json
import signal
import time

import yfinance as yf
from confluent_kafka import Producer

from config.logging_config import get_logger
from config.settings import settings

log = get_logger("price_producer")

running = True


def shutdown(sig, frame):
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def delivery_report(err, msg):
    if err:
        log.error("delivery_failed", error=str(err))


def fetch_latest_prices(ticker: str) -> list[dict]:
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1d", interval="1m")
    if hist.empty:
        return []

    records = []
    for ts, row in hist.tail(1).iterrows():
        records.append(
            {
                "ticker": ticker,
                "timestamp": ts.isoformat(),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            }
        )
    return records


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
    log.info("started", tickers=settings.tickers)

    while running:
        for ticker in settings.tickers:
            try:
                records = _fetch_with_retry(fetch_latest_prices, ticker)
                if not records:
                    continue
                for record in records:
                    producer.produce(
                        "raw.prices",
                        key=ticker.encode(),
                        value=json.dumps(record).encode(),
                        callback=delivery_report,
                    )
                    log.info(
                        "produced_price",
                        ticker=ticker,
                        close=record["close"],
                        volume=record["volume"],
                    )
            except Exception as e:
                log.error("fetch_failed", ticker=ticker, error=str(e))

        producer.flush()
        time.sleep(settings.price_poll_interval_seconds)

    producer.flush()
    log.info("stopped")


if __name__ == "__main__":
    main()
