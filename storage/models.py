from datetime import datetime

from sqlalchemy import Float, Integer, String, Text, Boolean, DateTime, JSON, PrimaryKeyConstraint
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


class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    anomaly_score: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
