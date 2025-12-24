from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .config import DB_PATH


def engine_url() -> str:
    if DB_PATH.startswith("sqlite:"):
        return DB_PATH
    if DB_PATH.startswith("/"):
        return f"sqlite:///{DB_PATH}"
    return f"sqlite:///{DB_PATH}"


_engine = create_engine(engine_url(), future=True)


def session() -> Session:
    return Session(_engine)
