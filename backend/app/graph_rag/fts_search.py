import sqlite3

from backend.app.graph_rag.db import get_connection, init_db


def search_website(query: str, limit: int = 5) -> list[dict]:
    init_db()
    cleaned_query = " ".join(query.strip().split())
    if not cleaned_query:
        return []

    with get_connection() as connection:
        try:
            rows = connection.execute(
                """
                SELECT wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text,
                       bm25(website_chunks_fts) AS score
                FROM website_chunks_fts
                JOIN website_chunks wc ON wc.id = website_chunks_fts.rowid
                WHERE website_chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (_fts_query(cleaned_query), limit),
            ).fetchall()
        except sqlite3.Error:
            rows = connection.execute(
                """
                SELECT id, title, url, page_type, chunk_text, 0.0 AS score
                FROM website_chunks
                WHERE title LIKE ? OR chunk_text LIKE ? OR page_type LIKE ?
                LIMIT ?
                """,
                (f"%{cleaned_query}%", f"%{cleaned_query}%", f"%{cleaned_query}%", limit),
            ).fetchall()

    return [dict(row) for row in rows]


def _fts_query(query: str) -> str:
    tokens = [token.replace('"', "") for token in query.split() if token.strip()]
    return " OR ".join(f'"{token}"' for token in tokens) or query
