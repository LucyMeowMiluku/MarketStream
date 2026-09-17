from sqlalchemy import text

from config.logging_config import get_logger
from storage.db import get_engine
from storage.migrations import run_migrations
from storage.models import Base

log = get_logger("init_db")

HYPERTABLES = {
    "sentiment_scores": "time",
    "factor_snapshots": "event_time",
}


def init_database():
    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("tables_created")

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        run_migrations(conn)
        conn.commit()

        for table, time_column in HYPERTABLES.items():
            try:
                conn.execute(
                    text(
                        f"SELECT create_hypertable('{table}', "
                        f"by_range('{time_column}', INTERVAL '1 day'), if_not_exists => TRUE)"
                    )
                )
                conn.commit()
                log.info("hypertable_created", table=table)
            except Exception as e:
                conn.rollback()
                log.warning("hypertable_skipped", table=table, error=str(e))

    log.info("database_initialized")


if __name__ == "__main__":
    init_database()
