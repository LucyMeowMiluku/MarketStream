"""Explicit baseline startup coordinator.

This is the only module that interprets COLD_START, VERIFIED_BACKFILL, and
RESTORE.  The Kafka runner receives a completed context and has no startup-mode
branches of its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from baseline.backfill import run_verified_backfill
from baseline.checkpoints import CheckpointManager
from baseline.repository import BaselineRepository, OffsetPosition, canonical_sha256
from config.settings import Settings, settings
from processing.event_models import FACTOR_GROUPS, as_utc
from processing.factor_engine import LightweightFactorEngine
from storage.models import BaselineEpoch


class BaselineStartupMode(StrEnum):
    COLD_START = "COLD_START"
    VERIFIED_BACKFILL = "VERIFIED_BACKFILL"
    RESTORE = "RESTORE"


@dataclass(frozen=True, slots=True)
class StartupConfiguration:
    mode: BaselineStartupMode
    expected_epoch_id: str | None
    baseline_algorithm_version: str
    engine_version: str
    cadences: tuple[int, ...]
    min_history_days: int
    baseline_days: int
    max_tickers: int
    checkpoint_dir: Path
    checkpoint_retention: int
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    activation_cutoff: datetime | None = None
    replaces_epoch_id: str | None = None
    recovery_reason: str | None = None

    @classmethod
    def from_settings(cls, value: Settings = settings) -> StartupConfiguration:
        raw_mode = value.factor_baseline_startup_mode
        if not raw_mode:
            raise ValueError("FACTOR_BASELINE_STARTUP_MODE must be explicitly configured")
        try:
            mode = BaselineStartupMode(raw_mode.upper())
        except ValueError as exc:
            raise ValueError(f"invalid FACTOR_BASELINE_STARTUP_MODE: {raw_mode}") from exc
        cutoff = (
            as_utc(value.factor_baseline_activation_cutoff)
            if value.factor_baseline_activation_cutoff
            else None
        )
        return cls(
            mode=mode,
            expected_epoch_id=value.factor_baseline_epoch_id,
            baseline_algorithm_version=value.factor_baseline_algorithm_version,
            engine_version=value.factor_engine_version,
            cadences=tuple(value.factor_cadences_seconds),
            min_history_days=value.factor_min_history_days,
            baseline_days=value.factor_baseline_days,
            max_tickers=value.factor_max_tickers,
            checkpoint_dir=value.factor_checkpoint_dir,
            checkpoint_retention=value.factor_checkpoint_retention,
            manifest_path=value.factor_baseline_manifest,
            manifest_sha256=value.factor_baseline_manifest_sha256,
            activation_cutoff=cutoff,
            replaces_epoch_id=value.factor_baseline_replaces_epoch_id,
            recovery_reason=value.factor_baseline_recovery_reason,
        )

    @property
    def factor_schema_hash(self) -> str:
        return canonical_sha256(sorted(FACTOR_GROUPS.items()))

    @property
    def config_hash(self) -> str:
        return canonical_sha256(
            {
                "cadences": self.cadences,
                "min_history_days": self.min_history_days,
                "baseline_days": self.baseline_days,
                "max_tickers": self.max_tickers,
                "timezone": "America/New_York",
            }
        )


@dataclass(frozen=True, slots=True)
class BaselineStartupContext:
    mode: BaselineStartupMode
    epoch_id: str
    activation_cutoff: datetime
    engine: LightweightFactorEngine
    offsets: tuple[OffsetPosition, ...]
    restored_from_checkpoint: bool = False
    verify_consumer_offsets: bool = False
    allow_consumer_offset_replay: bool = False


def _engine(config: StartupConfiguration, epoch_id: str) -> LightweightFactorEngine:
    return LightweightFactorEngine(
        cadences=config.cadences,
        min_history_days=config.min_history_days,
        baseline_days=config.baseline_days,
        max_tickers=config.max_tickers,
        epoch_id=epoch_id,
        track_state_updates=True,
    )


def _new_epoch(
    config: StartupConfiguration,
    *,
    status: str,
    origin: str,
    activation_cutoff: datetime,
) -> BaselineEpoch:
    now = datetime.now(timezone.utc)
    return BaselineEpoch(
        epoch_id=str(uuid.uuid4()),
        namespace="live",
        status=status,
        origin=origin,
        baseline_algorithm_version=config.baseline_algorithm_version,
        engine_version=config.engine_version,
        factor_schema_hash=config.factor_schema_hash,
        config_hash=config.config_hash,
        activation_cutoff=activation_cutoff,
        source_manifest_path=str(config.manifest_path) if config.manifest_path else None,
        source_manifest_sha256=config.manifest_sha256,
        replaces_epoch_id=config.replaces_epoch_id,
        recovery_reason=config.recovery_reason,
        activated_at=now if status == "ACTIVE" else None,
    )


def coordinate_startup(
    config: StartupConfiguration | None = None,
    *,
    repository: BaselineRepository | None = None,
    checkpoint_manager: CheckpointManager | None = None,
) -> BaselineStartupContext:
    config = config or StartupConfiguration.from_settings()
    repository = repository or BaselineRepository()
    checkpoint_manager = checkpoint_manager or CheckpointManager(
        config.checkpoint_dir, retention=config.checkpoint_retention
    )
    if not config.checkpoint_dir.is_absolute():
        raise ValueError("FACTOR_CHECKPOINT_DIR must be an absolute persistent path")
    if config.baseline_algorithm_version != "rolling-mad-v3":
        raise ValueError("this engine only supports rolling-mad-v3 durable baselines")
    if not config.engine_version.strip():
        raise ValueError("FACTOR_ENGINE_VERSION must be non-empty")
    if not config.cadences or any(cadence <= 0 for cadence in config.cadences):
        raise ValueError("factor cadences must be positive")
    if not 5 <= config.min_history_days <= config.baseline_days <= 20:
        raise ValueError(
            "baseline history must retain 5-20 days and include the warm-up minimum"
        )
    if config.max_tickers <= 0 or config.checkpoint_retention < 1:
        raise ValueError("ticker and checkpoint retention limits must be positive")
    if config.mode == BaselineStartupMode.COLD_START:
        return _cold_start(config, repository)
    if config.mode == BaselineStartupMode.VERIFIED_BACKFILL:
        return _verified_backfill(config, repository, checkpoint_manager)
    return _restore(config, repository, checkpoint_manager)


def _cold_start(
    config: StartupConfiguration, repository: BaselineRepository
) -> BaselineStartupContext:
    epochs = repository.list_epochs()
    origin = "INITIAL_DEPLOYMENT"
    if epochs:
        if not config.replaces_epoch_id or not config.recovery_reason:
            raise ValueError(
                "COLD_START is not a first deployment; replaces_epoch_id and "
                "recovery_reason are required"
            )
        replaced = next(
            (item for item in epochs if item.epoch_id == config.replaces_epoch_id), None
        )
        if replaced is None or replaced.status != "CORRUPT":
            raise ValueError("recovery COLD_START may replace only a CORRUPT epoch")
        if any(item.status in {"ACTIVE", "RECOVERING"} for item in epochs):
            raise ValueError("another live baseline epoch is still active")
        origin = "RECOVERY_COLD_START"
    elif repository.child_row_count() != 0:
        raise ValueError("orphan baseline state prevents COLD_START")
    cutoff = config.activation_cutoff or datetime.now(timezone.utc)
    epoch = _new_epoch(
        config, status="ACTIVE", origin=origin, activation_cutoff=cutoff
    )
    repository.create_epoch(epoch)
    return BaselineStartupContext(
        mode=config.mode,
        epoch_id=epoch.epoch_id,
        activation_cutoff=cutoff,
        engine=_engine(config, epoch.epoch_id),
        offsets=(),
    )


def _verified_backfill(
    config: StartupConfiguration,
    repository: BaselineRepository,
    checkpoint_manager: CheckpointManager,
) -> BaselineStartupContext:
    if not all(
        (config.manifest_path, config.manifest_sha256, config.activation_cutoff)
    ):
        raise ValueError(
            "VERIFIED_BACKFILL requires manifest, manifest checksum, and activation cutoff"
        )
    epochs = repository.list_epochs()
    if any(item.status in {"ACTIVE", "RECOVERING", "BUILDING"} for item in epochs):
        raise ValueError("another live baseline epoch is active or building")
    corrupt_epochs = [item for item in epochs if item.status == "CORRUPT"]
    if corrupt_epochs or config.replaces_epoch_id:
        if not config.replaces_epoch_id:
            raise ValueError("backfill replacement requires replaces_epoch_id")
        replaced = next(
            (item for item in epochs if item.epoch_id == config.replaces_epoch_id), None
        )
        if replaced is None or replaced.status != "CORRUPT":
            raise ValueError("VERIFIED_BACKFILL may replace only a CORRUPT epoch")
    epoch = _new_epoch(
        config,
        status="BUILDING",
        origin="VERIFIED_BACKFILL",
        activation_cutoff=config.activation_cutoff,
    )
    repository.create_epoch(epoch)
    engine = _engine(config, epoch.epoch_id)
    try:
        result = run_verified_backfill(
            epoch_id=epoch.epoch_id,
            engine=engine,
            repository=repository,
            checkpoint_manager=checkpoint_manager,
            manifest_path=config.manifest_path,
            manifest_sha256=config.manifest_sha256,
            engine_version=config.engine_version,
            activation_cutoff=config.activation_cutoff,
        )
        verification = repository.verify_epoch(epoch.epoch_id)
        if not verification.valid:
            raise ValueError(
                "verified backfill produced inconsistent state: "
                + "; ".join(verification.errors)
            )
        checkpoint_manifest = checkpoint_manager.validate_path(
            result.checkpoint_path,
            epoch_id=epoch.epoch_id,
            revision=repository.get_epoch(epoch.epoch_id).current_revision,
        )
        if (
            checkpoint_manifest.get("engine_version") != config.engine_version
            or checkpoint_manifest.get("factor_schema_hash")
            != config.factor_schema_hash
            or checkpoint_manifest.get("config_hash") != config.config_hash
        ):
            raise ValueError("verified backfill checkpoint configuration mismatch")
        repository.update_epoch_status(
            epoch.epoch_id, "ACTIVE", activated_at=datetime.now(timezone.utc)
        )
    except Exception:
        repository.update_epoch_status(epoch.epoch_id, "FAILED")
        raise
    return BaselineStartupContext(
        mode=config.mode,
        epoch_id=epoch.epoch_id,
        activation_cutoff=config.activation_cutoff,
        engine=engine,
        offsets=tuple(repository.load_offsets(epoch.epoch_id)),
    )


def _restore(
    config: StartupConfiguration,
    repository: BaselineRepository,
    checkpoint_manager: CheckpointManager,
) -> BaselineStartupContext:
    if not config.expected_epoch_id:
        raise ValueError("RESTORE requires FACTOR_BASELINE_EPOCH_ID")
    epoch = repository.get_epoch(config.expected_epoch_id)
    if epoch is None or epoch.status != "ACTIVE":
        raise ValueError("RESTORE requires the explicitly selected ACTIVE epoch")
    if epoch.baseline_algorithm_version != config.baseline_algorithm_version:
        raise ValueError("baseline algorithm version mismatch")
    if epoch.engine_version != config.engine_version:
        raise ValueError("factor engine version mismatch")
    if epoch.factor_schema_hash != config.factor_schema_hash:
        raise ValueError("factor schema mismatch")
    if epoch.config_hash != config.config_hash:
        raise ValueError("factor configuration mismatch")

    restored_from_checkpoint = False
    verification = repository.verify_epoch(epoch.epoch_id)
    if not verification.valid:
        repository.update_epoch_status(epoch.epoch_id, "RECOVERING")
        checkpoint = checkpoint_manager.find_latest_valid(epoch.epoch_id)
        if checkpoint is None:
            repository.update_epoch_status(epoch.epoch_id, "CORRUPT")
            raise ValueError(
                "baseline state is inconsistent and no valid checkpoint is available"
            )
        checkpoint_manager.restore(checkpoint)
        restored_from_checkpoint = True
        verification = repository.verify_epoch(epoch.epoch_id)
        if not verification.valid:
            repository.update_epoch_status(epoch.epoch_id, "CORRUPT")
            raise ValueError("restored checkpoint did not produce a consistent epoch")

    engine = _engine(config, epoch.epoch_id)
    engine.restore_observations(repository.load_observations(epoch.epoch_id))
    engine.restore_runtime_state(repository.load_runtime(epoch.epoch_id))
    return BaselineStartupContext(
        mode=config.mode,
        epoch_id=epoch.epoch_id,
        activation_cutoff=as_utc(epoch.activation_cutoff),
        engine=engine,
        offsets=tuple(repository.load_offsets(epoch.epoch_id)),
        restored_from_checkpoint=restored_from_checkpoint,
        verify_consumer_offsets=True,
        allow_consumer_offset_replay=restored_from_checkpoint,
    )
