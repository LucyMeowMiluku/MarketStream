"""Strict, manifest-backed construction of a live baseline epoch."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from baseline.checkpoints import CheckpointManager, file_sha256
from baseline.repository import BaselineRepository, PersistenceUnit
from processing.data_quality import EventQualityGate
from processing.event_models import MarketEvent, as_utc
from processing.factor_engine import LightweightFactorEngine


@dataclass(frozen=True, slots=True)
class BackfillResult:
    events: int
    snapshots: int
    first_event_time: datetime
    last_event_time: datetime
    checkpoint_path: Path


def _artifact_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else manifest_path.parent / path


def validate_manifest(
    manifest_path: Path,
    *,
    expected_sha256: str,
    engine_version: str,
    activation_cutoff: datetime,
) -> dict:
    if file_sha256(manifest_path) != expected_sha256:
        raise ValueError("backfill manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "marketstream-baseline-backfill-v1":
        raise ValueError("unsupported baseline backfill manifest")
    if manifest.get("provider") != "alpaca" or manifest.get("source") != "alpaca":
        raise ValueError("verified backfill requires Alpaca source data")
    if not isinstance(manifest.get("collection_version"), str):
        raise ValueError("backfill collection_version is required")
    provenance = manifest.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("phase") != "baseline_backfill"
    ):
        raise ValueError("backfill manifest provenance is invalid")
    if manifest.get("engine_version") != engine_version:
        raise ValueError("backfill engine version differs from deployment")
    if as_utc(manifest.get("activation_cutoff")) != activation_cutoff:
        raise ValueError("backfill activation cutoff differs from deployment")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("backfill manifest has no source artifacts")
    for artifact in artifacts:
        path = _artifact_path(manifest_path, str(artifact.get("path", "")))
        if not path.is_file() or file_sha256(path) != artifact.get("sha256"):
            raise ValueError(f"backfill artifact checksum mismatch: {path}")
        if not isinstance(artifact.get("events"), int) or artifact["events"] <= 0:
            raise ValueError(f"backfill artifact has invalid event count: {path}")
        if not artifact.get("feeds") or not artifact.get("event_types"):
            raise ValueError(
                f"backfill artifact feed/type contract is missing: {path}"
            )
    if int(manifest.get("event_count", -1)) != sum(
        artifact["events"] for artifact in artifacts
    ):
        raise ValueError("backfill manifest event count does not match artifacts")
    time_range = manifest.get("time_range") or {}
    if not time_range.get("start") or not time_range.get("end"):
        raise ValueError("backfill manifest time range is required")
    if as_utc(time_range["end"]) >= activation_cutoff:
        raise ValueError("backfill manifest reaches activation cutoff")
    return manifest


def run_verified_backfill(
    *,
    epoch_id: str,
    engine: LightweightFactorEngine,
    repository: BaselineRepository,
    checkpoint_manager: CheckpointManager,
    manifest_path: Path,
    manifest_sha256: str,
    engine_version: str,
    activation_cutoff: datetime,
    persist_every_events: int = 1_000,
) -> BackfillResult:
    manifest = validate_manifest(
        manifest_path,
        expected_sha256=manifest_sha256,
        engine_version=engine_version,
        activation_cutoff=activation_cutoff,
    )
    quality = EventQualityGate()
    event_count = 0
    snapshot_count = 0
    first: datetime | None = None
    last: datetime | None = None
    pending_snapshots = []
    previous_key: tuple[datetime, str] | None = None

    def persist_pending() -> None:
        nonlocal pending_snapshots
        updates = engine.drain_state_updates()
        if updates.empty and not pending_snapshots:
            return
        repository.persist_units(
            epoch_id,
            [PersistenceUnit(None, pending_snapshots, updates, [])],
        )
        pending_snapshots = []

    for artifact in manifest["artifacts"]:
        path = _artifact_path(manifest_path, artifact["path"])
        actual_events = 0
        with path.open() as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    event = MarketEvent.from_dict(json.loads(line))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid backfill event at {path}:{line_number}") from exc
                key = (event.event_time, event.event_id)
                if previous_key is not None and key < previous_key:
                    raise ValueError("backfill events are not globally chronological")
                previous_key = key
                if event.source != "alpaca" or event.mode != "verified_backfill":
                    raise ValueError("backfill event source/mode is not trusted")
                if not event.feed:
                    raise ValueError("backfill event feed is missing")
                if event.feed not in artifact["feeds"]:
                    raise ValueError("backfill event feed is outside its manifest")
                if event.event_type.value not in artifact["event_types"]:
                    raise ValueError("backfill event type is outside its manifest")
                if event.provenance.get("phase") != "baseline_backfill":
                    raise ValueError("backfill event provenance phase is invalid")
                lowered = event.event_id.lower()
                if any(token in lowered for token in ("synthetic", "soak", "replay")):
                    raise ValueError("backfill contains excluded event identity")
                if event.event_time >= activation_cutoff:
                    raise ValueError("backfill event is not strictly before activation cutoff")
                assessed = quality.assess(event, mode="replay", now=event.event_time)
                snapshots = engine.process(assessed)
                pending_snapshots.extend(snapshots)
                snapshot_count += len(snapshots)
                event_count += 1
                actual_events += 1
                first = event.event_time if first is None else min(first, event.event_time)
                last = event.event_time if last is None else max(last, event.event_time)
                if event_count % persist_every_events == 0:
                    persist_pending()
        if actual_events != artifact["events"]:
            raise ValueError(f"backfill event count mismatch: {path}")
    flushed = engine.flush()
    pending_snapshots.extend(flushed)
    snapshot_count += len(flushed)
    persist_pending()
    if first is None or last is None:
        raise ValueError("verified backfill contains no events")
    time_range = manifest["time_range"]
    if first != as_utc(time_range["start"]) or last != as_utc(time_range["end"]):
        raise ValueError("backfill observed time range differs from manifest")
    checkpoint_path = checkpoint_manager.create(epoch_id)
    return BackfillResult(event_count, snapshot_count, first, last, checkpoint_path)
