"""Database schema, initialization, and connection management for FitTrack.

Uses standard library sqlite3 with foreign keys enabled and row factories.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Generator, Optional

DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "fittrack.db")


def get_db_path() -> str:
    """Return the database file path from environment or default."""
    return os.getenv("FITTRACK_DB_PATH", DEFAULT_DB_PATH)


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create a configured SQLite connection with foreign keys enabled."""
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database transactions with auto-commit and rollback."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Create all required database tables and indexes if they do not exist."""
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                duration_days INTEGER NOT NULL CHECK(duration_days > 0),
                price REAL NOT NULL CHECK(price >= 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trainers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                specialty TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                plan_id INTEGER NOT NULL REFERENCES plans(id),
                trainer_id INTEGER REFERENCES trainers(id) ON DELETE SET NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                amount REAL NOT NULL CHECK(amount >= 0),
                payment_date TEXT NOT NULL,
                payment_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS freezes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                days INTEGER NOT NULL CHECK(days > 0),
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS check_ins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER REFERENCES members(id) ON DELETE SET NULL,
                attempted_member_id INTEGER NOT NULL,
                check_in_date TEXT NOT NULL,
                check_in_time TEXT NOT NULL,
                allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
                reason TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_members_dates ON members(start_date, end_date);
            CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);
            CREATE INDEX IF NOT EXISTS idx_freezes_member_dates ON freezes(member_id, start_date, end_date);
            CREATE INDEX IF NOT EXISTS idx_check_ins_lookup ON check_ins(member_id, check_in_date, allowed);
            """
        )
