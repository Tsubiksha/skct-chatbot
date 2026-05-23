import asyncio
from datetime import datetime

import httpx

from backend.config import get_settings
from backend.app.graph_rag.chunker import chunk_text
from backend.app.graph_rag.db import get_connection, init_db, fts5_enabled
from backend.app.graph_rag.entity_extractor import extract_entities_and_relationships
from backend.app.graph_rag.fts_search import search_website
from backend.app.graph_rag.web_scraper import SKCTWebsiteScraper

settings = get_settings()
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_llm_model


class GraphRAGService:
    def __init__(self) -> None:
        init_db()

    async def scrape_website(self, force_reindex: bool = False, max_pages: int = 30, max_depth: int = 2) -> dict:
        return await asyncio.to_thread(self._scrape_website_sync, force_reindex, max_pages, max_depth)

    def _scrape_website_sync(self, force_reindex: bool, max_pages: int, max_depth: int) -> dict:
        scraper = SKCTWebsiteScraper()
        result = scraper.scrape(max_pages=max_pages, max_depth=max_depth)
        pages_saved = 0
        pages_updated = 0
        chunks_created = 0

        with get_connection() as connection:
            if force_reindex:
                connection.execute("DELETE FROM relationships")
                connection.execute("DELETE FROM entities")
                connection.execute("DELETE FROM website_chunks")
                connection.execute("DELETE FROM scraped_pages")

            for page in result.pages:
                existing = connection.execute("SELECT id, content_hash FROM scraped_pages WHERE url = ?", (page.url,)).fetchone()
                if existing and existing["content_hash"] == page.content_hash and not force_reindex:
                    continue

                now = datetime.utcnow().isoformat()
                if existing:
                    page_id = existing["id"]
                    connection.execute(
                        """
                        UPDATE scraped_pages
                        SET title = ?, page_type = ?, content = ?, content_hash = ?, scraped_at = ?
                        WHERE id = ?
                        """,
                        (page.title, page.page_type, page.content, page.content_hash, now, page_id),
                    )
                    connection.execute("DELETE FROM website_chunks WHERE page_id = ?", (page_id,))
                    connection.execute("DELETE FROM entities WHERE page_id = ?", (page_id,))
                    connection.execute("DELETE FROM relationships WHERE page_id = ?", (page_id,))
                    pages_updated += 1
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO scraped_pages(url, title, page_type, content, content_hash, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (page.url, page.title, page.page_type, page.content, page.content_hash, now),
                    )
                    page_id = cursor.lastrowid
                    pages_saved += 1

                for chunk in chunk_text(page.content):
                    connection.execute(
                        """
                        INSERT INTO website_chunks(page_id, title, url, page_type, chunk_text, chunk_index, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (page_id, page.title, page.url, page.page_type, chunk.chunk_text, chunk.chunk_index, now),
                    )
                    chunks_created += 1

                entities, relationships = extract_entities_and_relationships(page_id, page.title, page.url, page.page_type, page.content)
                for entity in entities:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO entities(entity_type, name, page_id, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (entity["entity_type"], entity["name"], entity["page_id"], now),
                    )
                for relationship in relationships:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO relationships(
                            source_type, source_name, relationship_type, target_type, target_name, page_id, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            relationship["source_type"],
                            relationship["source_name"],
                            relationship["relationship_type"],
                            relationship["target_type"],
                            relationship["target_name"],
                            relationship["page_id"],
                            now,
                        ),
                    )

            status = "success" if pages_saved or pages_updated or chunks_created else "warning"
            message = "Scraping complete" if status == "success" else "No new pages were saved. The website may be blocking requests or pages may already exist."
            connection.execute(
                """
                INSERT INTO ingestion_logs(status, message, pages_visited, pages_saved, pages_updated, chunks_created, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (status, message, result.pages_visited, pages_saved, pages_updated, chunks_created, datetime.utcnow().isoformat()),
            )

        return {
            "status": status,
            "pages_visited": result.pages_visited,
            "pages_saved": pages_saved,
            "pages_updated": pages_updated,
            "chunks_created": chunks_created,
            "errors": result.errors[:5],
        }

    def stats(self) -> dict:
        with get_connection() as connection:
            return {
                "pages": connection.execute("SELECT COUNT(*) FROM scraped_pages").fetchone()[0],
                "chunks": connection.execute("SELECT COUNT(*) FROM website_chunks").fetchone()[0],
                "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "relationships": connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
                "fts5_enabled": fts5_enabled(),
                "sqlite_active": True,
            }

    def scraped_pages(self) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT title, url, page_type, scraped_at
                FROM scraped_pages
                ORDER BY scraped_at DESC
                LIMIT 100
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        return search_website(query, limit=limit)

    def graph_context_for_chunks(self, chunks: list[dict]) -> list[dict]:
        urls = [chunk["url"] for chunk in chunks]
        if not urls:
            return []

        placeholders = ",".join("?" for _ in urls)
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT r.source_name, r.relationship_type, r.target_name, p.url
                FROM relationships r
                JOIN scraped_pages p ON p.id = r.page_id
                WHERE p.url IN ({placeholders})
                LIMIT 12
                """,
                urls,
            ).fetchall()
        return [dict(row) for row in rows]

    async def answer(self, question: str) -> dict:
        chunks = self.search(question, limit=5)
        if not chunks:
            return {
                "answer": "I could not find this in the scraped SKCT website data.",
                "sources": [],
                "graph_context": [],
            }

        graph_context = self.graph_context_for_chunks(chunks)
        prompt = self._build_prompt(question, chunks, graph_context)
        answer = await self._generate_with_ollama(prompt)
        return {
            "answer": answer,
            "sources": chunks,
            "graph_context": graph_context,
        }

    async def health(self) -> dict:
        ollama_status = "unavailable"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                response.raise_for_status()
            ollama_status = "connected"
        except Exception:
            pass

        stats = self.stats()
        return {
            "fastapi": "running",
            "ollama": ollama_status,
            "sqlite": "active" if stats["sqlite_active"] else "unavailable",
            "fts5": "enabled" if stats["fts5_enabled"] else "unavailable",
        }

    async def _generate_with_ollama(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()

    def _build_prompt(self, question: str, chunks: list[dict], graph_context: list[dict]) -> str:
        context = "\n\n".join(
            f"Source {index + 1}: {chunk['title']}\nURL: {chunk['url']}\nPage Type: {chunk['page_type']}\nText: {chunk['chunk_text']}"
            for index, chunk in enumerate(chunks)
        )
        graph = "\n".join(
            f"{row['source_name']} -> {row['relationship_type']} -> {row['target_name']}"
            for row in graph_context
        ) or "No graph relationships found for retrieved chunks."

        return f"""
You are an AI-powered SKCT GraphRAG assistant.

Answer ONLY using the provided SKCT website context and graph relationships.
Do not hallucinate.
If information is unavailable, say:
"I could not find this in the scraped SKCT website data."

Question:
{question}

SKCT website context:
{context}

Graph relationships:
{graph}

Grounded answer:
""".strip()
