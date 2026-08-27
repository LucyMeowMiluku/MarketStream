from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PriceTick(Base):
    __tablename__ = "price_ticks"
    __table_args__ = (PrimaryKeyConstraint("time", "ticker"),)

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ticker: Mapped[str] = mapped_column(String(10))
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)


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


class FeatureVector(Base):
    __tablename__ = "feature_vectors"
    __table_args__ = (PrimaryKeyConstraint("window_end", "ticker"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ticker: Mapped[str] = mapped_column(String(10))
    avg_close: Mapped[float] = mapped_column(Float)
    price_change_rate: Mapped[float] = mapped_column(Float)
    total_volume: Mapped[int] = mapped_column(Integer)
    avg_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_shift: Mapped[float] = mapped_column(Float, default=0.0)
    headline_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    detector_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)


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
    legacy_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)


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


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    training_data_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_data_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anomaly_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_path: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class DriftEvent(Base):
    __tablename__ = "drift_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    feature_name: Mapped[str] = mapped_column(String(100))
    drift_type: Mapped[str] = mapped_column(String(50), default="adwin")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
