from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def get_engine():
    connect_args = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        # SQLite wymaga check_same_thread=False w trybie wielowątkowym
        connect_args = {"check_same_thread": False}
    return create_engine(settings.DATABASE_URL, connect_args=connect_args)


engine = get_engine()

# Włącz foreign keys dla SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency – yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
