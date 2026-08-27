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

    price_poll_interval_seconds: int = 60
    news_poll_interval_seconds: int = 120
    window_duration_minutes: int = 5

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

    sentiment_recent_limit: int = 20
    sentiment_split_index: int = 10
    anomaly_price_threshold: float = 0.02
    anomaly_volume_threshold: int = 1_000_000
    anomaly_sentiment_threshold: float = 0.3
    anomaly_severity_threshold: float = -0.7

    # Ensemble
    ensemble_weights: list[float] = [0.40, 0.05, 0.45, 0.10]
    ensemble_threshold: float = -0.28

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

    # CEP (Complex Event Processing)
    # Primitive-event thresholds — the "simple indicators" the automata consume.
    cep_price_jump: float = 0.02  # |price_change_rate| >= this is a price jump
    cep_volume_surge_ratio: float = 3.0  # total_volume / baseline >= this is a surge
    cep_sentiment_shift: float = 0.3  # |sentiment_shift| >= this is a sentiment move
    cep_sentiment_floor: float = -0.5  # avg_sentiment <= this also counts as a drop
    cep_volume_ewma_span: int = 20  # span of the adaptive per-ticker volume baseline
    cep_min_volume_obs: int = 3  # warm-up windows before a volume surge can fire
    # Automaton + scoring knobs.
    cep_max_gap: int = 3  # max windows between matched events before reset
    cep_point_severity: float = 0.55  # severity of a lone primitive (simple-rule layer)
    cep_threshold: float = -0.5  # score below this flags an anomaly (CEP-only mode)
    cep_cooldown_seconds: int = 300
    cep_max_factor_frames: int = 64

    # The legacy four-model path is opt-in and does not block CEP production.
    ml_shadow_enabled: bool = False


settings = Settings()
