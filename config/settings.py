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
    cep_price_jump: float = 0.02        # |price_change_rate| >= this is a price jump
    cep_volume_surge_ratio: float = 3.0  # total_volume / baseline >= this is a surge
    cep_sentiment_shift: float = 0.3     # |sentiment_shift| >= this is a sentiment move
    cep_sentiment_floor: float = -0.5    # avg_sentiment <= this also counts as a drop
    cep_volume_ewma_span: int = 20       # span of the adaptive per-ticker volume baseline
    cep_min_volume_obs: int = 3          # warm-up windows before a volume surge can fire
    # Automaton + scoring knobs.
    cep_max_gap: int = 3                 # max windows between matched events before reset
    cep_point_severity: float = 0.55     # severity of a lone primitive (simple-rule layer)
    cep_threshold: float = -0.5          # score below this flags an anomaly (CEP-only mode)


settings = Settings()
