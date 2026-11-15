"""Database connection manager for CampusPilot AI.

Provides standard SQLite connections with foreign keys enabled and row-dictionary mapping.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Generator

# Project root is two levels up from app/database/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "campus.db"


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve and ensure parent directory for the database path."""
    if db_path is not None:
        resolved = Path(db_path)
    else:
        env_path = os.getenv("DATABASE_PATH")
        resolved = Path(env_path) if env_path else DEFAULT_DB_PATH

    # Make relative paths relative to project root
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved

    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def get_db_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create and return a configured SQLite connection.

    - Enables foreign key constraint enforcement.
    - Sets row_factory to sqlite3.Row for convenient dict-like access.
    """
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db_context(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe database connections with automatic commit/rollback and closing."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

