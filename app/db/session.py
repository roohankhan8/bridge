from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings



def _with_default_connect_timeout(database_url: str) -> URL:
    url = make_url(database_url)
    if url.get_backend_name() == "postgresql" and "connect_timeout" not in url.query:
        return url.update_query_dict({"connect_timeout": "5"})
    return url


engine = create_engine(_with_default_connect_timeout(get_settings().database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
