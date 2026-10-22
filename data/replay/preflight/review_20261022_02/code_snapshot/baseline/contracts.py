"""Storage-neutral contracts emitted and restored by the factor engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BaselineObservation:
    ticker: str
    cadence: int
    market_session: str
    intraday_slot: int
    factor_name: str
    session_date: date
    value: float

    @property
    def cell_key(self) -> tuple[str, int, str, int, str]:
        return (
            self.ticker,
            self.cadence,
            self.market_session,
            self.intraday_slot,
            self.factor_name,
        )


@dataclass(frozen=True, slots=True)
class RuntimeStateUpdate:
    ticker: str
    cadence: int
    previous_close: float
    latest_raw_return: float
    last_window_end: datetime


@dataclass(slots=True)
class StateUpdateBatch:
    observations: list[BaselineObservation] = field(default_factory=list)
    runtime: list[RuntimeStateUpdate] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.observations and not self.runtime

