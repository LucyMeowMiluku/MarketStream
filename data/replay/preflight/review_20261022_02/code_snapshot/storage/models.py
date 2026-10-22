from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarketEventRecord(Base):
    __tablename__ = "market_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    feed: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(20))
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    quality_flags: Mapped[list] = mapped_column(JSON)


class SentimentScore(Base):
    __tablename__ = "sentiment_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    headline: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    sentiment_score: Mapped[float] = mapped_column(Float)
    sentiment_label: Mapped[str] = mapped_column(String(20))


class FactorSnapshotRecord(Base):
    __tablename__ = "factor_snapshots"
    __table_args__ = (PrimaryKeyConstraint("event_time", "ticker", "cadence"),)

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ticker: Mapped[str] = mapped_column(String(10))
    cadence: Mapped[str] = mapped_column(String(8))
    factor_values: Mapped[dict] = mapped_column(JSON)
    factor_states: Mapped[dict] = mapped_column(JSON)
    baseline_version: Mapped[str] = mapped_column(String(100))
    data_quality: Mapped[dict] = mapped_column(JSON)
    warmup_status: Mapped[str] = mapped_column(String(20))
    source_event_ids: Mapped[list] = mapped_column(JSON)
    input_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class BaselineEpoch(Base):
    """Registry entry for one independently auditable live baseline epoch."""

    __tablename__ = "baseline_epochs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('BUILDING','ACTIVE','RECOVERING','RETIRED','FAILED','CORRUPT')",
            name="ck_baseline_epochs_status",
        ),
        Index(
            "ux_baseline_epochs_active_namespace",
            "namespace",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    epoch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(32), nullable=False, default="live")
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    factor_schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    activation_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_baseline_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_runtime_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expected_partition_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    source_manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replaces_epoch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recovery_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FactorBaselineSample(Base):
    __tablename__ = "factor_baseline_samples"
    __table_args__ = (
        PrimaryKeyConstraint(
            "epoch_id",
            "ticker",
            "cadence",
            "market_session",
            "intraday_slot",
            "factor_name",
            "session_date",
        ),
    )

    epoch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("baseline_epochs.epoch_id", ondelete="RESTRICT")
    )
    ticker: Mapped[str] = mapped_column(String(10))
    cadence: Mapped[int] = mapped_column(Integer)
    market_session: Mapped[str] = mapped_column(String(20))
    intraday_slot: Mapped[int] = mapped_column(Integer)
    factor_name: Mapped[str] = mapped_column(String(64))
    session_date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    state_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FactorRuntimeState(Base):
    __tablename__ = "factor_runtime_state"
    __table_args__ = (PrimaryKeyConstraint("epoch_id", "ticker", "cadence"),)

    epoch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("baseline_epochs.epoch_id", ondelete="RESTRICT")
    )
    ticker: Mapped[str] = mapped_column(String(10))
    cadence: Mapped[int] = mapped_column(Integer)
    previous_close: Mapped[float] = mapped_column(Float)
    latest_raw_return: Mapped[float] = mapped_column(Float)
    last_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class FactorEngineOffset(Base):
    __tablename__ = "factor_engine_offsets"
    __table_args__ = (
        PrimaryKeyConstraint("epoch_id", "consumer_group", "topic", "partition"),
    )

    epoch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("baseline_epochs.epoch_id", ondelete="RESTRICT")
    )
    consumer_group: Mapped[str] = mapped_column(String(128))
    topic: Mapped[str] = mapped_column(String(255))
    partition: Mapped[int] = mapped_column(Integer)
    next_offset: Mapped[int] = mapped_column(BigInteger)
    state_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class BaselineCheckpoint(Base):
    __tablename__ = "baseline_checkpoints"
    __table_args__ = (
        PrimaryKeyConstraint("epoch_id", "revision"),
        CheckConstraint(
            "status IN ('WRITING','COMMITTED','INVALID')",
            name="ck_baseline_checkpoints_status",
        ),
        Index("ix_baseline_checkpoints_status", "epoch_id", "status"),
    )

    epoch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("baseline_epochs.epoch_id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    baseline_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    runtime_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    offsets_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    detector_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pattern_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    factor_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trigger_event_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    data_quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
