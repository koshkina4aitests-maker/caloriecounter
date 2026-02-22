from __future__ import annotations

import os

from sqlmodel import Session, SQLModel, create_engine


def _sqlite_connect_args(db_url: str) -> dict:
    if db_url.startswith("sqlite:"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lifetracker.db")
engine = create_engine(DATABASE_URL, connect_args=_sqlite_connect_args(DATABASE_URL))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)

