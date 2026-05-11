from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings


@lru_cache
def get_engine():
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)


def get_session() -> Session:
    factory = sessionmaker(bind=get_engine())
    return factory()
