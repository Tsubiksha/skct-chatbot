"""db.py - SQLite connection manager for Graph RAG (graph_sqlite module).
Isolated from existing app DB. Stores data in data/graph_rag.db.
"""
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Resolve path: backend/app/graph_sqlite/db.py -> project root/data/graph_rag.db.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # .../graphrag/
_DEFAULT_DB = _PROJECT_ROOT / "data" / "graph_rag.db"

DB_PATH: Path = _DEFAULT_DB


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def db_conn():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetchall(sql: str, params: tuple = ()) -> list:
    conn = get_conn()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def fetchone(sql: str, params: tuple = ()):
    conn = get_conn()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def table_count(table: str) -> int:
    try:
        row = fetchone(f"SELECT COUNT(*) AS n FROM {table}")
        return row["n"] if row else 0
    except Exception:
        return 0
