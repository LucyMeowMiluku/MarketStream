"""Replay JSONL MarketEvents through the same raw Kafka topic as live data."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from confluent_kafka import Producer

from config.logging_config import get_logger
from config.settings import settings
from processing.event_models import MarketEvent

log = get_logger("replay_producer")

#从本地jsonl文件中加载处理过的 MarketEvent数据,并返回一个排序后的列表
def load_events(path: Path) -> list[MarketEvent]:
    events = []
    with path.open() as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                events.append(MarketEvent.from_dict(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"invalid MarketEvent at line {line_number}: {exc}") from exc
    return sorted(events, key=lambda event: (event.event_time, event.event_id))

#将历史replay数据推送到kafka的topic
def replay(path: Path, *, speed: float = 1.0, wait: bool = True) -> int:
    if speed <= 0:
        raise ValueError("speed must be positive")
    events = load_events(path)
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    previous = None
    for event in events:
        if wait and previous is not None:
            delay = max(0.0, (event.event_time - previous).total_seconds() / speed)
            if delay:
                time.sleep(delay)
        producer.produce(                       #主要函数
            settings.raw_market_events_topic,
            key=event.ticker.encode(),
            value=json.dumps(event.to_dict()).encode(),
            headers=[("marketstream-mode", b"replay")],
        )
        producer.poll(0)
        previous = event.event_time
    producer.flush()
    log.info("replay_complete", events=len(events), source=str(path), speed=speed)
    return len(events)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay MarketEvent JSONL through Kafka")
    parser.add_argument("path", type=Path)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--no-wait", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    replay(args.path, speed=args.speed, wait=not args.no_wait)


if __name__ == "__main__":
    main()
