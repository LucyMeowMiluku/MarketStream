from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tickers: list[str] = ["AAPL", "TSLA", "NVDA", "QQQ", "SPY"]

    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    raw_market_events_topic: str = "raw.market_events"
    factor_snapshots_topic: str = "stream.factor_snapshots"
    anomalies_topic: str = "stream.anomalies"
    factor_consumer_group: str = "factor-engine-v1"
    cep_consumer_group: str = "cep-online-v2"

    database_url: str = (
        "postgresql+psycopg://marketstream:marketstream@localhost:5432/marketstream"
    )

    # Live market data. Credentials are environment-only and SecretStr prevents
    # accidental plaintext representation in logs and tracebacks.
    alpaca_api_key: SecretStr | None = None
    alpaca_api_secret: SecretStr | None = None
    alpaca_data_feed: str = "iex"
    alpaca_stock_stream_url: str = "wss://stream.data.alpaca.markets/v2/iex"
    alpaca_news_stream_url: str = "wss://stream.data.alpaca.markets/v1beta1/news"
    databento_api_key: SecretStr | None = None

    # Lightweight factor plane.
    factor_cadences_seconds: list[int] = [10, 60, 300]
    factor_min_history_days: int = 5
    factor_baseline_days: int = 20
    factor_max_tickers: int = 64
    factor_stale_after_seconds: int = 30
    factor_gap_after_seconds: int = 90

    # Baseline startup is deliberately explicit.  Keeping this optional at
    # settings-import time lets offline tools run; baseline.startup rejects a
    # missing value before the live consumer subscribes.
    factor_baseline_startup_mode: str | None = None
    factor_baseline_epoch_id: str | None = None
    factor_baseline_algorithm_version: str = "rolling-mad-v3"
    factor_engine_version: str = "marketstream-0.1.0"
    factor_baseline_manifest: Path | None = None
    factor_baseline_manifest_sha256: str | None = None
    factor_baseline_activation_cutoff: str | None = None
    factor_baseline_replaces_epoch_id: str | None = None
    factor_baseline_recovery_reason: str | None = None
    factor_checkpoint_dir: Path = Path("data/baseline_checkpoints")
    factor_checkpoint_retention: int = 7
    factor_persistence_queue_max: int = 5_000
    factor_persistence_batch_size: int = 100
    factor_persistence_flush_ms: int = 250
    factor_persistence_shutdown_seconds: int = 30

    sentiment_recent_limit: int = 20

    # Six explicit factor state machines.
    cep_cooldown_seconds: int = 300
    cep_max_factor_frames: int = 64


settings = Settings()
