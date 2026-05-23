import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "graph_rag.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def fts5_enabled() -> bool:
    try:
        with get_connection() as connection:
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts5_check USING fts5(value)")
            connection.execute("DROP TABLE IF EXISTS fts5_check")
        return True
    except sqlite3.Error:
        return False
