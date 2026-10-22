"""
Resumable Alpaca IEX historical collection into canonical MarketEvent JSONL."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from config.settings import settings
from processing.event_models import EventType, MarketEvent, as_utc, bar_timing
from producers.alpaca_producer import headline_sentiment
from replay.labels import LabelRegistry, load_label_registry
from replay.models import ReviewedInterval, file_sha256

API_BASE = "https://data.alpaca.markets"
# v2: bars are keyed by completion time and carry their interval explicitly.
CONVERTER_VERSION = "alpaca-market-event-v2"


class AlpacaHistoricalClient:
    def __init__(
        self,
        key: str,
        secret: str,
        *,
        timeout_seconds: float = 30,
        max_retries: int = 5,
    ) -> None:
        self.headers = {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        }
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    @classmethod
    def from_settings(cls) -> AlpacaHistoricalClient:
        if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_API_SECRET are required")
        return cls(
            settings.alpaca_api_key.get_secret_value(),
            settings.alpaca_api_secret.get_secret_value(),
        )

    def request_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
        request = urllib.request.Request(f"{API_BASE}{path}?{query}", headers=self.headers)
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 >= self.max_retries:
                    raise RuntimeError(f"Alpaca request failed with HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt + 1 >= self.max_retries:
                    raise RuntimeError("Alpaca request failed after retries") from exc
                delay = min(2**attempt, 30)
            time.sleep(delay)
        raise RuntimeError("unreachable retry state")

    def iter_pages(
        self,
        path: str,
        params: dict[str, Any],
        *,
        row_key: str,
        initial_token: str | None = None,
    ) -> Iterator[tuple[list[dict[str, Any]], str | None]]:
        token = initial_token
        while True:
            page_params = {**params, "page_token": token}
            payload = self.request_json(path, page_params)
            rows = payload.get(row_key, [])
            if not isinstance(rows, list):
                raise ValueError(f"Alpaca response field {row_key!r} is not a list")
            token = payload.get("next_page_token")
            yield rows, token
            if not token:
                break

    def download_rows(
        self,
        path: str,
        params: dict[str, Any],
        *,
        row_key: str,
        output: Path,
    ) -> dict[str, Any]:
        state_path = output.with_suffix(output.suffix + ".state.json")
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        expected_request = {"path": path, "params": params, "row_key": row_key}
        if state and any(state.get(key) != value for key, value in expected_request.items()):
            raise ValueError(f"checkpoint request does not match current request: {state_path}")
        if state and not output.exists():
            state = {}
        if state.get("complete") and output.exists():
            return state
        output.parent.mkdir(parents=True, exist_ok=True)
        token = state.get("next_page_token")
        count = int(state.get("rows", 0))
        pages = int(state.get("pages", 0))
        mode = "a" if output.exists() and state else "w"
        with output.open(mode) as destination:
            for rows, token in self.iter_pages(
                path,
                params,
                row_key=row_key,
                initial_token=token,
            ):
                for row in rows:
                    destination.write(json.dumps(row, separators=(",", ":")) + "\n")
                destination.flush()
                count += len(rows)
                pages += 1
                state = {
                    "complete": token is None,
                    "rows": count,
                    "pages": pages,
                    "next_page_token": token,
                    "path": path,
                    "params": params,
                    "row_key": row_key,
                }
                state_path.write_text(json.dumps(state, indent=2) + "\n")
        return state


def _provider_id(row: dict[str, Any], fallback: str) -> str:
    value = row.get("i") or row.get("id")
    return str(value) if value is not None else hashlib.sha256(fallback.encode()).hexdigest()[:24]


def stock_row_to_event(
    kind: str,
    ticker: str,
    row: dict[str, Any],
    *,
    dataset_id: str,
    interval_id: str,
    phase: str,
    timeframe: str = "1Min",
) -> MarketEvent:
    event_time = as_utc(row["t"])
    fallback = f"{ticker}:{kind}:{event_time.isoformat()}:{json.dumps(row, sort_keys=True)}"
    provider_id = _provider_id(row, fallback)
    common = {
        "source": "alpaca",
        "feed": "iex",
        "ticker": ticker,
        "event_time": event_time,
        "received_at": event_time,
        "event_id": f"alpaca:iex:{kind}:{ticker}:{provider_id}",
        "dataset_id": dataset_id,
        "mode": "replay_real",
        "provenance": {
            "provider": "alpaca",
            "provider_event_id": provider_id,
            "interval_id": interval_id,
            "phase": phase,
            "converter_version": CONVERTER_VERSION,
        },
    }
    if kind == "trade":
        return MarketEvent.create(
            **common,
            event_type=EventType.TRADE,
            trade={
                "price": row.get("p"),
                "size": row.get("s"),
                "exchange": row.get("x"),
                "conditions": row.get("c", []),
                "tape": row.get("z"),
            },
        )
    if kind == "quote":
        return MarketEvent.create(
            **common,
            event_type=EventType.QUOTE,
            quote={
                "bid_price": row.get("bp"),
                "ask_price": row.get("ap"),
                "bid_size": row.get("bs"),
                "ask_size": row.get("as"),
                "bid_exchange": row.get("bx"),
                "ask_exchange": row.get("ax"),
                "conditions": row.get("c", []),
                "tape": row.get("z"),
            },
        )
    if kind == "bar":
        # Bars are keyed by completion, not by the provider's interval start;
        # the historical API exposes no publication time, so arrival is
        # assumed to coincide with completion.
        timing = bar_timing(row["t"], timeframe)
        return MarketEvent.create(
            **{
                **common,
                "event_time": timing["completed_at"],
                "received_at": timing["completed_at"],
                "provenance": {
                    **common["provenance"],
                    "received_at_basis": "assumed_at_completion",
                },
            },
            event_type=EventType.BAR,
            bar={
                **timing["payload"],
                "open": row.get("o"),
                "high": row.get("h"),
                "low": row.get("l"),
                "close": row.get("c"),
                "volume": row.get("v"),
                "trade_count": row.get("n"),
                "vwap": row.get("vw"),
            },
        )
    raise ValueError(f"unsupported stock row kind: {kind}")


def news_row_to_events(
    row: dict[str, Any],
    *,
    symbols: set[str],
    dataset_id: str,
    interval_id: str,
    phase: str,
) -> list[MarketEvent]:
    event_time = row.get("created_at") or row.get("updated_at")
    headline = str(row.get("headline", "")).strip()
    if not event_time or not headline:
        return []
    provider_id = str(row.get("id") or f"{event_time}:{headline}")
    matched = symbols.intersection(str(item).upper() for item in row.get("symbols", []))
    return [
        MarketEvent.create(
            source="alpaca",
            feed="benzinga_news",
            event_type=EventType.NEWS,
            ticker=ticker,
            event_time=event_time,
            received_at=event_time,
            event_id=f"alpaca:benzinga:news:{provider_id}:{ticker}",
            news={
                "headline": headline,
                "summary": row.get("summary", ""),
                "source": row.get("source", "benzinga"),
                "url": row.get("url"),
                "sentiment_score": headline_sentiment(headline),
            },
            dataset_id=dataset_id,
            mode="replay_real",
            provenance={
                "provider": "alpaca_benzinga",
                "provider_event_id": provider_id,
                "interval_id": interval_id,
                "phase": phase,
                "converter_version": CONVERTER_VERSION,
            },
        )
        for ticker in sorted(matched)
    ]


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open() as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def _convert_rows(
    raw_path: Path,
    output: Path,
    converter: Callable[[dict[str, Any]], list[MarketEvent]],
) -> dict[str, Any]:
    complete_path = output.with_suffix(output.suffix + ".complete.json")
    if complete_path.exists() and output.exists():
        return json.loads(complete_path.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w") as destination:
        for row in _iter_jsonl(raw_path):
            for event in converter(row):
                destination.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
                count += 1
    state = {"complete": True, "events": count, "sha256": file_sha256(output)}
    complete_path.write_text(json.dumps(state, indent=2) + "\n")
    return state


def _merge_event_parts(parts: list[Path], output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    first_time: datetime | None = None
    last_time: datetime | None = None
    seen: set[str] = set()
    with ExitStack() as stack, output.open("w") as destination:
        sources = [stack.enter_context(path.open()) for path in parts if path.exists()]
        heap: list[tuple[datetime, str, int, dict[str, Any]]] = []
        for index, source in enumerate(sources):
            line = source.readline()
            if line:
                value = json.loads(line)
                heapq.heappush(
                    heap,
                    (as_utc(value["event_time"]), value["event_id"], index, value),
                )
        while heap:
            event_time, event_id, index, value = heapq.heappop(heap)
            if event_id not in seen:
                event = MarketEvent.from_dict(value)
                destination.write(json.dumps(event.to_dict(), separators=(",", ":")) + "\n")
                seen.add(event_id)
                counts[event.event_type.value] += 1
                first_time = event_time if first_time is None else min(first_time, event_time)
                last_time = event_time if last_time is None else max(last_time, event_time)
            line = sources[index].readline()
            if line:
                following = json.loads(line)
                heapq.heappush(
                    heap,
                    (
                        as_utc(following["event_time"]),
                        following["event_id"],
                        index,
                        following,
                    ),
                )
    return {
        "path": str(output.resolve()),
        "sha256": file_sha256(output),
        "events": sum(counts.values()),
        "event_types": dict(sorted(counts.items())),
        "first_event_time": first_time.isoformat() if first_time else None,
        "last_event_time": last_time.isoformat() if last_time else None,
    }


class AlpacaReplayCollector:
    def __init__(self, client: AlpacaHistoricalClient) -> None:
        self.client = client

    def previous_sessions(
        self,
        ticker: str,
        before: datetime,
        *,
        count: int,
        timezone_name: str,
    ) -> list[date]:
        local = before.astimezone(ZoneInfo(timezone_name))
        payload = self.client.request_json(
            f"/v2/stocks/{ticker}/bars",
            {
                "start": (local.date() - timedelta(days=max(90, count * 5))).isoformat(),
                "end": local.date().isoformat(),
                "timeframe": "1Day",
                "feed": "iex",
                "adjustment": "raw",
                "limit": 10_000,
                "sort": "asc",
            },
        )
        sessions = sorted(
            {
                as_utc(row["t"]).astimezone(ZoneInfo(timezone_name)).date()
                for row in payload.get("bars", [])
                if as_utc(row["t"]).astimezone(ZoneInfo(timezone_name)).date() < local.date()
            }
        )
        if len(sessions) < count:
            raise ValueError(
                f"{ticker}: only {len(sessions)} prior IEX sessions available; need {count}"
            )
        return sessions[-count:]

    def _collect_window(
        self,
        *,
        registry: LabelRegistry,
        interval: ReviewedInterval,
        started_at: datetime,
        ended_at: datetime,
        phase: str,
        window_id: str,
        directory: Path,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        symbols = interval.symbols
        raw_dir = directory / "provider_rows" / phase / window_id
        event_dir = directory / "event_parts" / phase / window_id
        parts: list[Path] = []
        requests: list[dict[str, Any]] = []
        for ticker in symbols:
            for kind in ("trade", "quote", "bar"):
                plural = {"trade": "trades", "quote": "quotes", "bar": "bars"}[kind]
                params = {
                    "start": started_at.isoformat(),
                    "end": ended_at.isoformat(),
                    "feed": "iex",
                    "limit": 10_000,
                    "sort": "asc",
                }
                if kind == "bar":
                    params["timeframe"] = "1Min"
                    params["adjustment"] = "raw"
                raw_path = raw_dir / f"{ticker}.{plural}.jsonl"
                state = self.client.download_rows(
                    f"/v2/stocks/{ticker}/{plural}",
                    params,
                    row_key=plural,
                    output=raw_path,
                )
                event_path = event_dir / f"{ticker}.{plural}.jsonl"
                conversion = _convert_rows(
                    raw_path,
                    event_path,
                    # A bar that completes after the window end was not yet
                    # available inside the window, so it is not part of it.
                    lambda row, kind=kind, ticker=ticker: [
                        event
                        for event in [
                            stock_row_to_event(
                                kind,
                                ticker,
                                row,
                                dataset_id=registry.dataset_id,
                                interval_id=interval.interval_id,
                                phase=phase,
                            )
                        ]
                        if event.event_time <= ended_at
                    ],
                )
                parts.append(event_path)
                requests.append(
                    {
                        "window_id": window_id,
                        "phase": phase,
                        "ticker": ticker,
                        "kind": kind,
                        "provider": "alpaca",
                        "feed": "iex",
                        "started_at": started_at.isoformat(),
                        "ended_at": ended_at.isoformat(),
                        "provider_rows": state["rows"],
                        "provider_rows_sha256": file_sha256(raw_path),
                        "events": conversion["events"],
                        "events_sha256": conversion["sha256"],
                        "pages": state["pages"],
                        "complete": state["complete"],
                    }
                )
        news_params = {
            "symbols": ",".join(symbols),
            "start": started_at.isoformat(),
            "end": ended_at.isoformat(),
            "limit": 50,
            "sort": "asc",
        }
        news_raw = raw_dir / "news.jsonl"
        news_state = self.client.download_rows(
            "/v1beta1/news",
            news_params,
            row_key="news",
            output=news_raw,
        )
        news_events = event_dir / "news.jsonl"
        news_conversion = _convert_rows(
            news_raw,
            news_events,
            lambda row: news_row_to_events(
                row,
                symbols=set(symbols),
                dataset_id=registry.dataset_id,
                interval_id=interval.interval_id,
                phase=phase,
            ),
        )
        parts.append(news_events)
        requests.append(
            {
                "window_id": window_id,
                "phase": phase,
                "ticker": ",".join(symbols),
                "kind": "news",
                "provider": "alpaca_benzinga",
                "feed": "benzinga_news",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "provider_rows": news_state["rows"],
                "provider_rows_sha256": file_sha256(news_raw),
                "events": news_conversion["events"],
                "events_sha256": news_conversion["sha256"],
                "pages": news_state["pages"],
                "complete": news_state["complete"],
            }
        )
        return parts, requests

    def collect(
        self,
        registry: LabelRegistry,
        output_root: Path,
        *,
        baseline_days: int = 20,
    ) -> dict[str, Any]:
        registry.validate(
            require_frozen=True,
            expected_anomalies=12,
            expected_normals=12,
        )
        dataset_dir = output_root / registry.dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        timezone_name = registry.timezone
        local_zone = ZoneInfo(timezone_name)
        interval_manifests = []
        for interval in registry.intervals:
            interval_dir = dataset_dir / "intervals" / interval.interval_id
            local_start = interval.started_at.astimezone(local_zone)
            local_end = interval.ended_at.astimezone(local_zone)
            sessions = self.previous_sessions(
                interval.ticker,
                interval.started_at,
                count=baseline_days,
                timezone_name=timezone_name,
            )
            baseline_parts: list[Path] = []
            requests: list[dict[str, Any]] = []
            baseline_windows = []
            for session in sessions:
                start = datetime.combine(session, local_start.timetz()).astimezone(timezone.utc)
                end = datetime.combine(session, local_end.timetz()).astimezone(timezone.utc)
                window_id = session.isoformat()
                parts, rows = self._collect_window(
                    registry=registry,
                    interval=interval,
                    started_at=start,
                    ended_at=end,
                    phase="baseline",
                    window_id=window_id,
                    directory=interval_dir,
                )
                baseline_parts.extend(parts)
                requests.extend(rows)
                baseline_windows.append({"session": window_id, "started_at": start.isoformat(), "ended_at": end.isoformat()})
            evaluation_parts, rows = self._collect_window(
                registry=registry,
                interval=interval,
                started_at=interval.started_at,
                ended_at=interval.ended_at,
                phase="evaluation",
                window_id=interval.interval_id,
                directory=interval_dir,
            )
            requests.extend(rows)
            baseline_file = interval_dir / "baseline.events.jsonl"
            evaluation_file = interval_dir / "evaluation.events.jsonl"
            baseline_summary = _merge_event_parts(baseline_parts, baseline_file)
            evaluation_summary = _merge_event_parts(evaluation_parts, evaluation_file)
            interval_manifest = {
                "interval_id": interval.interval_id,
                "kind": interval.kind,
                "ticker": interval.ticker,
                "symbols": list(interval.symbols),
                "started_at": interval.started_at.isoformat(),
                "ended_at": interval.ended_at.isoformat(),
                "baseline_windows": baseline_windows,
                "baseline": baseline_summary,
                "evaluation": evaluation_summary,
                "requests": requests,
            }
            (interval_dir / "manifest.json").write_text(
                json.dumps(interval_manifest, indent=2) + "\n"
            )
            interval_manifests.append(interval_manifest)
        manifest = {
            "schema_version": "marketstream-real-replay-dataset-v1",
            "dataset_id": registry.dataset_id,
            "data_kind": "real_historical",
            "provider": "alpaca",
            "feed": "iex",
            "coverage": "Alpaca IEX only; not consolidated SIP",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "converter_version": CONVERTER_VERSION,
            "labels_sha256": registry.digest,
            "baseline_days": baseline_days,
            "intervals": interval_manifests,
        }
        manifest_path = dataset_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a reviewed Alpaca IEX replay dataset")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/replay/raw"))
    parser.add_argument("--baseline-days", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_label_registry(args.labels)
    collector = AlpacaReplayCollector(AlpacaHistoricalClient.from_settings())
    manifest = collector.collect(registry, args.output_root, baseline_days=args.baseline_days)
    print(
        json.dumps(
            {
                "status": "collected",
                "dataset_id": manifest["dataset_id"],
                "intervals": len(manifest["intervals"]),
                "manifest": str(args.output_root / manifest["dataset_id"] / "manifest.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
