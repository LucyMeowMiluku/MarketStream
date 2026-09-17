"""Reproducible factor-sequence anomalies and explicit negative controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from processing.event_models import FACTOR_GROUPS, FactorSnapshot

PATTERNS = (
    "stock_specific_dislocation",
    "liquidity_pressure_move",
    "news_confirmed_move",
    "flash_reversal",
    "sustained_pressure",
    "cross_asset_shock",
)
NEGATIVE_CONTROLS = (
    "high_volume_no_price_move",
    "orderly_market_move",
    "stale_news",
    "after_hours_spread",
)
INTENSITY_Z = {"low": 4.5, "medium": 6.5, "high": 9.0}


@dataclass(slots=True)
class SyntheticScenario:
    name: str
    seed: int
    intensity: str
    snapshots: list[FactorSnapshot]
    expected_pattern: str | None
    expected_direction: str | None
    started_at: datetime
    ended_at: datetime


def _snapshot(
    ticker: str,
    event_time: datetime,
    anomalies: dict[str, tuple[float, str, str]],
    *,
    session: str = "regular",
) -> FactorSnapshot:
    values = {name: 0.0 for name in FACTOR_GROUPS}
    states = {
        name: {
            "group": group,
            "state": "normal",
            "direction": "up",
            "baseline": 0.0,
            "robust_z": 0.0,
            "threshold": 4.0,
            "extreme_threshold": 8.0,
            "history_days": 20,
        }
        for name, group in FACTOR_GROUPS.items()
    }
    for factor, (value, direction, state) in anomalies.items():
        values[factor] = value
        states[factor].update(
            state=state,
            direction=direction,
            robust_z=abs(value) if direction == "up" else -abs(value),
        )
    source_ids = [f"synthetic:{ticker}:{event_time.isoformat()}"]
    return FactorSnapshot(
        ticker=ticker,
        event_time=event_time,
        window_start=event_time - timedelta(seconds=10),
        cadence="10s",
        factor_values=values,
        factor_states=states,
        baseline_version="frozen-synthetic-v1",
        data_quality={"status": "good", "flags": [], "session": session, "mode": "replay"},
        warmup_status="ready",
        source_event_ids=source_ids,
    )


def generate_scenario(
    name: str,
    *,
    seed: int,
    intensity: str,
    start: datetime | None = None,
) -> SyntheticScenario:
    if name not in PATTERNS + NEGATIVE_CONTROLS:
        raise ValueError(f"unknown scenario: {name}")
    if intensity not in INTENSITY_Z:
        raise ValueError(f"intensity must be one of {tuple(INTENSITY_Z)}")
    rng = np.random.default_rng(seed)
    z_score = INTENSITY_Z[intensity] + float(rng.normal(0, 0.05))
    state = "extreme" if intensity == "high" else "elevated"
    base = start or datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=10)
    up = (z_score, "up", state)
    down = (-z_score, "down", state)
    snapshots: list[FactorSnapshot]
    expected: str | None = name if name in PATTERNS else None
    expected_direction: str | None = None

    if name == "stock_specific_dislocation":
        expected_direction = "up"
        snapshots = [_snapshot("AAPL", base, {"return_surprise": up, "market_residual": up})]
    elif name == "liquidity_pressure_move":
        expected_direction = "up"
        snapshots = [
            _snapshot("AAPL", base, {"spread_stress": up, "quote_imbalance": up}),
            _snapshot("AAPL", base + step, {"return_surprise": up}),
        ]
    elif name == "news_confirmed_move":
        expected_direction = "down"
        snapshots = [
            _snapshot("AAPL", base, {"news_shock": down}),
            _snapshot("AAPL", base + step, {"return_surprise": down}),
        ]
    elif name == "flash_reversal":
        expected_direction = "down"
        snapshots = [
            _snapshot("AAPL", base, {"return_surprise": up}),
            _snapshot("AAPL", base + step, {"return_surprise": down}),
        ]
    elif name == "sustained_pressure":
        expected_direction = "up"
        snapshots = [
            _snapshot("AAPL", base + step * index, {"signed_trade_imbalance": up})
            for index in range(3)
        ]
        snapshots.append(_snapshot("AAPL", base + step * 3, {"return_surprise": up}))
    elif name == "cross_asset_shock":
        expected_direction = "down"
        snapshots = [
            _snapshot(ticker, base, {"return_surprise": down})
            for ticker in ("SPY", "AAPL", "TSLA")
        ]
    elif name == "high_volume_no_price_move":
        snapshots = [_snapshot("AAPL", base, {"relative_volume": up})]
    elif name == "orderly_market_move":
        snapshots = [
            _snapshot(ticker, base, {"return_surprise": up}) for ticker in ("SPY", "AAPL")
        ]
    elif name == "stale_news":
        snapshots = [
            _snapshot("AAPL", base, {"news_shock": down}),
            _snapshot("AAPL", base + timedelta(minutes=6), {"return_surprise": down}),
        ]
    else:
        snapshots = [
            _snapshot("AAPL", base, {"spread_stress": up}, session="post_market")
        ]
    return SyntheticScenario(
        name=name,
        seed=seed,
        intensity=intensity,
        snapshots=snapshots,
        expected_pattern=expected,
        expected_direction=expected_direction,
        started_at=min(snapshot.event_time for snapshot in snapshots),
        ended_at=max(snapshot.event_time for snapshot in snapshots) + step,
    )
