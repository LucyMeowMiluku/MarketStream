# 来源归属（2026-10-22）：XI LU 主导方案选择与具体约束，AI 按确认方案生成／重构实现。
# 本注释不声明全部代码由本人手写；逐项原日志与未确认范围见
# docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_CN.md 及 report/ownership_evidence/08_Contribution_Attribution_Matrix_CN.md。
"""Six small, explicit state machines used by the factor CEP detector.

Each machine owns only the bounded history needed by one market pattern.  The
public detector remains responsible for alert suppression, severity and
cooldown; these classes only answer whether a pattern is complete or pending.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from typing import Protocol

from processing.event_models import AtomicEvent, FactorSnapshot, PatternMatch


def _pattern(
    name: str,
    direction: str,
    started_at,
    completed_at,
    evidence: list[str],
    *,
    status: str = "completed",
) -> PatternMatch:
    return PatternMatch(
        name=name,
        direction=direction,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        evidence=evidence,
    )


def _cadence_seconds(cadence: str) -> int:
    return {"10s": 10, "1m": 60, "5m": 300}.get(cadence, 60)


def _by_factor(atoms: list[AtomicEvent]) -> dict[str, AtomicEvent]:
    return {atom.factor: atom for atom in atoms}


class PatternMachine(Protocol):
    name: str

    def advance(
        self, snapshot: FactorSnapshot, atoms: list[AtomicEvent]
    ) -> tuple[list[PatternMatch], list[PatternMatch]]: ...

    def expire(self, snapshot: FactorSnapshot) -> None: ...

    def reset(self, ticker: str | None = None) -> None: ...

    @property
    def state_keys(self) -> int: ...


class StockSpecificDislocationMachine:
    """IDLE -> COMPLETED when price and residual agree in the same frame."""

    name = "stock_specific_dislocation"

    def advance(self, snapshot, atoms):
        current = _by_factor(atoms)
        price = current.get("return_surprise")
        residual = current.get("market_residual")
        if price and residual and price.direction == residual.direction:
            return [
                _pattern(
                    self.name,
                    price.direction,
                    min(price.event_time, residual.event_time),
                    snapshot.event_time,
                    [price.factor, residual.factor],
                )
            ], []
        return [], []

    def expire(self, snapshot):
        del snapshot

    def reset(self, ticker=None):
        del ticker

    @property
    def state_keys(self):
        return 0


class LiquidityPressureMoveMachine:
    """IDLE -> PRESSURE_PENDING -> COMPLETED after aligned price confirmation."""

    name = "liquidity_pressure_move"

    def __init__(self, max_frames: int):
        self._history = defaultdict(lambda: deque(maxlen=max_frames))

    def expire(self, snapshot):
        key = (snapshot.ticker, snapshot.cadence)
        seconds = _cadence_seconds(snapshot.cadence)
        cutoff = snapshot.event_time - timedelta(seconds=max(60, seconds * 2))
        self._history[key] = deque(
            (atom for atom in self._history[key] if atom.event_time >= cutoff),
            maxlen=self._history[key].maxlen,
        )

    def advance(self, snapshot, atoms):
        self.expire(snapshot)
        key = (snapshot.ticker, snapshot.cadence)
        current = _by_factor(atoms)
        price = current.get("return_surprise")
        liquidity = list(self._history[key]) + [
            atom
            for atom in atoms
            if atom.factor in {"spread_stress", "quote_imbalance", "signed_trade_imbalance"}
        ]
        pressure = [atom for atom in liquidity if atom.factor != "spread_stress"]
        spread = next((atom for atom in reversed(liquidity) if atom.factor == "spread_stress"), None)
        aligned = next(
            (atom for atom in reversed(pressure) if price and atom.direction == price.direction),
            None,
        )
        self._history[key].extend(
            atom
            for atom in atoms
            if atom.factor in {"spread_stress", "quote_imbalance", "signed_trade_imbalance"}
        )
        if price and spread and aligned:
            return [
                _pattern(
                    self.name,
                    price.direction,
                    min(price.event_time, spread.event_time, aligned.event_time),
                    snapshot.event_time,
                    [spread.factor, aligned.factor, price.factor],
                )
            ], []
        if liquidity:
            return [], [
                _pattern(
                    self.name,
                    pressure[-1].direction if pressure else "up",
                    min(atom.event_time for atom in liquidity),
                    None,
                    [atom.factor for atom in liquidity],
                    status="in_progress",
                )
            ]
        return [], []

    def reset(self, ticker=None):
        if ticker is None:
            self._history.clear()
            return
        for key in [key for key in self._history if key[0] == ticker]:
            del self._history[key]

    @property
    def state_keys(self):
        return len(self._history)


class NewsConfirmedMoveMachine:
    """IDLE -> NEWS_PENDING -> COMPLETED within five minutes."""

    name = "news_confirmed_move"

    def __init__(self, max_frames: int):
        self._news = defaultdict(lambda: deque(maxlen=max_frames))

    def expire(self, snapshot):
        key = (snapshot.ticker, snapshot.cadence)
        cutoff = snapshot.event_time - timedelta(minutes=5)
        self._news[key] = deque(
            (atom for atom in self._news[key] if atom.event_time >= cutoff),
            maxlen=self._news[key].maxlen,
        )

    def advance(self, snapshot, atoms):
        self.expire(snapshot)
        key = (snapshot.ticker, snapshot.cadence)
        current = _by_factor(atoms)
        price = current.get("return_surprise")
        current_news = [atom for atom in atoms if atom.factor == "news_shock"]
        candidates = list(self._news[key]) + current_news
        news = candidates[-1] if candidates else None
        self._news[key].extend(current_news)
        if news and price and news.direction == price.direction:
            return [
                _pattern(
                    self.name,
                    price.direction,
                    news.event_time,
                    snapshot.event_time,
                    [news.factor, price.factor],
                )
            ], []
        if news:
            return [], [
                _pattern(
                    self.name,
                    news.direction,
                    news.event_time,
                    None,
                    [news.factor],
                    status="in_progress",
                )
            ]
        return [], []

    def reset(self, ticker=None):
        if ticker is None:
            self._news.clear()
            return
        for key in [key for key in self._news if key[0] == ticker]:
            del self._news[key]

    @property
    def state_keys(self):
        return len(self._news)


class FlashReversalMachine:
    """IDLE -> MOVE_PENDING -> COMPLETED after an opposite price move."""

    name = "flash_reversal"

    def __init__(self):
        self._previous: dict[tuple[str, str], AtomicEvent] = {}

    def expire(self, snapshot):
        key = (snapshot.ticker, snapshot.cadence)
        previous = self._previous.get(key)
        if previous and snapshot.event_time - previous.event_time > timedelta(
            seconds=_cadence_seconds(snapshot.cadence) * 2
        ):
            del self._previous[key]

    def advance(self, snapshot, atoms):
        self.expire(snapshot)
        key = (snapshot.ticker, snapshot.cadence)
        price = _by_factor(atoms).get("return_surprise")
        previous = self._previous.get(key)
        if price is None:
            return [], []
        self._previous[key] = price
        if previous and price.direction != previous.direction:
            return [
                _pattern(
                    self.name,
                    price.direction,
                    previous.event_time,
                    snapshot.event_time,
                    [previous.name, price.name],
                )
            ], []
        return [], [
            _pattern(
                self.name,
                price.direction,
                price.event_time,
                None,
                [price.factor],
                status="in_progress",
            )
        ]

    def reset(self, ticker=None):
        if ticker is None:
            self._previous.clear()
            return
        for key in [key for key in self._previous if key[0] == ticker]:
            del self._previous[key]

    @property
    def state_keys(self):
        return len(self._previous)


class SustainedPressureMachine:
    """IDLE -> PRESSURE_1 -> PRESSURE_2 -> COMPLETED with price confirmation."""

    name = "sustained_pressure"

    def __init__(self):
        self._frames = defaultdict(lambda: deque(maxlen=4))

    def expire(self, snapshot):
        key = (snapshot.ticker, snapshot.cadence)
        seconds = _cadence_seconds(snapshot.cadence)
        cutoff = snapshot.event_time - timedelta(seconds=max(300, seconds * 5))
        self._frames[key] = deque(
            (item for item in self._frames[key] if item[0] >= cutoff), maxlen=4
        )

    def advance(self, snapshot, atoms):
        self.expire(snapshot)
        key = (snapshot.ticker, snapshot.cadence)
        frames = list(self._frames[key]) + [(snapshot.event_time, atoms)]
        self._frames[key].append((snapshot.event_time, atoms))
        price = _by_factor(atoms).get("return_surprise")
        completed: list[PatternMatch] = []
        pending: list[PatternMatch] = []
        for direction in ("up", "down"):
            directional = [
                atom
                for _, frame_atoms in frames[-4:]
                for atom in frame_atoms
                if atom.factor in {"quote_imbalance", "signed_trade_imbalance"}
                and atom.direction == direction
            ]
            distinct_windows = len({atom.event_time for atom in directional})
            if distinct_windows >= 3 and price and price.direction == direction:
                completed.append(
                    _pattern(
                        self.name,
                        direction,
                        min(atom.event_time for atom in directional),
                        snapshot.event_time,
                        sorted({atom.factor for atom in directional} | {price.factor}),
                    )
                )
            elif distinct_windows >= 2:
                pending.append(
                    _pattern(
                        self.name,
                        direction,
                        min(atom.event_time for atom in directional),
                        None,
                        sorted({atom.factor for atom in directional}),
                        status="in_progress",
                    )
                )
        return completed, pending

    def reset(self, ticker=None):
        if ticker is None:
            self._frames.clear()
            return
        for key in [key for key in self._frames if key[0] == ticker]:
            del self._frames[key]

    @property
    def state_keys(self):
        return len(self._frames)


class CrossAssetShockMachine:
    """IDLE -> ACCUMULATING -> COMPLETED for three tickers including an ETF."""

    name = "cross_asset_shock"

    def __init__(self, max_frames: int = 256):
        # One cross-ticker buffer per cadence: 10s, 1m and 5m windows must not
        # confirm each other.
        self._prices = defaultdict(lambda: deque(maxlen=max_frames))

    def expire(self, snapshot):
        prices = self._prices[snapshot.cadence]
        cutoff = snapshot.event_time - timedelta(seconds=60)
        while prices and prices[0][0] < cutoff:
            prices.popleft()

    def advance(self, snapshot, atoms):
        self.expire(snapshot)
        price = _by_factor(atoms).get("return_surprise")
        if price is None:
            # Only the ticker that has just moved can complete the shock.
            return [], []
        prices = self._prices[snapshot.cadence]
        prices.append((snapshot.event_time, snapshot.ticker, price))
        completed: list[PatternMatch] = []
        for direction in ("up", "down"):
            relevant = [item for item in prices if item[2].direction == direction]
            tickers = {ticker for _, ticker, _ in relevant}
            if (
                price.direction == direction
                and len(tickers) >= 3
                and tickers.intersection({"SPY", "QQQ"})
            ):
                completed.append(
                    _pattern(
                        self.name,
                        direction,
                        min(event_time for event_time, _, _ in relevant),
                        snapshot.event_time,
                        [f"return_surprise:{ticker}" for ticker in sorted(tickers)],
                    )
                )
        return completed, []

    def reset(self, ticker=None):
        if ticker is None:
            self._prices.clear()
            return
        for cadence, prices in self._prices.items():
            self._prices[cadence] = deque(
                (item for item in prices if item[1] != ticker), maxlen=prices.maxlen
            )

    @property
    def state_keys(self):
        return len(
            {ticker for prices in self._prices.values() for _, ticker, _ in prices}
        )


def build_state_machines(max_frames: int) -> list[PatternMachine]:
    """Return the six machines in deterministic evaluation order."""

    return [
        StockSpecificDislocationMachine(),
        LiquidityPressureMoveMachine(max_frames),
        NewsConfirmedMoveMachine(max_frames),
        FlashReversalMachine(),
        SustainedPressureMachine(),
        CrossAssetShockMachine(),
    ]
