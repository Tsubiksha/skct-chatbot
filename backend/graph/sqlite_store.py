import asyncio
import hashlib
from collections import Counter
from datetime import datetime
from typing import Any

from backend.app.graph_rag.db import get_connection, init_db
from backend.models import Chunk, SourceDocument


class SQLiteKnowledgeStore:
    def __init__(self) -> None:
        init_db()

    async def close(self) -> None:
        return None

    async def health(self) -> str:
        try:
            await asyncio.to_thread(self.stats)
            return "active"
        except Exception:
            return "unavailable"

    async def reset(self) -> None:
        await asyncio.to_thread(self._reset_sync)

    def _reset_sync(self) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM relationships")
            connection.execute("DELETE FROM entities")
            connection.execute("DELETE FROM website_chunks")
            connection.execute("DELETE FROM scraped_pages")

    async def upsert_documents_and_chunks(self, documents: list[SourceDocument], chunks: list[Chunk]) -> None:
        await asyncio.to_thread(self._upsert_documents_and_chunks_sync, documents, chunks)

    def _upsert_documents_and_chunks_sync(self, documents: list[SourceDocument], chunks: list[Chunk]) -> None:
        now = datetime.utcnow().isoformat()
        chunks_by_url: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            chunks_by_url.setdefault(chunk.source_url, []).append(chunk)

        with get_connection() as connection:
            for document in documents:
                content_hash = hashlib.sha256(document.text.encode("utf-8", errors="ignore")).hexdigest()
                row = connection.execute("SELECT id FROM scraped_pages WHERE url = ?", (document.url,)).fetchone()
                if row:
                    page_id = row["id"]
                    connection.execute(
                        """
                        UPDATE scraped_pages
                        SET title = ?, page_type = ?, content = ?, content_hash = ?, scraped_at = ?
                        WHERE id = ?
                        """,
                        (document.title, self._page_type(document), document.text, content_hash, now, page_id),
                    )
                    connection.execute("DELETE FROM website_chunks WHERE page_id = ?", (page_id,))
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO scraped_pages(url, title, page_type, content, content_hash, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (document.url, document.title, self._page_type(document), document.text, content_hash, now),
                    )
                    page_id = cursor.lastrowid

                for chunk in chunks_by_url.get(document.url, []):
                    connection.execute(
                        """
                        INSERT INTO website_chunks(page_id, title, url, page_type, chunk_text, chunk_index, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (page_id, chunk.title, chunk.source_url, self._page_type(document), chunk.text, chunk.chunk_index, now),
                    )

    async def upsert_extracted_graph(self, extracted: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        return await asyncio.to_thread(self._upsert_extracted_graph_sync, extracted)

    def _upsert_extracted_graph_sync(self, extracted: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        now = datetime.utcnow().isoformat()
        counts = Counter()

        with get_connection() as connection:
            for entity_type in ["Department", "Faculty", "Company", "Course", "Event"]:
                for entity in extracted.get(entity_type, []):
                    page_id = self._page_id_for_url(connection, entity.get("source_url", ""))
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entities(entity_type, name, page_id, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (entity_type, entity["name"], page_id, now),
                    )
                    counts[entity_type] += 1

            for relationship in extracted.get("relationships", []):
                page_id = self._page_id_for_url(connection, relationship.get("source_url", ""))
                source_type, target_type = self._relationship_labels(relationship["type"])
                connection.execute(
                    """
                    INSERT OR IGNORE INTO relationships(
                        source_type, source_name, relationship_type, target_type, target_name, page_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_type,
                        relationship["source"],
                        relationship["type"],
                        target_type,
                        relationship["target"],
                        page_id,
                        now,
                    ),
                )
                counts["relationships"] += 1

        return dict(counts)

    async def query_context(self, names: list[str], limit: int = 12) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._query_context_sync, names, limit)

    def _query_context_sync(self, names: list[str], limit: int) -> list[dict[str, Any]]:
        if not names:
            return []

        clauses: list[str] = []
        params: list[str | int] = []
        for name in names[:8]:
            pattern = f"%{name}%"
            clauses.append("(source_name LIKE ? OR target_name LIKE ?)")
            params.extend([pattern, pattern])
        params.append(limit)

        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT source_type AS source_label,
                       source_name AS source,
                       relationship_type AS relationship,
                       target_type AS target_label,
                       target_name AS target
                FROM relationships
                WHERE {" OR ".join(clauses)}
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    async def stats(self) -> dict[str, int]:
        return await asyncio.to_thread(self._stats_sync)

    def _stats_sync(self) -> dict[str, int]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT entity_type, COUNT(*) AS count
                FROM entities
                GROUP BY entity_type
                """
            ).fetchall()
            counts = {str(row["entity_type"]).lower(): int(row["count"]) for row in rows}
            relationships = connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            chunks = connection.execute("SELECT COUNT(*) FROM website_chunks").fetchone()[0]

        return {
            "departments": counts.get("department", 0),
            "faculty": counts.get("faculty", 0),
            "courses": counts.get("course", 0),
            "companies": counts.get("company", 0),
            "events": counts.get("event", 0),
            "relationships": int(relationships),
            "chunks": int(chunks),
        }

    def _page_id_for_url(self, connection, url: str) -> int | None:
        if not url:
            return None
        row = connection.execute("SELECT id FROM scraped_pages WHERE url = ?", (url,)).fetchone()
        return int(row["id"]) if row else None

    def _page_type(self, document: SourceDocument) -> str:
        lowered = f"{document.url} {document.title} {document.text[:1000]}".lower()
        for page_type in ["placement", "department", "faculty", "academics", "event", "research"]:
            if page_type in lowered or f"{page_type}s" in lowered:
                return page_type
        return "home" if document.url.rstrip("/") == "https://skct.edu.in" else "general"

    def _relationship_labels(self, relationship_type: str) -> tuple[str, str]:
        labels = {
            "FACULTY_BELONGS_TO_DEPARTMENT": ("Faculty", "Department"),
            "FACULTY_TEACHES_COURSE": ("Faculty", "Course"),
            "COMPANY_HIRED_FROM_DEPARTMENT": ("Company", "Department"),
            "DEPARTMENT_OFFERS_COURSE": ("Department", "Course"),
            "EVENT_CONDUCTED_BY_DEPARTMENT": ("Event", "Department"),
        }
        return labels.get(relationship_type, ("Entity", "Entity"))
