def price_change_rate(first_close: float, last_close: float) -> float:
    if first_close == 0:
        return 0.0
    return round((last_close - first_close) / first_close, 6)


def volume_surge_ratio(window_volume: int, baseline_volume: float) -> float:
    if baseline_volume == 0:
        return 0.0
    return round(window_volume / baseline_volume, 4)


def sentiment_shift(current_avg: float, previous_avg: float) -> float:
    return round(current_avg - previous_avg, 4)


def compute_window_features(window_value: dict, ticker: str, window_start: int, window_end: int) -> dict:
    prices = window_value.get("prices", [])
    volumes = window_value.get("volumes", [])

    avg_close = sum(prices) / len(prices) if prices else 0.0
    first_close = prices[0] if prices else 0.0
    last_close = prices[-1] if prices else 0.0
    total_volume = sum(volumes)

    return {
        "ticker": ticker,
        "window_start": window_start,
        "window_end": window_end,
        "avg_close": round(avg_close, 4),
        "first_close": round(first_close, 4),
        "last_close": round(last_close, 4),
        "price_change_rate": price_change_rate(first_close, last_close),
        "total_volume": total_volume,
        "tick_count": len(prices),
    }
