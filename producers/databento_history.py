"""Quota-conscious Databento BBO/trades and event-day MBP-10 downloader."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from config.settings import settings

ALLOWED_SCHEMAS = ("bbo-1s", "trades", "mbp-10")


def download(
    *,
    dataset: str,
    symbols: list[str],
    schema: str,
    start: date,
    end: date,
    output: Path,
) -> Path:
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"schema must be one of {ALLOWED_SCHEMAS}")
    if schema == "mbp-10" and (end - start).days > 3:
        raise ValueError("MBP-10 downloads are capped at three event days per request")
    if settings.databento_api_key is None:
        raise RuntimeError("DATABENTO_API_KEY is required")
    try:
        import databento as db
    except ImportError as exc:
        raise RuntimeError("Install the optional Databento SDK before historical downloads") from exc
    client = db.Historical(settings.databento_api_key.get_secret_value())
    output.parent.mkdir(parents=True, exist_ok=True)
    data = client.timeseries.get_range(
        dataset=dataset,
        symbols=symbols,
        schema=schema,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    data.to_file(str(output))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download bounded Databento history")
    parser.add_argument("--dataset", default="XNAS.ITCH")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--schema", choices=ALLOWED_SCHEMAS, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    download(**vars(args))


if __name__ == "__main__":
    main()
