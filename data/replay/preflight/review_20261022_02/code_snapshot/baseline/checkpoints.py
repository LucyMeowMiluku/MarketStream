"""Immutable baseline checkpoint artifacts and verified recovery."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select

from baseline.contracts import BaselineObservation, RuntimeStateUpdate
from baseline.repository import (
    canonical_sha256,
    observation_checksum,
    runtime_checksum,
)
from storage.db import get_session
from storage.models import (
    BaselineCheckpoint,
    BaselineEpoch,
    FactorBaselineSample,
    FactorEngineOffset,
    FactorRuntimeState,
)


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class CheckpointManager:
    def __init__(
        self,
        root: Path,
        *,
        retention: int = 7,
        session_factory=get_session,
    ) -> None:
        self.root = Path(root)
        self.retention = retention
        self._session_factory = session_factory

    def create(self, epoch_id: str) -> Path:
        with self._session_factory() as session:
            # PostgreSQL's default READ COMMITTED isolation can observe a
            # different revision between the three exports. Use one repeatable
            # snapshot; SQLite test stores already provide snapshot semantics.
            if session.get_bind().dialect.name == "postgresql":
                session.connection(
                    execution_options={"isolation_level": "REPEATABLE READ"}
                )
            epoch = session.get(BaselineEpoch, epoch_id)
            if epoch is None or epoch.status not in {"ACTIVE", "BUILDING"}:
                raise ValueError("checkpoint requires an ACTIVE or BUILDING epoch")
            revision = epoch.current_revision
            existing = session.get(BaselineCheckpoint, (epoch_id, revision))
            if existing is not None and existing.status == "COMMITTED":
                existing_path = Path(existing.artifact_path)
                self.validate_path(
                    existing_path, epoch_id=epoch_id, revision=revision
                )
                return existing_path
            baseline = list(
                session.scalars(
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
            )
            runtime = list(
                session.scalars(
                    select(FactorRuntimeState).where(FactorRuntimeState.epoch_id == epoch_id)
                )
            )
            offsets = list(
                session.scalars(
                    select(FactorEngineOffset).where(FactorEngineOffset.epoch_id == epoch_id)
                )
            )

        target = self.root / epoch_id / str(revision)
        temporary = target.parent / f".{revision}-{uuid.uuid4().hex}.tmp"
        temporary.mkdir(parents=True, exist_ok=False)
        with self._session_factory() as session, session.begin():
            session.merge(
                BaselineCheckpoint(
                    epoch_id=epoch_id,
                    revision=revision,
                    status="WRITING",
                    artifact_path=str(target),
                    baseline_rows=len(baseline),
                    runtime_rows=len(runtime),
                    offsets_summary=self._offset_json(offsets),
                )
            )
        try:
            baseline_path = temporary / "baseline.parquet"
            runtime_path = temporary / "runtime.json"
            offsets_path = temporary / "offsets.json"
            manifest_path = temporary / "manifest.json"
            baseline_records = [
                self._baseline_json(row, epoch_id, revision) for row in baseline
            ]
            baseline_columns = [
                "epoch_id",
                "checkpoint_revision",
                "ticker",
                "cadence",
                "market_session",
                "intraday_slot",
                "factor_name",
                "session_date",
                "value",
                "state_revision",
                "row_checksum",
                "updated_at",
            ]
            pd.DataFrame(baseline_records, columns=baseline_columns).to_parquet(
                baseline_path, index=False
            )
            runtime_rows = [self._runtime_json(row) for row in runtime]
            offset_rows = self._offset_json(offsets)
            runtime_payload = {
                "epoch_id": epoch_id,
                "revision": revision,
                "rows": runtime_rows,
            }
            offset_payload = {
                "epoch_id": epoch_id,
                "revision": revision,
                "rows": offset_rows,
            }
            runtime_path.write_text(json.dumps(runtime_payload, indent=2) + "\n")
            offsets_path.write_text(json.dumps(offset_payload, indent=2) + "\n")
            artifacts = {
                "baseline.parquet": file_sha256(baseline_path),
                "runtime.json": file_sha256(runtime_path),
                "offsets.json": file_sha256(offsets_path),
            }
            state_sha256 = canonical_sha256(artifacts)
            manifest = {
                "schema_version": "marketstream-baseline-checkpoint-v1",
                "epoch_id": epoch_id,
                "revision": revision,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "baseline_algorithm_version": epoch.baseline_algorithm_version,
                "engine_version": epoch.engine_version,
                "factor_schema_hash": epoch.factor_schema_hash,
                "config_hash": epoch.config_hash,
                "activation_cutoff": epoch.activation_cutoff.isoformat(),
                "baseline_rows": len(baseline),
                "runtime_rows": len(runtime),
                "offsets": offset_rows,
                "time_bounds": self._time_bounds(baseline_records, runtime_rows),
                "artifacts": artifacts,
                "state_sha256": state_sha256,
            }
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            manifest_sha256 = file_sha256(manifest_path)
            if target.exists():
                shutil.rmtree(target)
            temporary.rename(target)
            self.validate_path(target, epoch_id=epoch_id, revision=revision)
            with self._session_factory() as session, session.begin():
                row = session.get(BaselineCheckpoint, (epoch_id, revision))
                if row is None:
                    raise RuntimeError("checkpoint registry row disappeared")
                row.status = "COMMITTED"
                row.manifest_sha256 = manifest_sha256
                row.state_sha256 = state_sha256
                row.committed_at = datetime.now(timezone.utc)
            self._prune(epoch_id)
            return target
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            with self._session_factory() as session, session.begin():
                row = session.get(BaselineCheckpoint, (epoch_id, revision))
                if row is not None:
                    row.status = "INVALID"
            raise

    def find_latest_valid(self, epoch_id: str) -> Path | None:
        with self._session_factory() as session:
            checkpoints = list(
                session.scalars(
                    select(BaselineCheckpoint)
                    .where(
                        BaselineCheckpoint.epoch_id == epoch_id,
                        BaselineCheckpoint.status == "COMMITTED",
                    )
                    .order_by(BaselineCheckpoint.revision.desc())
                )
            )
        for checkpoint in checkpoints:
            path = Path(checkpoint.artifact_path)
            try:
                self.validate_path(
                    path, epoch_id=epoch_id, revision=checkpoint.revision
                )
                if checkpoint.manifest_sha256 != file_sha256(path / "manifest.json"):
                    raise ValueError("registered manifest checksum mismatch")
                return path
            except (OSError, ValueError, json.JSONDecodeError):
                with self._session_factory() as session, session.begin():
                    row = session.get(
                        BaselineCheckpoint, (epoch_id, checkpoint.revision)
                    )
                    if row is not None:
                        row.status = "INVALID"
        return None

    def validate_path(
        self, path: Path, *, epoch_id: str | None = None, revision: int | None = None
    ) -> dict:
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schema_version") != "marketstream-baseline-checkpoint-v1":
            raise ValueError("unsupported checkpoint manifest")
        if epoch_id is not None and manifest.get("epoch_id") != epoch_id:
            raise ValueError("checkpoint epoch mismatch")
        if revision is not None and int(manifest.get("revision", -1)) != revision:
            raise ValueError("checkpoint revision mismatch")
        for name, expected in manifest.get("artifacts", {}).items():
            artifact = path / name
            if not artifact.is_file() or file_sha256(artifact) != expected:
                raise ValueError(f"checkpoint artifact checksum mismatch: {name}")
        if canonical_sha256(manifest["artifacts"]) != manifest.get("state_sha256"):
            raise ValueError("checkpoint state checksum mismatch")
        self._validate_contents(path, manifest)
        return manifest

    def restore(self, path: Path) -> tuple[str, int]:
        manifest = self.validate_path(path)
        epoch_id = str(manifest["epoch_id"])
        revision = int(manifest["revision"])
        baseline = pd.read_parquet(path / "baseline.parquet").to_dict("records")
        runtime = json.loads((path / "runtime.json").read_text())["rows"]
        offsets = json.loads((path / "offsets.json").read_text())["rows"]
        if len(baseline) != int(manifest["baseline_rows"]):
            raise ValueError("checkpoint baseline row count mismatch")
        if len(runtime) != int(manifest["runtime_rows"]):
            raise ValueError("checkpoint runtime row count mismatch")
        with self._session_factory() as session, session.begin():
            epoch = session.get(BaselineEpoch, epoch_id, with_for_update=True)
            if epoch is None:
                raise ValueError("checkpoint epoch is not registered")
            for model in (FactorBaselineSample, FactorRuntimeState, FactorEngineOffset):
                session.execute(delete(model).where(model.epoch_id == epoch_id))
            for item in baseline:
                session.add(
                    FactorBaselineSample(
                        epoch_id=epoch_id,
                        ticker=item["ticker"],
                        cadence=int(item["cadence"]),
                        market_session=item["market_session"],
                        intraday_slot=int(item["intraday_slot"]),
                        factor_name=item["factor_name"],
                        session_date=date.fromisoformat(str(item["session_date"])),
                        value=float(item["value"]),
                        state_revision=int(item["state_revision"]),
                        row_checksum=item["row_checksum"],
                        updated_at=datetime.fromisoformat(str(item["updated_at"])),
                    )
                )
            for item in runtime:
                session.add(
                    FactorRuntimeState(
                        epoch_id=epoch_id,
                        ticker=item["ticker"],
                        cadence=int(item["cadence"]),
                        previous_close=float(item["previous_close"]),
                        latest_raw_return=float(item["latest_raw_return"]),
                        last_window_end=datetime.fromisoformat(item["last_window_end"]),
                        state_revision=int(item["state_revision"]),
                        row_checksum=item["row_checksum"],
                        updated_at=datetime.fromisoformat(item["updated_at"]),
                    )
                )
            for item in offsets:
                session.add(
                    FactorEngineOffset(
                        epoch_id=epoch_id,
                        consumer_group=item["consumer_group"],
                        topic=item["topic"],
                        partition=int(item["partition"]),
                        next_offset=int(item["next_offset"]),
                        state_revision=int(item["state_revision"]),
                        updated_at=datetime.fromisoformat(item["updated_at"]),
                    )
                )
            epoch.current_revision = revision
            epoch.expected_baseline_rows = len(baseline)
            epoch.expected_runtime_rows = len(runtime)
            epoch.expected_partition_rows = len(offsets)
            epoch.status = "ACTIVE"
            epoch.last_persisted_at = datetime.now(timezone.utc)
        return epoch_id, revision

    def _prune(self, epoch_id: str) -> None:
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(BaselineCheckpoint)
                    .where(
                        BaselineCheckpoint.epoch_id == epoch_id,
                        BaselineCheckpoint.status == "COMMITTED",
                    )
                    .order_by(BaselineCheckpoint.revision.desc())
                )
            )
        for row in rows[self.retention :]:
            shutil.rmtree(row.artifact_path, ignore_errors=True)
            with self._session_factory() as session, session.begin():
                stored = session.get(BaselineCheckpoint, (epoch_id, row.revision))
                if stored is not None:
                    session.delete(stored)

    @staticmethod
    def _baseline_json(
        row: FactorBaselineSample, epoch_id: str, revision: int
    ) -> dict:
        return {
            "epoch_id": epoch_id,
            "checkpoint_revision": revision,
            "ticker": row.ticker,
            "cadence": row.cadence,
            "market_session": row.market_session,
            "intraday_slot": row.intraday_slot,
            "factor_name": row.factor_name,
            "session_date": row.session_date.isoformat(),
            "value": row.value,
            "state_revision": row.state_revision,
            "row_checksum": row.row_checksum,
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    def _runtime_json(row: FactorRuntimeState) -> dict:
        return {
            "ticker": row.ticker,
            "cadence": row.cadence,
            "previous_close": row.previous_close,
            "latest_raw_return": row.latest_raw_return,
            "last_window_end": row.last_window_end.isoformat(),
            "state_revision": row.state_revision,
            "row_checksum": row.row_checksum,
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    def _offset_json(rows: list[FactorEngineOffset]) -> list[dict]:
        return [
            {
                "consumer_group": row.consumer_group,
                "topic": row.topic,
                "partition": row.partition,
                "next_offset": row.next_offset,
                "state_revision": row.state_revision,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]

    @staticmethod
    def _time_bounds(baseline: list[dict], runtime: list[dict]) -> dict:
        baseline_dates = [row["session_date"] for row in baseline]
        runtime_ends = [row["last_window_end"] for row in runtime]
        return {
            "baseline_session_date_min": min(baseline_dates, default=None),
            "baseline_session_date_max": max(baseline_dates, default=None),
            "runtime_window_end_min": min(runtime_ends, default=None),
            "runtime_window_end_max": max(runtime_ends, default=None),
        }

    @staticmethod
    def _validate_contents(path: Path, manifest: dict) -> None:
        epoch_id = str(manifest["epoch_id"])
        revision = int(manifest["revision"])
        baseline = pd.read_parquet(path / "baseline.parquet").to_dict("records")
        runtime_payload = json.loads((path / "runtime.json").read_text())
        offset_payload = json.loads((path / "offsets.json").read_text())
        for name, payload in (
            ("runtime", runtime_payload),
            ("offset", offset_payload),
        ):
            if (
                payload.get("epoch_id") != epoch_id
                or int(payload.get("revision", -1)) != revision
                or not isinstance(payload.get("rows"), list)
            ):
                raise ValueError(f"checkpoint {name} identity mismatch")
        if len(baseline) != int(manifest["baseline_rows"]):
            raise ValueError("checkpoint baseline row count mismatch")
        runtime = runtime_payload["rows"]
        offsets = offset_payload["rows"]
        if len(runtime) != int(manifest["runtime_rows"]):
            raise ValueError("checkpoint runtime row count mismatch")
        if offsets != manifest.get("offsets"):
            raise ValueError("checkpoint offset summary mismatch")
        if CheckpointManager._time_bounds(baseline, runtime) != manifest.get(
            "time_bounds"
        ):
            raise ValueError("checkpoint time bounds mismatch")
        for item in baseline:
            if (
                item.get("epoch_id") != epoch_id
                or int(item.get("checkpoint_revision", -1)) != revision
                or not 1 <= int(item["state_revision"]) <= revision
            ):
                raise ValueError("checkpoint baseline identity/revision mismatch")
            observation = BaselineObservation(
                ticker=item["ticker"],
                cadence=int(item["cadence"]),
                market_session=item["market_session"],
                intraday_slot=int(item["intraday_slot"]),
                factor_name=item["factor_name"],
                session_date=date.fromisoformat(str(item["session_date"])),
                value=float(item["value"]),
            )
            if item["row_checksum"] != observation_checksum(observation):
                raise ValueError("checkpoint baseline row checksum mismatch")
        for item in runtime:
            if not 1 <= int(item["state_revision"]) <= revision:
                raise ValueError("checkpoint runtime revision mismatch")
            state = RuntimeStateUpdate(
                ticker=item["ticker"],
                cadence=int(item["cadence"]),
                previous_close=float(item["previous_close"]),
                latest_raw_return=float(item["latest_raw_return"]),
                last_window_end=datetime.fromisoformat(item["last_window_end"]),
            )
            if item["row_checksum"] != runtime_checksum(state):
                raise ValueError("checkpoint runtime row checksum mismatch")
        if any(
            not 1 <= int(item["state_revision"]) <= revision for item in offsets
        ):
            raise ValueError("checkpoint offset revision mismatch")
