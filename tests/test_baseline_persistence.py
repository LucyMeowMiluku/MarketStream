from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from baseline.checkpoints import CheckpointManager, file_sha256
from baseline.contracts import BaselineObservation, RuntimeStateUpdate, StateUpdateBatch
from baseline.repository import BaselineRepository, OffsetPosition, PersistenceUnit
from baseline.startup import (
    BaselineStartupMode,
    StartupConfiguration,
    coordinate_startup,
)
from baseline.writer import BaselineWriter
from processing.event_models import MarketEvent
from storage.models import Base, BaselineCheckpoint, FactorBaselineSample


def _storage(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return (
        BaselineRepository(factory),
        CheckpointManager(tmp_path / "checkpoints", session_factory=factory),
        factory,
    )


def _config(tmp_path, mode, **overrides):
    values = {
        "mode": mode,
        "expected_epoch_id": None,
        "baseline_algorithm_version": "rolling-mad-v2",
        "engine_version": "test-engine",
        "cadences": (300,),
        "min_history_days": 5,
        "baseline_days": 20,
        "max_tickers": 8,
        "checkpoint_dir": tmp_path / "checkpoints",
        "checkpoint_retention": 7,
        "activation_cutoff": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return StartupConfiguration(**values)


def _observation(day: int, value: float | None = None):
    return BaselineObservation(
        ticker="AAPL",
        cadence=300,
        market_session="regular",
        intraday_slot=120,
        factor_name="relative_volume",
        session_date=date(2025, 1, 1) + timedelta(days=day),
        value=float(day if value is None else value),
    )


def test_cold_start_is_explicit_and_cannot_mask_existing_epoch(tmp_path):
    repository, manager, _ = _storage(tmp_path)
    context = coordinate_startup(
        _config(tmp_path, BaselineStartupMode.COLD_START),
        repository=repository,
        checkpoint_manager=manager,
    )
    assert context.mode == BaselineStartupMode.COLD_START
    assert repository.get_epoch(context.epoch_id).origin == "INITIAL_DEPLOYMENT"
    with pytest.raises(ValueError, match="not a first deployment"):
        coordinate_startup(
            _config(tmp_path, BaselineStartupMode.COLD_START),
            repository=repository,
            checkpoint_manager=manager,
        )


def test_repository_upserts_same_day_and_prunes_each_cell_to_twenty(tmp_path):
    repository, manager, _ = _storage(tmp_path)
    context = coordinate_startup(
        _config(tmp_path, BaselineStartupMode.COLD_START),
        repository=repository,
        checkpoint_manager=manager,
    )
    for day in range(21):
        repository.persist_units(
            context.epoch_id,
            [
                PersistenceUnit(
                    None,
                    [],
                    StateUpdateBatch(observations=[_observation(day)]),
                    [OffsetPosition("group", "raw", 0, day + 1)],
                )
            ],
        )
    repository.persist_units(
        context.epoch_id,
        [
            PersistenceUnit(
                None,
                [],
                StateUpdateBatch(observations=[_observation(20, 999.0)]),
                [OffsetPosition("group", "raw", 0, 21)],
            )
        ],
    )
    observations = repository.load_observations(context.epoch_id)
    assert len(observations) == 20
    assert observations[0].session_date == date(2025, 1, 2)
    assert observations[-1].value == 999.0
    assert repository.verify_epoch(context.epoch_id).valid


def test_restore_loads_runtime_and_recovers_corrupt_current_state(tmp_path):
    repository, manager, factory = _storage(tmp_path)
    cold = coordinate_startup(
        _config(tmp_path, BaselineStartupMode.COLD_START),
        repository=repository,
        checkpoint_manager=manager,
    )
    runtime = RuntimeStateUpdate(
        ticker="AAPL",
        cadence=300,
        previous_close=123.0,
        latest_raw_return=0.01,
        last_window_end=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    repository.persist_units(
        cold.epoch_id,
        [
            PersistenceUnit(
                None,
                [],
                StateUpdateBatch([_observation(0)], [runtime]),
                [OffsetPosition("group", "raw", 0, 10)],
            )
        ],
    )
    manager.create(cold.epoch_id)
    with factory() as session, session.begin():
        session.execute(
            delete(FactorBaselineSample).where(
                FactorBaselineSample.epoch_id == cold.epoch_id
            )
        )
    assert not repository.verify_epoch(cold.epoch_id).valid
    restored = coordinate_startup(
        _config(
            tmp_path,
            BaselineStartupMode.RESTORE,
            expected_epoch_id=cold.epoch_id,
        ),
        repository=repository,
        checkpoint_manager=manager,
    )
    assert restored.restored_from_checkpoint
    assert repository.verify_epoch(cold.epoch_id).valid
    assert restored.engine.export_baseline_state()["previous_close"][0]["value"] == 123.0


def test_restore_skips_invalid_latest_checkpoint(tmp_path):
    repository, manager, factory = _storage(tmp_path)
    cold = coordinate_startup(
        _config(tmp_path, BaselineStartupMode.COLD_START),
        repository=repository,
        checkpoint_manager=manager,
    )
    repository.persist_units(
        cold.epoch_id,
        [
            PersistenceUnit(
                None,
                [],
                StateUpdateBatch(observations=[_observation(0)]),
                [OffsetPosition("group", "raw", 0, 10)],
            )
        ],
    )
    first = manager.create(cold.epoch_id)
    repository.persist_units(
        cold.epoch_id,
        [
            PersistenceUnit(
                None,
                [],
                StateUpdateBatch(observations=[_observation(1)]),
                [OffsetPosition("group", "raw", 0, 20)],
            )
        ],
    )
    latest = manager.create(cold.epoch_id)
    (latest / "runtime.json").write_text("corrupt\n")
    with factory() as session, session.begin():
        session.execute(
            delete(FactorBaselineSample).where(
                FactorBaselineSample.epoch_id == cold.epoch_id
            )
        )
    restored = coordinate_startup(
        _config(
            tmp_path,
            BaselineStartupMode.RESTORE,
            expected_epoch_id=cold.epoch_id,
        ),
        repository=repository,
        checkpoint_manager=manager,
    )
    assert restored.restored_from_checkpoint
    assert manager.find_latest_valid(cold.epoch_id) == first
    assert repository.load_offsets(cold.epoch_id)[0].next_offset == 10
    with factory() as session:
        invalid = session.get(BaselineCheckpoint, (cold.epoch_id, 2))
        assert invalid.status == "INVALID"


def test_recovery_cold_start_requires_corrupt_replacement(tmp_path):
    repository, manager, _ = _storage(tmp_path)
    cold = coordinate_startup(
        _config(tmp_path, BaselineStartupMode.COLD_START),
        repository=repository,
        checkpoint_manager=manager,
    )
    repository.update_epoch_status(cold.epoch_id, "RECOVERING")
    repository.update_epoch_status(cold.epoch_id, "CORRUPT")
    with pytest.raises(ValueError, match="invalid baseline epoch transition"):
        repository.update_epoch_status(cold.epoch_id, "ACTIVE")
    recovered = coordinate_startup(
        _config(
            tmp_path,
            BaselineStartupMode.COLD_START,
            replaces_epoch_id=cold.epoch_id,
            recovery_reason="verified state and checkpoints were lost",
        ),
        repository=repository,
        checkpoint_manager=manager,
    )
    epoch = repository.get_epoch(recovered.epoch_id)
    assert epoch.origin == "RECOVERY_COLD_START"
    assert epoch.replaces_epoch_id == cold.epoch_id


def test_writer_retries_and_acknowledges_only_after_success():
    class FlakyRepository:
        calls = 0

        def persist_units(self, _epoch_id, _units):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database unavailable")
            return 7

    repository = FlakyRepository()
    writer = BaselineWriter(
        repository, "epoch", max_queue=2, batch_size=1, flush_seconds=0.01
    )
    writer.start()
    position = OffsetPosition("group", "raw", 0, 1)
    assert writer.submit_nowait(
        PersistenceUnit(None, [], StateUpdateBatch(), [position])
    )
    degraded_deadline = time.monotonic() + 0.5
    while time.monotonic() < degraded_deadline and not writer.degraded:
        time.sleep(0.01)
    assert writer.degraded
    assert writer.depth == 1
    assert writer.submit_nowait(
        PersistenceUnit(
            None,
            [],
            StateUpdateBatch(),
            [OffsetPosition("group", "raw", 0, 2)],
        )
    )
    assert writer.depth == 2
    assert not writer.submit_nowait(
        PersistenceUnit(
            None,
            [],
            StateUpdateBatch(),
            [OffsetPosition("group", "raw", 0, 3)],
        )
    )
    deadline = time.monotonic() + 2.5
    acks = []
    while time.monotonic() < deadline and not acks:
        acks = writer.poll_acks()
        time.sleep(0.02)
    assert repository.calls >= 2
    assert acks[0].offsets == (position,)
    assert writer.stop(1)


def test_verified_backfill_requires_manifested_trusted_raw_events(tmp_path):
    repository, manager, _ = _storage(tmp_path)
    cutoff = datetime(2025, 1, 10, tzinfo=timezone.utc)
    events = [
        MarketEvent.create(
            event_id=f"alpaca-{index}",
            source="alpaca",
            feed="iex",
            event_type="trade",
            ticker="AAPL",
            event_time=datetime(2025, 1, 2 + index, 15, tzinfo=timezone.utc),
            received_at=datetime(2025, 1, 2 + index, 15, tzinfo=timezone.utc),
            trade={"price": 100 + index, "size": 10, "side": "buy"},
            mode="verified_backfill",
            provenance={"phase": "baseline_backfill", "request_id": "trusted"},
        )
        for index in range(2)
    ]
    artifact = tmp_path / "events.jsonl"
    artifact.write_text("".join(json.dumps(event.to_dict()) + "\n" for event in events))
    manifest = {
        "schema_version": "marketstream-baseline-backfill-v1",
        "provider": "alpaca",
        "source": "alpaca",
        "collection_version": "test-collector-v1",
        "provenance": {"phase": "baseline_backfill"},
        "engine_version": "test-engine",
        "activation_cutoff": cutoff.isoformat(),
        "event_count": 2,
        "time_range": {
            "start": events[0].event_time.isoformat(),
            "end": events[-1].event_time.isoformat(),
        },
        "artifacts": [
            {
                "path": artifact.name,
                "sha256": file_sha256(artifact),
                "events": 2,
                "feeds": ["iex"],
                "event_types": ["trade"],
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    context = coordinate_startup(
        _config(
            tmp_path,
            BaselineStartupMode.VERIFIED_BACKFILL,
            manifest_path=manifest_path,
            manifest_sha256=file_sha256(manifest_path),
            activation_cutoff=cutoff,
        ),
        repository=repository,
        checkpoint_manager=manager,
    )
    epoch = repository.get_epoch(context.epoch_id)
    assert epoch.status == "ACTIVE"
    assert epoch.origin == "VERIFIED_BACKFILL"
    assert manager.find_latest_valid(context.epoch_id) is not None
