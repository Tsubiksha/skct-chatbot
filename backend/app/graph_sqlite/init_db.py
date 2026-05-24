"""init_db.py — Create all Graph RAG tables from schema.sql."""
import logging
from pathlib import Path
from backend.app.graph_sqlite.db import get_conn, DB_PATH

logger = logging.getLogger(__name__)
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db() -> dict:
    logger.info(f"[Graph RAG] Initialising database at: {DB_PATH}")
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_conn()
    try:
        conn.executescript(sql)
        _recreate_if_missing_columns(
            conn,
            "entities",
            {"name", "entity_type", "source_type", "source_id", "metadata_json"},
            """
            CREATE TABLE entities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                entity_type   TEXT NOT NULL,
                source_type   TEXT,
                source_id     INTEGER,
                metadata_json TEXT,
                UNIQUE(name, entity_type)
            )
            """,
        )
        _recreate_if_missing_columns(
            conn,
            "relationships",
            {"source_entity_id", "relation_type", "target_entity_id", "properties_json"},
            """
            CREATE TABLE relationships (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity_id  INTEGER NOT NULL,
                relation_type     TEXT NOT NULL,
                target_entity_id  INTEGER NOT NULL,
                properties_json   TEXT,
                UNIQUE(source_entity_id, relation_type, target_entity_id, properties_json),
                FOREIGN KEY(source_entity_id) REFERENCES entities(id),
                FOREIGN KEY(target_entity_id) REFERENCES entities(id)
            )
            """,
        )
        _ensure_column(conn, "ingestion_logs", "source_type", "TEXT")
        _ensure_column(conn, "ingestion_logs", "source_name", "TEXT")
        _ensure_column(conn, "ingestion_logs", "rows_read", "INTEGER DEFAULT 0")
        _ensure_column(conn, "ingestion_logs", "rows_inserted", "INTEGER DEFAULT 0")
        _ensure_column(conn, "ingestion_logs", "rows_skipped", "INTEGER DEFAULT 0")
        _ensure_column(conn, "graph_chat_sessions", "user_id", "TEXT")
        _ensure_column(conn, "graph_chat_messages", "user_id", "TEXT")
        _ensure_table(
            conn,
            "page_links",
            """
            CREATE TABLE IF NOT EXISTS page_links (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_page_id INTEGER,
                source_url     TEXT,
                target_url     TEXT,
                link_text      TEXT,
                depth          INTEGER,
                created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_url, target_url),
                FOREIGN KEY(source_page_id) REFERENCES scraped_pages(id)
            )
        """,
        )
        conn.commit()
        logger.info("[Graph RAG] Database initialised successfully.")
    finally:
        conn.close()
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "message": "Graph RAG database initialised. All tables created (IF NOT EXISTS).",
    }


def _ensure_column(conn, table: str, column: str, definition: str):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_table(conn, table: str, ddl: str):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row:
        conn.execute(ddl)


def _recreate_if_missing_columns(conn, table: str, required_columns: set[str], ddl: str):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if columns and required_columns.issubset(columns):
        return
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(ddl)
