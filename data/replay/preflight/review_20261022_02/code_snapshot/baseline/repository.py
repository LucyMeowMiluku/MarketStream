"""Transactional repository for live baseline epochs and their state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from baseline.contracts import BaselineObservation, RuntimeStateUpdate, StateUpdateBatch
from processing.event_models import FactorSnapshot, MarketEvent, as_utc
from storage.db import get_session
from storage.models import (
    BaselineCheckpoint,
    BaselineEpoch,
    FactorBaselineSample,
    FactorEngineOffset,
    FactorRuntimeState,
    FactorSnapshotRecord,
    MarketEventRecord,
    SentimentScore,
)


EPOCH_STATUSES = {
    "BUILDING",
    "ACTIVE",
    "RECOVERING",
    "RETIRED",
    "FAILED",
    "CORRUPT",
}
EPOCH_TRANSITIONS = {
    "BUILDING": {"ACTIVE", "FAILED"},
    "ACTIVE": {"RECOVERING", "RETIRED"},
    "RECOVERING": {"ACTIVE", "CORRUPT"},
    "RETIRED": set(),
    "FAILED": set(),
    "CORRUPT": set(),
}


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def observation_checksum(value: BaselineObservation) -> str:
    return canonical_sha256(
        {
            "ticker": value.ticker,
            "cadence": value.cadence,
            "market_session": value.market_session,
            "intraday_slot": value.intraday_slot,
            "factor_name": value.factor_name,
            "session_date": value.session_date.isoformat(),
            "value": value.value,
        }
    )


def runtime_checksum(value: RuntimeStateUpdate) -> str:
    window_end = value.last_window_end
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    window_end = window_end.astimezone(timezone.utc)
    return canonical_sha256(
        {
            "ticker": value.ticker,
            "cadence": value.cadence,
            "previous_close": value.previous_close,
            "latest_raw_return": value.latest_raw_return,
            "last_window_end": window_end.isoformat(),
        }
    )


@dataclass(frozen=True, slots=True)
class OffsetPosition:
    consumer_group: str
    topic: str
    partition: int
    next_offset: int


@dataclass(slots=True)
class PersistenceUnit:
    event: MarketEvent | None
    snapshots: list[FactorSnapshot]
    updates: StateUpdateBatch
    offsets: list[OffsetPosition]


@dataclass(frozen=True, slots=True)
class StateVerification:
    valid: bool
    errors: tuple[str, ...]
    baseline_rows: int
    runtime_rows: int
    partition_rows: int


class BaselineRepository:
    def __init__(self, session_factory: Callable[[], Session] = get_session) -> None:
        self._session_factory = session_factory

    def list_epochs(self, namespace: str = "live") -> list[BaselineEpoch]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(BaselineEpoch)
                    .where(BaselineEpoch.namespace == namespace)
                    .order_by(BaselineEpoch.created_at)
                )
            )

    def get_epoch(self, epoch_id: str) -> BaselineEpoch | None:
        with self._session_factory() as session:
            return session.get(BaselineEpoch, epoch_id)

    def child_row_count(self) -> int:
        with self._session_factory() as session:
            return sum(
                int(session.scalar(select(func.count()).select_from(model)) or 0)
                for model in (
                    FactorBaselineSample,
                    FactorRuntimeState,
                    FactorEngineOffset,
                    BaselineCheckpoint,
                )
            )

    def create_epoch(self, epoch: BaselineEpoch) -> BaselineEpoch:
        if epoch.status not in EPOCH_STATUSES:
            raise ValueError(f"invalid baseline epoch status: {epoch.status}")
        with self._session_factory() as session, session.begin():
            session.add(epoch)
            session.flush()
            session.expunge(epoch)
        return epoch

    def update_epoch_status(
        self,
        epoch_id: str,
        status: str,
        *,
        activated_at: datetime | None = None,
        retired_at: datetime | None = None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            epoch = session.get(BaselineEpoch, epoch_id, with_for_update=True)
            if epoch is None:
                raise ValueError(f"unknown baseline epoch: {epoch_id}")
            if status not in EPOCH_STATUSES:
                raise ValueError(f"invalid baseline epoch status: {status}")
            if status != epoch.status and status not in EPOCH_TRANSITIONS[epoch.status]:
                raise ValueError(
                    f"invalid baseline epoch transition: {epoch.status} -> {status}"
                )
            epoch.status = status
            if activated_at is not None:
                epoch.activated_at = activated_at
            if retired_at is not None:
                epoch.retired_at = retired_at

    def load_observations(self, epoch_id: str) -> list[BaselineObservation]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(FactorBaselineSample)
                .where(FactorBaselineSample.epoch_id == epoch_id)
                .order_by(
                    FactorBaselineSample.ticker,
                    FactorBaselineSample.cadence,
                    FactorBaselineSample.market_session,
                    FactorBaselineSample.intraday_slot,
                    FactorBaselineSample.factor_name,
                    FactorBaselineSample.session_date,
                )
            )
            return [self._observation_from_row(row) for row in rows]

    def load_runtime(self, epoch_id: str) -> list[RuntimeStateUpdate]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(FactorRuntimeState).where(FactorRuntimeState.epoch_id == epoch_id)
            )
            return [self._runtime_from_row(row) for row in rows]

    def load_offsets(self, epoch_id: str) -> list[OffsetPosition]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(FactorEngineOffset).where(FactorEngineOffset.epoch_id == epoch_id)
            )
            return [
                OffsetPosition(
                    consumer_group=row.consumer_group,
                    topic=row.topic,
                    partition=row.partition,
                    next_offset=row.next_offset,
                )
                for row in rows
            ]

    def verify_epoch(self, epoch_id: str) -> StateVerification:
        errors: list[str] = []
        with self._session_factory() as session:
            epoch = session.get(BaselineEpoch, epoch_id)
            if epoch is None:
                return StateVerification(False, ("epoch does not exist",), 0, 0, 0)
            baseline_rows = list(
                session.scalars(
                    select(FactorBaselineSample).where(
                        FactorBaselineSample.epoch_id == epoch_id
                    )
                )
            )
            runtime_rows = list(
                session.scalars(
                    select(FactorRuntimeState).where(FactorRuntimeState.epoch_id == epoch_id)
                )
            )
            partition_rows = int(
                session.scalar(
                    select(func.count())
                    .select_from(FactorEngineOffset)
                    .where(FactorEngineOffset.epoch_id == epoch_id)
                )
                or 0
            )
            offset_rows = list(
                session.scalars(
                    select(FactorEngineOffset).where(
                        FactorEngineOffset.epoch_id == epoch_id
                    )
                )
            )
            if len(baseline_rows) != epoch.expected_baseline_rows:
                errors.append("baseline row count differs from registry")
            if len(runtime_rows) != epoch.expected_runtime_rows:
                errors.append("runtime row count differs from registry")
            if partition_rows != epoch.expected_partition_rows:
                errors.append("offset partition count differs from registry")
            if epoch.current_revision < 0:
                errors.append("registry revision is negative")
            total_child_rows = len(baseline_rows) + len(runtime_rows) + partition_rows
            if epoch.current_revision == 0 and total_child_rows:
                errors.append("state rows exist at registry revision zero")
            if epoch.current_revision > 0 and not total_child_rows:
                errors.append("registry revision is nonzero but all state rows are absent")
            persisted_boundary = (
                as_utc(epoch.last_persisted_at) if epoch.last_persisted_at else None
            )
            if epoch.current_revision > 0 and persisted_boundary is None:
                errors.append("nonzero registry revision has no persistence boundary")
            for row in baseline_rows:
                value = self._observation_from_row(row)
                if row.row_checksum != observation_checksum(value):
                    errors.append(f"baseline checksum mismatch: {value.cell_key}")
                    break
                if not 1 <= row.state_revision <= epoch.current_revision:
                    errors.append("baseline revision is outside the registry boundary")
                    break
                if persisted_boundary and (
                    as_utc(row.updated_at) > persisted_boundary
                    or row.session_date > persisted_boundary.date()
                ):
                    errors.append("baseline timestamp is ahead of registry boundary")
                    break
            for row in runtime_rows:
                value = self._runtime_from_row(row)
                if row.row_checksum != runtime_checksum(value):
                    errors.append(f"runtime checksum mismatch: {value.ticker}/{value.cadence}")
                    break
                if not 1 <= row.state_revision <= epoch.current_revision:
                    errors.append("runtime revision is outside the registry boundary")
                    break
                if persisted_boundary and (
                    as_utc(row.updated_at) > persisted_boundary
                    or as_utc(row.last_window_end) > persisted_boundary
                ):
                    errors.append("runtime timestamp is ahead of registry boundary")
                    break
            if any(
                not 1 <= row.state_revision <= epoch.current_revision
                for row in offset_rows
            ):
                errors.append("offset revision is outside the registry boundary")
            if any(row.next_offset < 0 for row in offset_rows):
                errors.append("offset contains a negative next_offset")
            if persisted_boundary and any(
                as_utc(row.updated_at) > persisted_boundary for row in offset_rows
            ):
                errors.append("offset timestamp is ahead of registry boundary")
            if offset_rows:
                offset_revision = max(row.state_revision for row in offset_rows)
                state_revisions = [
                    *(row.state_revision for row in baseline_rows),
                    *(row.state_revision for row in runtime_rows),
                ]
                if offset_revision != epoch.current_revision:
                    errors.append("latest DB offset does not match registry revision")
                if state_revisions and max(state_revisions) > offset_revision:
                    errors.append("DB offsets are behind persisted factor state")
            return StateVerification(
                not errors,
                tuple(errors),
                len(baseline_rows),
                len(runtime_rows),
                partition_rows,
            )

    def persist_units(self, epoch_id: str, units: Iterable[PersistenceUnit]) -> int:
        units = list(units)
        if not units:
            epoch = self.get_epoch(epoch_id)
            return epoch.current_revision if epoch else 0
        with self._session_factory() as session, session.begin():
            epoch = session.get(BaselineEpoch, epoch_id, with_for_update=True)
            if epoch is None or epoch.status not in {"ACTIVE", "BUILDING"}:
                raise ValueError(f"baseline epoch is not writable: {epoch_id}")
            revision = epoch.current_revision + 1
            observations: dict[tuple, BaselineObservation] = {}
            runtime: dict[tuple, RuntimeStateUpdate] = {}
            offsets: dict[tuple, OffsetPosition] = {}
            for unit in units:
                if unit.event is not None:
                    self._merge_event(session, unit.event)
                for snapshot in unit.snapshots:
                    self._merge_snapshot(session, snapshot)
                for item in unit.updates.observations:
                    observations[(*item.cell_key, item.session_date)] = item
                for item in unit.updates.runtime:
                    runtime[(item.ticker, item.cadence)] = item
                for item in unit.offsets:
                    offsets[(item.consumer_group, item.topic, item.partition)] = item

            for item in observations.values():
                self._upsert_baseline(
                    session,
                    epoch_id,
                    item,
                    revision,
                )
            session.flush()
            self._prune_cells(session, epoch_id, observations.values())

            for item in runtime.values():
                self._upsert_runtime(session, epoch_id, item, revision)
            for item in offsets.values():
                existing = session.get(
                    FactorEngineOffset,
                    (epoch_id, item.consumer_group, item.topic, item.partition),
                )
                if existing is None:
                    session.add(
                        FactorEngineOffset(
                            epoch_id=epoch_id,
                            consumer_group=item.consumer_group,
                            topic=item.topic,
                            partition=item.partition,
                            next_offset=item.next_offset,
                            state_revision=revision,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                else:
                    existing.next_offset = max(existing.next_offset, item.next_offset)
                    existing.state_revision = revision
                    existing.updated_at = datetime.now(timezone.utc)
            session.flush()
            epoch.current_revision = revision
            epoch.expected_baseline_rows = self._count(
                session, FactorBaselineSample, epoch_id
            )
            epoch.expected_runtime_rows = self._count(session, FactorRuntimeState, epoch_id)
            epoch.expected_partition_rows = self._count(session, FactorEngineOffset, epoch_id)
            epoch.last_persisted_at = datetime.now(timezone.utc)
            return revision

    @staticmethod
    def _upsert_baseline(
        session: Session,
        epoch_id: str,
        item: BaselineObservation,
        revision: int,
    ) -> None:
        values = {
            "epoch_id": epoch_id,
            "ticker": item.ticker,
            "cadence": item.cadence,
            "market_session": item.market_session,
            "intraday_slot": item.intraday_slot,
            "factor_name": item.factor_name,
            "session_date": item.session_date,
            "value": item.value,
            "state_revision": revision,
            "row_checksum": observation_checksum(item),
            "updated_at": datetime.now(timezone.utc),
        }
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert

            statement = insert(FactorBaselineSample).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        "epoch_id",
                        "ticker",
                        "cadence",
                        "market_session",
                        "intraday_slot",
                        "factor_name",
                        "session_date",
                    ],
                    set_={
                        "value": statement.excluded.value,
                        "state_revision": statement.excluded.state_revision,
                        "row_checksum": statement.excluded.row_checksum,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
            )
            return
        session.merge(FactorBaselineSample(**values))

    @staticmethod
    def _upsert_runtime(
        session: Session,
        epoch_id: str,
        item: RuntimeStateUpdate,
        revision: int,
    ) -> None:
        values = {
            "epoch_id": epoch_id,
            "ticker": item.ticker,
            "cadence": item.cadence,
            "previous_close": item.previous_close,
            "latest_raw_return": item.latest_raw_return,
            "last_window_end": item.last_window_end,
            "state_revision": revision,
            "row_checksum": runtime_checksum(item),
            "updated_at": datetime.now(timezone.utc),
        }
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert

            statement = insert(FactorRuntimeState).values(**values)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["epoch_id", "ticker", "cadence"],
                    set_={
                        "previous_close": statement.excluded.previous_close,
                        "latest_raw_return": statement.excluded.latest_raw_return,
                        "last_window_end": statement.excluded.last_window_end,
                        "state_revision": statement.excluded.state_revision,
                        "row_checksum": statement.excluded.row_checksum,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
            )
            return
        session.merge(FactorRuntimeState(**values))

    @staticmethod
    def _count(session: Session, model, epoch_id: str) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.epoch_id == epoch_id)
            )
            or 0
        )

    @staticmethod
    def _observation_from_row(row: FactorBaselineSample) -> BaselineObservation:
        return BaselineObservation(
            ticker=row.ticker,
            cadence=row.cadence,
            market_session=row.market_session,
            intraday_slot=row.intraday_slot,
            factor_name=row.factor_name,
            session_date=row.session_date,
            value=row.value,
        )

    @staticmethod
    def _runtime_from_row(row: FactorRuntimeState) -> RuntimeStateUpdate:
        return RuntimeStateUpdate(
            ticker=row.ticker,
            cadence=row.cadence,
            previous_close=row.previous_close,
            latest_raw_return=row.latest_raw_return,
            last_window_end=row.last_window_end,
        )

    @staticmethod
    def _prune_cells(
        session: Session,
        epoch_id: str,
        observations: Iterable[BaselineObservation],
    ) -> None:
        for cell in {item.cell_key for item in observations}:
            dates = list(
                session.scalars(
                    select(FactorBaselineSample.session_date)
                    .where(
                        FactorBaselineSample.epoch_id == epoch_id,
                        FactorBaselineSample.ticker == cell[0],
                        FactorBaselineSample.cadence == cell[1],
                        FactorBaselineSample.market_session == cell[2],
                        FactorBaselineSample.intraday_slot == cell[3],
                        FactorBaselineSample.factor_name == cell[4],
                    )
                    .order_by(FactorBaselineSample.session_date.desc())
                    .offset(20)
                )
            )
            if dates:
                session.execute(
                    delete(FactorBaselineSample).where(
                        FactorBaselineSample.epoch_id == epoch_id,
                        FactorBaselineSample.ticker == cell[0],
                        FactorBaselineSample.cadence == cell[1],
                        FactorBaselineSample.market_session == cell[2],
                        FactorBaselineSample.intraday_slot == cell[3],
                        FactorBaselineSample.factor_name == cell[4],
                        FactorBaselineSample.session_date.in_(dates),
                    )
                )

    @staticmethod
    def _merge_event(session: Session, event: MarketEvent) -> None:
        is_new = session.get(MarketEventRecord, event.event_id) is None
        session.merge(
            MarketEventRecord(
                event_id=event.event_id,
                source=event.source,
                feed=event.feed,
                event_type=event.event_type.value,
                ticker=event.ticker,
                event_time=event.event_time,
                received_at=event.received_at,
                payload=event.payload,
                quality_flags=list(event.quality_flags),
            )
        )
        if (
            is_new
            and event.event_type.value == "news"
            and "duplicate" not in event.quality_flags
        ):
            score = float(event.payload.get("sentiment_score", 0.0))
            session.add(
                SentimentScore(
                    time=event.event_time,
                    ticker=event.ticker,
                    headline=str(event.payload.get("headline", "")),
                    source=str(event.payload.get("source", event.feed)),
                    sentiment_score=score,
                    sentiment_label=(
                        "positive" if score > 0 else "negative" if score < 0 else "neutral"
                    ),
                )
            )

    @staticmethod
    def _merge_snapshot(session: Session, snapshot: FactorSnapshot) -> None:
        session.merge(
            FactorSnapshotRecord(
                event_time=snapshot.event_time,
                window_start=snapshot.window_start,
                ticker=snapshot.ticker,
                cadence=snapshot.cadence,
                factor_values=snapshot.factor_values,
                factor_states=snapshot.factor_states,
                baseline_version=snapshot.baseline_version,
                data_quality=snapshot.data_quality,
                warmup_status=snapshot.warmup_status,
                source_event_ids=snapshot.source_event_ids,
                input_summary=snapshot.input_summary,
            )
        )
