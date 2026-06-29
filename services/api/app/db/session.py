from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


@event.listens_for(engine, "connect")
def register_pgvector(dbapi_connection, _connection_record) -> None:
    try:
        from pgvector.psycopg2 import register_vector

        register_vector(dbapi_connection)
    except Exception:
        # Registration is best effort for non-Postgres unit tests and migration tooling.
        pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
