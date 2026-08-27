"""Public contracts for reviewed real-market replay runs."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml.event_metrics import GroundTruthEvent
from processing.event_models import DetectionResult, FactorSnapshot, as_utc


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewedInterval:
    interval_id: str
    kind: str
    ticker: str
    started_at: datetime
    ended_at: datetime
    direction: str | None = None
    pattern: str | None = None
    event_id: str | None = None
    evidence_urls: tuple[str, ...] = ()
    confidence: float | None = None
    approval_status: str = "proposed"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    notes: str = ""
    context_tickers: tuple[str, ...] = ("QQQ", "SPY")

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.upper())
        object.__setattr__(self, "started_at", as_utc(self.started_at))
        object.__setattr__(self, "ended_at", as_utc(self.ended_at))
        if self.reviewed_at is not None:
            object.__setattr__(self, "reviewed_at", as_utc(self.reviewed_at))
        object.__setattr__(
            self,
            "context_tickers",
            tuple(dict.fromkeys(item.upper() for item in self.context_tickers)),
        )
        if self.kind not in {"anomaly", "normal"}:
            raise ValueError(f"interval {self.interval_id}: kind must be anomaly or normal")
        if self.started_at >= self.ended_at:
            raise ValueError(f"interval {self.interval_id}: started_at must precede ended_at")
        if self.direction not in {None, "up", "down"}:
            raise ValueError(f"interval {self.interval_id}: direction must be up or down")
        if self.approval_status not in {"proposed", "approved", "rejected"}:
            raise ValueError(f"interval {self.interval_id}: invalid approval_status")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError(f"interval {self.interval_id}: confidence must be in [0, 1]")
        if self.kind == "anomaly" and (not self.event_id or not self.direction):
            raise ValueError(
                f"interval {self.interval_id}: anomaly labels require event_id and direction"
            )

    @property
    def approved(self) -> bool:
        return (
            self.approval_status == "approved"
            and bool(self.reviewed_by)
            and self.reviewed_at is not None
        )

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.ticker, *self.context_tickers)))

    def to_ground_truth(self) -> GroundTruthEvent:
        if self.kind != "anomaly":
            raise ValueError("normal intervals do not create GroundTruthEvent records")
        return GroundTruthEvent(
            event_id=self.event_id or self.interval_id,
            ticker=self.ticker,
            pattern=self.pattern or "market_anomaly",
            direction=self.direction or "up",
            started_at=self.started_at,
            ended_at=self.ended_at,
            evidence_urls=self.evidence_urls,
            label_status=self.approval_status,
            confidence=self.confidence,
            reviewed_by=self.reviewed_by,
            reviewed_at=self.reviewed_at,
            data_kind="real_historical",
            interval_id=self.interval_id,
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["started_at"] = self.started_at.isoformat()
        value["ended_at"] = self.ended_at.isoformat()
        value["reviewed_at"] = self.reviewed_at.isoformat() if self.reviewed_at else None
        value["evidence_urls"] = list(self.evidence_urls)
        value["context_tickers"] = list(self.context_tickers)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ReviewedInterval:
        parsed = dict(value)
        parsed["evidence_urls"] = tuple(parsed.get("evidence_urls", ()))
        parsed["context_tickers"] = tuple(parsed.get("context_tickers", ("QQQ", "SPY")))
        return cls(**parsed)


@dataclass(slots=True)
class ReplayRunConfig:
    dataset_manifest: Path
    labels_path: Path
    output_dir: Path
    run_id: str = field(
        default_factory=lambda: f"real-replay-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    )
    cadences: tuple[int, ...] = (10, 60, 300)
    timezone: str = "America/New_York"
    detector_version: str = "factor-cep-v1"
    min_history_days: int = 5
    baseline_days: int = 20
    bootstrap_samples: int = 1_000
    require_frozen_labels: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_manifest": str(self.dataset_manifest),
            "labels_path": str(self.labels_path),
            "output_dir": str(self.output_dir),
            "run_id": self.run_id,
            "cadences": list(self.cadences),
            "timezone": self.timezone,
            "detector_version": self.detector_version,
            "min_history_days": self.min_history_days,
            "baseline_days": self.baseline_days,
            "bootstrap_samples": self.bootstrap_samples,
            "require_frozen_labels": self.require_frozen_labels,
        }


@dataclass(slots=True)
class ReplayStep:
    run_id: str
    interval_id: str
    snapshot: FactorSnapshot
    detection: DetectionResult
    truth_kind: str
    truth_event_id: str | None = None
    detection_id: str | None = None
    match_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "interval_id": self.interval_id,
            "event_time": self.snapshot.event_time.isoformat(),
            "ticker": self.snapshot.ticker,
            "cadence": self.snapshot.cadence,
            "input_summary": self.snapshot.input_summary,
            "data_quality": self.snapshot.data_quality,
            "factor_values": self.snapshot.factor_values,
            "factor_states": self.snapshot.factor_states,
            "baseline_version": self.snapshot.baseline_version,
            "warmup_status": self.snapshot.warmup_status,
            "source_event_ids": self.snapshot.source_event_ids,
            "legacy_features": self.snapshot.legacy_features,
            "detection": self.detection.to_dict(),
            "truth_kind": self.truth_kind,
            "truth_event_id": self.truth_event_id,
            "detection_id": self.detection_id,
            "match_status": self.match_status,
        }
