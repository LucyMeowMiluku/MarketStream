from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings


@lru_cache
def get_engine():
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)


@lru_cache
def _session_factory():
    return sessionmaker(bind=get_engine())


def get_session() -> Session:
    return _session_factory()()
