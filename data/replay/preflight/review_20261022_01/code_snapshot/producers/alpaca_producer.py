"""Live Alpaca IEX trades, quotes, bars, and timestamped news ingestion."""

from __future__ import annotations

import asyncio
import json
import re
import signal
from datetime import datetime, timezone
from typing import Any

import websockets
from confluent_kafka import Producer

from config.logging_config import get_logger
from config.settings import settings
from processing.event_models import EventType, MarketEvent

log = get_logger("alpaca_producer")
running = True

POSITIVE_WORDS = {
    "beat",
    "beats",
    "growth",
    "gain",
    "gains",
    "upgrade",
    "surge",
    "record",
    "profit",
    "strong",
}
NEGATIVE_WORDS = {
    "miss",
    "misses",
    "loss",
    "losses",
    "downgrade",
    "drop",
    "falls",
    "fraud",
    "weak",
    "probe",
}


def shutdown(sig, frame) -> None:
    del frame
    global running
    log.info("shutting_down", signal=sig)
    running = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def headline_sentiment(headline: str) -> float:
    """Small transparent lexical score; no model is loaded on the live path."""
    words = set(re.findall(r"[a-z]+", headline.lower()))
    positive = len(words.intersection(POSITIVE_WORDS))
    negative = len(words.intersection(NEGATIVE_WORDS))
    total = positive + negative
    return round((positive - negative) / total, 4) if total else 0.0


def _credentials() -> tuple[str, str]:
    if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_API_SECRET are required")
    return settings.alpaca_api_key.get_secret_value(), settings.alpaca_api_secret.get_secret_value()


def _stock_event(message: dict[str, Any]) -> MarketEvent | None:
    kind = message.get("T")
    event_time = message.get("t")
    ticker = message.get("S")
    if not event_time or not ticker:
        return None
    common = {
        "source": "alpaca",
        "feed": settings.alpaca_data_feed,
        "ticker": ticker,
        "event_time": event_time,
        "received_at": datetime.now(timezone.utc),
    }
    if kind == "t":
        return MarketEvent.create(
            **common,
            event_type=EventType.TRADE,
            event_id=str(message.get("i")) if message.get("i") is not None else None,
            trade={
                "price": message.get("p"),
                "size": message.get("s"),
                "exchange": message.get("x"),
                "conditions": message.get("c", []),
            },
        )
    if kind == "q":
        return MarketEvent.create(
            **common,
            event_type=EventType.QUOTE,
            quote={
                "bid_price": message.get("bp"),
                "ask_price": message.get("ap"),
                "bid_size": message.get("bs"),
                "ask_size": message.get("as"),
                "bid_exchange": message.get("bx"),
                "ask_exchange": message.get("ax"),
            },
        )
    if kind in {"b", "u", "d"}:
        return MarketEvent.create(
            **common,
            event_type=EventType.BAR,
            bar={
                "open": message.get("o"),
                "high": message.get("h"),
                "low": message.get("l"),
                "close": message.get("c"),
                "volume": message.get("v"),
                "trade_count": message.get("n"),
                "vwap": message.get("vw"),
            },
        )
    return None


def _news_events(message: dict[str, Any]) -> list[MarketEvent]:
    if message.get("T") != "n":
        return []
    tracked = set(settings.tickers)
    symbols = tracked.intersection(symbol.upper() for symbol in message.get("symbols", []))
    headline = str(message.get("headline", ""))
    event_time = message.get("created_at") or message.get("updated_at")
    if not headline or not event_time:
        return []
    return [
        MarketEvent.create(
            source="alpaca",
            feed="benzinga_news",
            event_type=EventType.NEWS,
            ticker=ticker,
            event_time=event_time,
            received_at=datetime.now(timezone.utc),
            event_id=f"{message.get('id', 'news')}:{ticker}",
            news={
                "headline": headline,
                "summary": message.get("summary", ""),
                "source": message.get("source", "unknown"),
                "sentiment_score": headline_sentiment(headline),
            },
        )
        for ticker in sorted(symbols)
    ]


def _publish(producer: Producer, event: MarketEvent) -> None:
    producer.produce(
        settings.raw_market_events_topic,
        key=event.ticker.encode(),
        value=json.dumps(event.to_dict()).encode(),
        headers=[("marketstream-mode", b"live")],
    )
    producer.poll(0)


async def _consume_stream(
    *,
    url: str,
    subscription: dict[str, Any],
    parser,
    producer: Producer,
) -> None:
    key, secret = _credentials()
    backoff = 1
    while running:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                backoff = 1
                authenticated = False
                while running:
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                    except TimeoutError:
                        continue
                    for message in json.loads(raw):
                        if message.get("T") == "error":
                            raise RuntimeError(
                                f"Alpaca stream error {message.get('code')}: "
                                f"{message.get('msg', 'unknown error')}"
                            )
                        if message.get("T") == "success" and message.get("msg") == "authenticated":
                            authenticated = True
                            await socket.send(json.dumps(subscription))
                            continue
                        if message.get("T") == "subscription":
                            log.info(
                                "stream_subscribed",
                                stream=url.rsplit("/", 1)[-1],
                                subscription=message,
                            )
                            continue
                        if not authenticated:
                            continue
                        parsed = parser(message)
                        events = parsed if isinstance(parsed, list) else [parsed]
                        for event in events:
                            if event is not None:
                                _publish(producer, event)
        except Exception as exc:
            log.warning("stream_disconnected", stream=url.rsplit("/", 1)[-1], error=str(exc))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def run() -> None:
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    symbols = list(settings.tickers)
    log.info(
        "started",
        symbols=symbols,
        feed=settings.alpaca_data_feed,
        coverage="IEX only; not consolidated SIP",
    )
    await asyncio.gather(
        _consume_stream(
            url=settings.alpaca_stock_stream_url,
            subscription={
                "action": "subscribe",
                "trades": symbols,
                "quotes": symbols,
                "bars": symbols,
            },
            parser=_stock_event,
            producer=producer,
        ),
        _consume_stream(
            url=settings.alpaca_news_stream_url,
            subscription={"action": "subscribe", "news": symbols},
            parser=_news_events,
            producer=producer,
        ),
    )
    producer.flush()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
