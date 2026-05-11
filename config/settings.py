from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tickers: list[str] = ["AAPL", "TSLA", "NVDA"]

    kafka_bootstrap_servers: str = "127.0.0.1:9092"

    database_url: str = (
        "postgresql+psycopg://marketstream:marketstream@localhost:5432/marketstream"
    )

    price_poll_interval_seconds: int = 60
    news_poll_interval_seconds: int = 120
    window_duration_minutes: int = 5

    sentiment_recent_limit: int = 20
    sentiment_split_index: int = 10
    anomaly_price_threshold: float = 0.02
    anomaly_volume_threshold: int = 1_000_000
    anomaly_sentiment_threshold: float = 0.3
    anomaly_severity_threshold: float = -0.3

    # Ensemble
    ensemble_weights: list[float] = [0.2, 0.3, 0.3, 0.2]
    ensemble_threshold: float = -0.3

    # EWMA
    ewma_span: int = 20

    # Half-Space Trees
    hst_n_trees: int = 25
    hst_height: int = 6
    hst_window_size: int = 50

    # LSTM Autoencoder
    lstm_sequence_length: int = 12
    lstm_hidden_dim: int = 32
    lstm_model_path: str = "data/models/lstm_autoencoder.pt"

    # Drift detection
    drift_detection_enabled: bool = True
    drift_sensitivity: float = 0.002


settings = Settings()
