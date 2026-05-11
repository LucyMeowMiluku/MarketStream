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


settings = Settings()
