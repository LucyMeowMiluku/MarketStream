"""Collect and validate the 12-month MarketStream research dataset.

Daily OHLCV is downloaded from Yahoo Finance. Historical headlines use the
Alpaca News API when credentials are available and otherwise fall back to
date-bounded Google News RSS queries. The fallback is intentionally labelled
as a query corpus rather than a complete market-wide news feed.

Usage:
    uv run python -m scripts.collect_historical_dataset
    uv run python -m scripts.collect_historical_dataset --news-provider alpaca
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yfinance as yf

from config.settings import settings


COMPANY_QUERIES = {
    "AAPL": '(AAPL OR "Apple Inc")',
    "TSLA": '(TSLA OR Tesla)',
    "NVDA": '(NVDA OR Nvidia)',
    "QQQ": '(QQQ OR "Invesco QQQ")',
    "SPY": '(SPY OR "SPDR S&P 500 ETF")',
}
USER_AGENT = "MarketStream academic research/0.1"


def _request_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 4,
) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def _month_windows(start: date, end: date) -> Iterable[tuple[date, date]]:
    cursor = start
    while cursor < end:
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1, day=1)
        else:
            next_month = cursor.replace(month=cursor.month + 1, day=1)
        window_end = min(next_month, end)
        yield cursor, window_end
        cursor = window_end


def download_ohlcv(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        frame = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if frame.empty:
            continue
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.reset_index().rename(columns={"Date": "timestamp"})
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["ticker"] = ticker
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    columns = ["timestamp", "ticker", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    return pd.concat(frames, ignore_index=True)[columns].sort_values(
        ["timestamp", "ticker"]
    )


def _parse_google_rss(
    payload: bytes,
    *,
    ticker: str,
    window_start: date,
    window_end: date,
) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        if not title or not link or not published:
            continue
        published_at = parsedate_to_datetime(published).astimezone(timezone.utc)
        source_node = item.find("source")
        articles.append(
            {
                "ticker": ticker,
                "published_at": published_at.isoformat(),
                "headline": title,
                "url": link,
                "source": (source_node.text or "unknown").strip()
                if source_node is not None
                else "unknown",
                "provider": "google_news_rss",
                "query_window_start": window_start.isoformat(),
                "query_window_end": window_end.isoformat(),
            }
        )
    return articles


def download_google_news(tickers: list[str], start: date, end: date) -> tuple[list[dict], int]:
    articles: list[dict[str, Any]] = []
    capped_windows = 0
    for ticker in tickers:
        query = COMPANY_QUERIES.get(ticker, ticker)
        for window_start, window_end in _month_windows(start, end):
            bounded_query = (
                f"{query} after:{window_start.isoformat()} before:{window_end.isoformat()}"
            )
            params = urllib.parse.urlencode(
                {"q": bounded_query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
            )
            payload = _request_bytes(f"https://news.google.com/rss/search?{params}")
            window_articles = _parse_google_rss(
                payload,
                ticker=ticker,
                window_start=window_start,
                window_end=window_end,
            )
            if len(window_articles) >= 100:
                capped_windows += 1
            articles.extend(window_articles)
            time.sleep(0.15)

    unique: dict[tuple[str, str], dict] = {}
    for article in articles:
        unique[(article["ticker"], article["url"])] = article
    return sorted(unique.values(), key=lambda row: (row["published_at"], row["ticker"])), capped_windows


def download_alpaca_news(tickers: list[str], start: date, end: date) -> list[dict]:
    if settings.alpaca_api_key is None or settings.alpaca_api_secret is None:
        raise RuntimeError("Alpaca credentials are required for --news-provider alpaca")
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key.get_secret_value(),
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret.get_secret_value(),
    }
    base_params = {
        "symbols": ",".join(tickers),
        "start": datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
        "end": datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc).isoformat(),
        "sort": "asc",
        "limit": "50",
        "include_content": "false",
        "exclude_contentless": "true",
    }
    articles: list[dict] = []
    page_token: str | None = None
    while True:
        params = dict(base_params)
        if page_token:
            params["page_token"] = page_token
        payload = _request_bytes(
            "https://data.alpaca.markets/v1beta1/news?" + urllib.parse.urlencode(params),
            headers=headers,
        )
        body = json.loads(payload)
        for article in body.get("news", []):
            for ticker in sorted(set(article.get("symbols", [])).intersection(tickers)):
                articles.append(
                    {
                        "ticker": ticker,
                        "published_at": article["created_at"],
                        "headline": article.get("headline", ""),
                        "url": article.get("url", ""),
                        "source": article.get("source", "unknown"),
                        "provider": "alpaca_benzinga",
                        "article_id": article.get("id"),
                    }
                )
        page_token = body.get("next_page_token")
        if not page_token:
            break
    return articles


def _coverage(
    values: pd.Series,
    *,
    expected_start: date,
    expected_end: date,
    minimum_rows: int,
    boundary_tolerance_days: int,
) -> dict[str, Any]:
    timestamps = pd.to_datetime(values, utc=True).dropna().sort_values()
    if timestamps.empty:
        return {"rows": 0, "passed": False}
    first = timestamps.iloc[0].date()
    last = timestamps.iloc[-1].date()
    span_days = (last - first).days
    passed = (
        len(timestamps) >= minimum_rows
        and first <= expected_start + timedelta(days=boundary_tolerance_days)
        and last >= expected_end - timedelta(days=boundary_tolerance_days)
        and span_days >= 365
    )
    return {
        "rows": int(len(timestamps)),
        "first": first.isoformat(),
        "last": last.isoformat(),
        "span_days": span_days,
        "passed": passed,
    }


def build_manifest(
    ohlcv: pd.DataFrame,
    news: list[dict],
    *,
    tickers: list[str],
    start: date,
    end: date,
    news_provider: str,
    capped_windows: int,
) -> dict[str, Any]:
    ohlcv_coverage = {
        ticker: _coverage(
            ohlcv.loc[ohlcv["ticker"] == ticker, "timestamp"]
            if not ohlcv.empty
            else pd.Series(dtype="datetime64[ns, UTC]"),
            expected_start=start,
            expected_end=end,
            minimum_rows=252,
            boundary_tolerance_days=10,
        )
        for ticker in tickers
    }
    news_frame = pd.DataFrame(news)
    news_coverage = {
        ticker: _coverage(
            news_frame.loc[news_frame["ticker"] == ticker, "published_at"]
            if not news_frame.empty
            else pd.Series(dtype="datetime64[ns, UTC]"),
            expected_start=start,
            expected_end=end,
            minimum_rows=12,
            boundary_tolerance_days=45,
        )
        for ticker in tickers
    }

    unique_dates = sorted(pd.to_datetime(ohlcv["timestamp"], utc=True).dt.date.unique())
    train_end = unique_dates[int(len(unique_dates) * 0.6) - 1]
    validation_end = unique_dates[int(len(unique_dates) * 0.8) - 1]
    gates = {
        "ohlcv_12_months": all(row["passed"] for row in ohlcv_coverage.values()),
        "news_12_months": all(row["passed"] for row in news_coverage.values()),
    }
    gates["historical_dataset"] = all(gates.values())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "tickers": tickers,
        "ohlcv": {
            "provider": "yahoo_finance",
            "interval": "1d",
            "coverage": ohlcv_coverage,
        },
        "news": {
            "provider": news_provider,
            "coverage": news_coverage,
            "capped_query_windows": capped_windows,
            "completeness_note": (
                "Date-bounded query corpus; not a complete consolidated news archive."
                if news_provider == "google_news_rss"
                else "Alpaca historical news sourced from Benzinga."
            ),
        },
        "temporal_split": {
            "train": [start.isoformat(), train_end.isoformat()],
            "validation": [
                (train_end + timedelta(days=1)).isoformat(),
                validation_end.isoformat(),
            ],
            "test": [(validation_end + timedelta(days=1)).isoformat(), end.isoformat()],
            "ratio": "60/20/20",
        },
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=400)
    parser.add_argument(
        "--news-provider", choices=("auto", "alpaca", "google-rss"), default="auto"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/historical"))
    args = parser.parse_args()

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days)
    tickers = list(settings.tickers)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading daily OHLCV for {tickers}: {start} to {end}")
    ohlcv = download_ohlcv(tickers, start, end)
    ohlcv_path = args.output_dir / "ohlcv_1d_12m.csv"
    ohlcv.to_csv(ohlcv_path, index=False)

    provider = args.news_provider
    if provider == "auto":
        provider = (
            "alpaca"
            if settings.alpaca_api_key is not None and settings.alpaca_api_secret is not None
            else "google-rss"
        )
    print(f"Downloading historical news with provider={provider}")
    if provider == "alpaca":
        news = download_alpaca_news(tickers, start, end)
        manifest_provider = "alpaca_benzinga"
        capped_windows = 0
    else:
        news, capped_windows = download_google_news(tickers, start, end)
        manifest_provider = "google_news_rss"

    news_path = args.output_dir / "news_12m.jsonl"
    with news_path.open("w", encoding="utf-8") as handle:
        for article in news:
            handle.write(json.dumps(article, ensure_ascii=False) + "\n")

    manifest = build_manifest(
        ohlcv,
        news,
        tickers=tickers,
        start=start,
        end=end,
        news_provider=manifest_provider,
        capped_windows=capped_windows,
    )
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest["gates"], indent=2))
    print(f"OHLCV: {ohlcv_path} ({len(ohlcv)} rows)")
    print(f"News:  {news_path} ({len(news)} rows)")
    print(f"Manifest: {manifest_path}")
    return 0 if manifest["gates"]["historical_dataset"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
