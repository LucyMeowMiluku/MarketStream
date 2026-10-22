# 来源归属（2026-10-22）：XI LU 主导方案选择与具体约束，AI 按确认方案生成／重构实现。
# 本注释不声明全部代码由本人手写；逐项原日志与未确认范围见
# docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md 及 report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md。
"""Bounded orchestration for the eight explainable market factors."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Any

from baseline.contracts import BaselineObservation, RuntimeStateUpdate, StateUpdateBatch
from processing.event_models import FACTOR_GROUPS, FactorSnapshot, MarketEvent, as_utc
from processing.factor_calculations import calculate_factors, summarize_window
from processing.factor_state import (
    CADENCE_NAMES,
    NY,
    SIGNED_FACTORS,
    BaselineSeries,
    WindowAccumulator,
    floor_time,
    market_session,
)


class LightweightFactorEngine:
    """Convert events into 10-second, 1-minute and 5-minute factor snapshots."""

    def __init__(
        self,
        *,
        cadences: tuple[int, ...] = (10, 60, 300),
        min_history_days: int = 5,
        baseline_days: int = 20,
        max_tickers: int = 64,
        frozen_baselines: bool = False,
        epoch_id: str | None = None,
        track_state_updates: bool = False,
    ) -> None:
        self.cadences = tuple(sorted(cadences))
        self.min_history_days = min_history_days
        self.baseline_days = baseline_days
        self.max_tickers = max_tickers
        self._frozen_baselines = frozen_baselines
        self.epoch_id = epoch_id
        self._track_state_updates = track_state_updates
        self._pending_updates = StateUpdateBatch()
        self._baseline_version = "rolling-mad-v2"
        self._windows: OrderedDict[tuple[str, int], WindowAccumulator] = OrderedDict()
        self._baselines: dict[tuple[str, int, str, int, str], BaselineSeries] = {}
        self._previous_close: dict[tuple[str, int], float] = {}
        self._benchmark_returns: dict[tuple[int, str], tuple[datetime, float]] = {}
        self._trading_days: dict[str, deque[date]] = {}
        self._known_tickers: OrderedDict[str, None] = OrderedDict()

    def process(self, event: MarketEvent) -> list[FactorSnapshot]:
        """Add one event and emit each cadence window that it closes."""

        self._touch_ticker(event.ticker)
        snapshots: list[FactorSnapshot] = []
        for cadence in self.cadences:
            key = (event.ticker, cadence)
            current = self._windows.get(key)
            start = floor_time(event.event_time, cadence)
            if current is None:
                current = self._new_window(start, cadence)
                self._windows[key] = current
            elif event.event_time >= current.end:
                snapshots.append(self._finalize(event.ticker, cadence, current))
                current = self._new_window(start, cadence)
                self._windows[key] = current
            elif event.event_time < current.start:
                current.quality_flags.add("out_of_order")
                continue
            current.update(event)
            self._windows.move_to_end(key)
        return snapshots

    @staticmethod
    def _new_window(start: datetime, cadence: int) -> WindowAccumulator:
        return WindowAccumulator(start=start, end=start + timedelta(seconds=cadence))

    def flush(self, until: datetime | None = None) -> list[FactorSnapshot]:
        cutoff = until or datetime.max.replace(tzinfo=timezone.utc)
        snapshots = []
        for key, window in list(self._windows.items()):
            if window.end <= cutoff:
                snapshots.append(self._finalize(key[0], key[1], window))
                del self._windows[key]
        return sorted(snapshots, key=lambda item: (item.event_time, item.ticker, item.cadence))

    @property
    def state_size(self) -> dict[str, int]:
        return {
            "tickers": len(self._known_tickers),
            "windows": len(self._windows),
            "baselines": len(self._baselines),
        }

    @property
    def frozen_baselines(self) -> bool:
        return self._frozen_baselines

    def export_baseline_state(self) -> dict[str, Any]:
        """Return the train-period threshold state for a frozen test replay."""

        return {
            "format": "marketstream-baseline-v1",
            "epoch_id": self.epoch_id,
            "min_history_days": self.min_history_days,
            "baseline_days": self.baseline_days,
            "baselines": [
                {
                    "ticker": key[0],
                    "cadence": key[1],
                    "session": key[2],
                    "slot": key[3],
                    "name": key[4],
                    "values": [[day.isoformat(), value] for day, value in series.values],
                }
                for key, series in sorted(self._baselines.items())
            ],
            "trading_days": {
                ticker: [day.isoformat() for day in days]
                for ticker, days in sorted(self._trading_days.items())
            },
            "previous_close": [
                {"ticker": key[0], "cadence": key[1], "value": value}
                for key, value in sorted(self._previous_close.items())
            ],
            "benchmark_returns": [
                {
                    "cadence": key[0],
                    "ticker": key[1],
                    "event_time": value[0].isoformat(),
                    "return": value[1],
                }
                for key, value in sorted(self._benchmark_returns.items())
            ],
        }

    def import_baseline_state(self, state: dict[str, Any], *, freeze: bool = True) -> None:
        if state.get("format") != "marketstream-baseline-v1":
            raise ValueError("unsupported baseline state format")
        self._baselines.clear()
        self.epoch_id = state.get("epoch_id") or self.epoch_id
        for record in state.get("baselines", []):
            key = (
                str(record["ticker"]),
                int(record["cadence"]),
                str(record["session"]),
                int(record["slot"]),
                str(record["name"]),
            )
            series = BaselineSeries(self.baseline_days)
            for session_date, value in record.get("values", []):
                series.add(date.fromisoformat(session_date), float(value))
            self._baselines[key] = series
        self._trading_days = {
            ticker: deque(
                (date.fromisoformat(item) for item in values),
                maxlen=self.baseline_days + 1,
            )
            for ticker, values in state.get("trading_days", {}).items()
        }
        self._previous_close = {
            (record["ticker"], int(record["cadence"])): float(record["value"])
            for record in state.get("previous_close", [])
        }
        self._benchmark_returns = {
            (int(record["cadence"]), record["ticker"]): (
                datetime.fromisoformat(record["event_time"]),
                float(record["return"]),
            )
            for record in state.get("benchmark_returns", [])
        }
        self._known_tickers = OrderedDict((ticker, None) for ticker in self._trading_days)
        self._frozen_baselines = freeze
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        self._baseline_version = f"frozen-mad-v2:{digest}" if freeze else "rolling-mad-v2"

    def restore_observations(
        self, observations: list[BaselineObservation], *, clear: bool = True
    ) -> None:
        """Restore durable observations without coupling the engine to SQLAlchemy."""

        if clear:
            self._baselines.clear()
        for observation in observations:
            key = self._baseline_key(
                observation.ticker,
                observation.cadence,
                observation.market_session,
                observation.intraday_slot,
                observation.factor_name,
            )
            self._series(key).add(observation.session_date, observation.value)
            self._known_tickers[observation.ticker] = None

    def restore_runtime_state(self, states: list[RuntimeStateUpdate]) -> None:
        for state in states:
            self._previous_close[(state.ticker, state.cadence)] = state.previous_close
            if state.ticker in {"SPY", "QQQ"}:
                self._benchmark_returns[(state.cadence, state.ticker)] = (
                    as_utc(state.last_window_end),
                    state.latest_raw_return,
                )
            self._known_tickers[state.ticker] = None

    def drain_state_updates(self) -> StateUpdateBatch:
        updates = self._pending_updates
        self._pending_updates = StateUpdateBatch()
        return updates

    def _touch_ticker(self, ticker: str) -> None:
        if ticker in self._known_tickers:
            self._known_tickers.move_to_end(ticker)
            return
        self._known_tickers[ticker] = None
        if len(self._known_tickers) <= self.max_tickers:
            return
        evicted, _ = self._known_tickers.popitem(last=False)
        self._windows = OrderedDict(
            (key, value) for key, value in self._windows.items() if key[0] != evicted
        )
        self._baselines = {
            key: value for key, value in self._baselines.items() if key[0] != evicted
        }
        self._previous_close = {
            key: value for key, value in self._previous_close.items() if key[0] != evicted
        }
        self._trading_days.pop(evicted, None)

    @staticmethod
    def _baseline_key(ticker, cadence, session, slot, name):
        return ticker, cadence, session, slot, name

    def _series(self, key) -> BaselineSeries:
        if key not in self._baselines:
            if self._frozen_baselines:
                return BaselineSeries(self.baseline_days)
            self._baselines[key] = BaselineSeries(self.baseline_days)
        return self._baselines[key]

    def _add_baseline_value(self, key, session_date: date, value: float) -> None:
        series = self._series(key)
        before = list(series.values)
        series.add(session_date, value)
        if (
            self._track_state_updates
            and not self._frozen_baselines
            and list(series.values) != before
        ):
            self._pending_updates.observations.append(
                BaselineObservation(
                    ticker=key[0],
                    cadence=key[1],
                    market_session=key[2],
                    intraday_slot=key[3],
                    factor_name=key[4],
                    session_date=session_date,
                    value=value,
                )
            )

    def _finalize(self, ticker: str, cadence: int, window: WindowAccumulator) -> FactorSnapshot:
        session = market_session(window.end - timedelta(microseconds=1))
        local_end = window.end.astimezone(NY)
        slot = (local_end.hour * 3600 + local_end.minute * 60 + local_end.second) // cadence
        session_date = local_end.date()
        days = self._trading_days.setdefault(ticker, deque(maxlen=self.baseline_days + 1))
        if not self._frozen_baselines and session_date not in days and session != "closed":
            days.append(session_date)

        previous_close = self._previous_close.get((ticker, cadence), 0.0)
        metrics = summarize_window(window, previous_close)
        if metrics.close:
            self._previous_close[(ticker, cadence)] = metrics.close
        durable_previous_close = self._previous_close.get((ticker, cadence), 0.0)

        volume_key = self._baseline_key(ticker, cadence, session, slot, "_volume")
        range_key = self._baseline_key(ticker, cadence, session, slot, "_range")
        spread_key = self._baseline_key(ticker, cadence, session, slot, "_spread")
        return_key = self._baseline_key(ticker, cadence, session, slot, "_return")
        volume_series = self._series(volume_key)
        range_series = self._series(range_key)
        spread_series = self._series(spread_key)
        return_series = self._series(return_key)
        return_median, return_mad, _, _ = return_series.summary(before=session_date)
        benchmark_return = self._latest_benchmark_return(ticker, cadence, window.end)
        if ticker in {"SPY", "QQQ"}:
            self._benchmark_returns[(cadence, ticker)] = (window.end, metrics.raw_return)

        factor_values = calculate_factors(
            window,
            metrics,
            return_median=return_median,
            return_mad=return_mad,
            volume_median=volume_series.summary(before=session_date)[0],
            range_median=range_series.summary(before=session_date)[0],
            spread_median=spread_series.summary(before=session_date)[0],
            benchmark_return=benchmark_return,
        )
        factor_states = self._classify_factors(
            ticker, cadence, session, slot, session_date, factor_values
        )
        ready = all(item["state"] != "warmup" for item in factor_states.values())
        if not self._frozen_baselines:
            self._add_baseline_value(volume_key, session_date, metrics.volume)
            self._add_baseline_value(range_key, session_date, metrics.price_range)
            if metrics.spread_bps:
                self._add_baseline_value(spread_key, session_date, metrics.spread_bps)
            self._add_baseline_value(return_key, session_date, metrics.raw_return)
            if self._track_state_updates:
                self._pending_updates.runtime.append(
                    RuntimeStateUpdate(
                        ticker=ticker,
                        cadence=cadence,
                        # Quote/news-only windows do not have a close. Persist
                        # the retained runtime value so a restart is identical
                        # to uninterrupted execution.
                        previous_close=durable_previous_close,
                        latest_raw_return=metrics.raw_return,
                        last_window_end=window.end,
                    )
                )

        history_days = min(
            (item["history_days"] for item in factor_states.values()), default=0
        )
        epoch_fragment = f":{self.epoch_id}" if self.epoch_id else ""

        return FactorSnapshot(
            ticker=ticker,
            event_time=window.end,
            window_start=window.start,
            cadence=CADENCE_NAMES.get(cadence, f"{cadence}s"),
            factor_values=factor_values,
            factor_states=factor_states,
            baseline_version=(
                f"{self._baseline_version}{epoch_fragment}:{session}:{history_days}d"
            ),
            data_quality=self._quality_summary(window, session),
            warmup_status="ready" if ready else "warming_up",
            source_event_ids=list(window.event_ids),
            input_summary={
                "event_type_counts": dict(sorted(window.event_type_counts.items())),
                "first_price": window.first_price,
                "last_price": window.last_price,
                "bid_price": window.bid_price,
                "ask_price": window.ask_price,
                "bid_size": window.bid_size,
                "ask_size": window.ask_size,
                "trade_volume": window.trade_volume,
                "bar_volume": window.bar_volume,
                "news_count": len(window.news_scores),
                "news_headlines": list(window.news_headlines),
                "traced_source_event_ids": len(window.event_ids),
            },
            run_id=window.run_id,
            dataset_id=window.dataset_id,
            mode=window.mode,
            provenance=window.provenance,
        )

    def _classify_factors(self, ticker, cadence, session, slot, session_date, values):
        states = {}
        for name, value in values.items():
            series = self._series(self._baseline_key(ticker, cadence, session, slot, name))
            median, mad, quantile_995, quantile_999 = series.summary(before=session_date)
            scale = max(1.4826 * mad, 1e-6)
            prior_samples = series.samples_before(session_date)
            robust_z = (value - median) / scale if prior_samples else 0.0
            if name in SIGNED_FACTORS:
                threshold = max(abs(quantile_995 - median), 4 * scale)
                extreme_threshold = max(abs(quantile_999 - median), 6 * scale)
                distance = abs(value - median)
                direction = "up" if value >= median else "down"
            else:
                threshold = max(quantile_995, median + 4 * scale)
                extreme_threshold = max(quantile_999, median + 6 * scale)
                distance = value
                direction = "up"
            state = "warmup"
            history_days = series.distinct_days_before(session_date)
            if history_days >= self.min_history_days:
                state = "extreme" if distance >= extreme_threshold else "elevated" if distance >= threshold else "normal"
            states[name] = {
                "group": FACTOR_GROUPS[name],
                "state": state,
                "direction": direction,
                "baseline": round(median, 8),
                "robust_z": round(robust_z, 4),
                "threshold": round(threshold, 8),
                "extreme_threshold": round(extreme_threshold, 8),
                "history_days": history_days,
            }
            if not self._frozen_baselines:
                self._add_baseline_value(
                    self._baseline_key(ticker, cadence, session, slot, name),
                    session_date,
                    value,
                )
        return states

    @staticmethod
    def _quality_summary(window, session):
        severe = {"duplicate", "out_of_order", "stale", "invalid_price", "crossed_quote"}
        flags = sorted(window.quality_flags)
        return {
            "status": "degraded" if severe.intersection(flags) else "good",
            "flags": flags,
            "session": session,
            "feed_event_count": window.event_count,
            "first_received_at": window.first_received_at.isoformat() if window.first_received_at else None,
            "last_received_at": window.last_received_at.isoformat() if window.last_received_at else None,
        }

    def _latest_benchmark_return(self, ticker: str, cadence: int, event_time: datetime) -> float:
        candidates = (
            ("QQQ", "SPY")
            if ticker not in {"QQQ", "SPY"}
            else tuple(item for item in ("SPY", "QQQ") if item != ticker)
        )
        for benchmark in candidates:
            latest = self._benchmark_returns.get((cadence, benchmark))
            if latest and event_time - latest[0] <= timedelta(seconds=cadence * 2):
                return latest[1]
        return 0.0


__all__ = ["LightweightFactorEngine", "market_session"]
