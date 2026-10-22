"""Credential-safe Alpaca WebSocket authentication and schema smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

from config.settings import settings
from producers.alpaca_producer import _credentials, _news_events, _stock_event


async def probe_stream(
    *,
    name: str,
    url: str,
    subscription: dict[str, Any],
    require_data: bool,
    timeout_seconds: float,
) -> dict[str, Any]:
    key, secret = _credentials()
    result: dict[str, Any] = {
        "name": name,
        "url": url,
        "authenticated": False,
        "subscribed": False,
        "data_messages": 0,
        "parsed_market_events": 0,
        "message_types": [],
        "timed_out_waiting_for_data": False,
    }
    message_types: set[str] = set()
    try:
        async with asyncio.timeout(timeout_seconds):
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                async for raw in socket:
                    for message in json.loads(raw):
                        message_type = str(message.get("T", "unknown"))
                        message_types.add(message_type)
                        if message_type == "error":
                            raise RuntimeError(
                                f"{name}: Alpaca error {message.get('code')}: "
                                f"{message.get('msg', 'unknown error')}"
                            )
                        if message_type == "success" and message.get("msg") == "authenticated":
                            result["authenticated"] = True
                            await socket.send(json.dumps(subscription))
                            continue
                        if message_type == "subscription":
                            result["subscribed"] = True
                            if not require_data:
                                result["message_types"] = sorted(message_types)
                                return result
                            continue
                        if message_type in {"t", "q", "b", "u", "d", "n"}:
                            result["data_messages"] += 1
                            if name == "stocks":
                                parsed = _stock_event(message)
                                parsed_events = [parsed] if parsed is not None else []
                            else:
                                parsed_events = _news_events(message)
                            result["parsed_market_events"] += len(parsed_events)
                            if result["subscribed"] and result["parsed_market_events"]:
                                result["message_types"] = sorted(message_types)
                                return result
    except TimeoutError:
        result["timed_out_waiting_for_data"] = require_data and result["subscribed"]
    result["message_types"] = sorted(message_types)
    return result


async def run_probe(timeout_seconds: float) -> dict[str, Any]:
    symbols = list(settings.tickers)
    started_at = datetime.now(timezone.utc)
    stock_probe, news_probe = await asyncio.gather(
        probe_stream(
            name="stocks",
            url=settings.alpaca_stock_stream_url,
            subscription={
                "action": "subscribe",
                "trades": symbols,
                "quotes": symbols,
                "bars": symbols,
            },
            require_data=True,
            timeout_seconds=timeout_seconds,
        ),
        probe_stream(
            name="news",
            url=settings.alpaca_news_stream_url,
            subscription={"action": "subscribe", "news": symbols},
            require_data=False,
            timeout_seconds=timeout_seconds,
        ),
    )
    control_plane_gate = (
        stock_probe["authenticated"]
        and stock_probe["subscribed"]
        and news_probe["authenticated"]
        and news_probe["subscribed"]
    )
    protocol_gate = (
        stock_probe["authenticated"]
        and stock_probe["subscribed"]
        and stock_probe["parsed_market_events"] > 0
        and news_probe["authenticated"]
        and news_probe["subscribed"]
    )
    is_non_live_probe = settings.alpaca_data_feed in {"test", "delayed_sip"}
    live_gate = protocol_gate and not is_non_live_probe
    coverage = {
        "iex": "IEX only; not consolidated SIP",
        "sip": "Consolidated SIP feed",
        "test": "Alpaca FAKEPACA synthetic protocol stream; not market data",
        "delayed_sip": "Consolidated SIP market data delayed by 15 minutes; not real-time",
    }.get(settings.alpaca_data_feed, f"Alpaca feed={settings.alpaca_data_feed}")
    return {
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "stock_feed": settings.alpaca_data_feed,
        "coverage": coverage,
        "probes": {"stocks": stock_probe, "news": news_probe},
        "status": "passed" if (protocol_gate if is_non_live_probe else live_gate) else "failed",
        "gates": {
            "alpaca_control_plane": control_plane_gate,
            "alpaca_websocket_protocol": protocol_gate,
            "alpaca_live_stream": live_gate,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=90)
    parser.add_argument(
        "--output", type=Path, default=Path("data/evaluation/alpaca_live_smoke.json")
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "reason": "ALPACA_API_KEY and ALPACA_API_SECRET are not present in the environment",
            "gates": {"alpaca_live_stream": None},
        }
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    try:
        report = asyncio.run(run_probe(args.timeout_seconds))
    except Exception as exc:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "gates": {"alpaca_live_stream": False},
        }
    serialized = json.dumps(report, indent=2)
    args.output.write_text(serialized, encoding="utf-8")
    attempts_dir = args.output.parent / "alpaca_smoke_attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ.json")
    (attempts_dir / attempt_name).write_text(serialized, encoding="utf-8")
    print(serialized)
    target_gate = (
        "alpaca_websocket_protocol"
        if settings.alpaca_data_feed in {"test", "delayed_sip"}
        else "alpaca_live_stream"
    )
    return 0 if report["gates"].get(target_gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
