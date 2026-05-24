"""
graph_rag_router.py — FastAPI routes for website-based Graph RAG.

All routes under /api/graph-rag/ (mounted in main.py).
Scraping runs as a FastAPI BackgroundTask — returns immediately with a job_id.
"""

import logging
import threading
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.graph_sqlite.db import table_count, fetchall
from backend.app.graph_sqlite.init_db import init_db
from backend.app.graph_sqlite.web_scraper import scrape_website
from backend.app.graph_sqlite.website_entity_extractor import extract_website_entities
from backend.app.graph_sqlite.fts_search import search_website, fts_status, reset_fts_cache
from backend.app.graph_sqlite.answer_service import answer_graph_question, stream_graph_question
from backend.app.graph_sqlite.graph_queries import get_related_entities
from backend.app.graph_sqlite.chunker import rebuild_fts

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory job store for background scrape jobs ────────────────────────────
_jobs: dict[str, dict] = {}


# ── Request / response models ─────────────────────────────────────────────────

class GraphChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None


class ScrapeRequest(BaseModel):
    force_reindex: bool = False
    max_pages:     Optional[int] = 60
    max_depth:     Optional[int] = 3
    clear_first:   bool = True


class ReindexRequest(BaseModel):
    clear_data: bool = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(data=None, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data or {}}


def _fail(error: str, status_code: int = 400):
    from fastapi import HTTPException
    raise HTTPException(status_code=status_code, detail=error)


def _clear_website_tables():
    from backend.app.graph_sqlite.db import get_conn
    conn = get_conn()
    try:
        for table in [
            "relationships", "entities",
            "website_chunks_fts", "website_chunks", "page_links", "scraped_pages",
            "graph_chat_messages", "graph_chat_sessions",
            "ingestion_logs",
        ]:
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception as e:
                logger.warning(f"Could not clear {table}: {e}")
        conn.commit()
    finally:
        conn.close()


# ── Background scrape runner ──────────────────────────────────────────────────

def _run_scrape_job(job_id: str, max_pages: int, max_depth: int,
                    force_reindex: bool, clear_first: bool):
    """Runs in a background thread. Updates _jobs[job_id] with progress."""
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = time.time()
    try:
        if clear_first:
            logger.info(f"[Job {job_id}] Clearing old data...")
            _clear_website_tables()
            reset_fts_cache()
            _jobs[job_id]["step"] = "cleared"

        logger.info(f"[Job {job_id}] Scraping website (max_pages={max_pages}, max_depth={max_depth})...")
        _jobs[job_id]["step"] = "scraping"
        scrape_result = scrape_website(
            max_pages=max_pages,
            max_depth=max_depth,
            force_reindex=force_reindex,
        )
        _jobs[job_id]["scrape"] = scrape_result
        _jobs[job_id]["step"] = "scrape_done"

        logger.info(f"[Job {job_id}] Building knowledge graph...")
        _jobs[job_id]["step"] = "building_graph"
        graph_result = extract_website_entities()
        _jobs[job_id]["graph"] = graph_result
        _jobs[job_id]["step"] = "graph_done"

        logger.info(f"[Job {job_id}] Rebuilding FTS index...")
        _jobs[job_id]["step"] = "rebuilding_fts"
        fts_count = rebuild_fts()
        reset_fts_cache()
        _jobs[job_id]["fts_chunks"] = fts_count
        _jobs[job_id]["step"] = "done"

        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["completed_at"] = time.time()
        elapsed = round(_jobs[job_id]["completed_at"] - _jobs[job_id]["started_at"], 1)
        logger.info(
            f"[Job {job_id}] DONE in {elapsed}s — "
            f"pages={scrape_result.get('pages_saved',0)}, "
            f"chunks={scrape_result.get('chunks_created',0)}, "
            f"fts={fts_count}"
        )
    except Exception as e:
        logger.exception(f"[Job {job_id}] Failed: {e}")
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _jobs[job_id]["completed_at"] = time.time()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/init")
def api_init_db():
    """Initialize the Graph RAG SQLite database (creates tables if not exists)."""
    try:
        result = init_db()
        return _ok(result, message="Graph RAG database initialised.")
    except Exception as e:
        logger.error(f"init error: {e}")
        _fail(str(e), 500)


@router.post("/scrape-website")
def api_scrape_website(body: ScrapeRequest = None):
    """
    Launch a background scrape job.
    Returns immediately with a job_id.
    Poll /job/{job_id} to check progress.
    """
    body = body or ScrapeRequest()
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id":    job_id,
        "status":    "queued",
        "step":      "queued",
        "max_pages": body.max_pages,
        "max_depth": body.max_depth,
    }

    t = threading.Thread(
        target=_run_scrape_job,
        args=(job_id, body.max_pages or 60, body.max_depth or 3,
              body.force_reindex, body.clear_first),
        daemon=True,
    )
    t.start()

    return _ok(
        {"job_id": job_id},
        message=(
            f"Scrape job {job_id} started in background. "
            f"Poll GET /api/graph-rag/job/{job_id} for progress."
        )
    )


@router.get("/job/{job_id}")
def api_job_status(job_id: str):
    """Check status of a background scrape job."""
    job = _jobs.get(job_id)
    if not job:
        _fail(f"Job '{job_id}' not found.", 404)
    return _ok(job, message=f"Job {job_id} is {job.get('status','unknown')}.")


@router.get("/jobs")
def api_all_jobs():
    """List all scrape jobs (most recent first)."""
    jobs_list = sorted(_jobs.values(), key=lambda j: j.get("started_at", 0), reverse=True)
    return _ok({"jobs": jobs_list[:20]})


@router.post("/build-graph")
def api_build_graph():
    """Extract entities and relationships from scraped pages (website-only graph)."""
    try:
        result = extract_website_entities()
        return _ok(result, message=(
            f"Graph built. Entities: {result.get('entities_created', 0)}, "
            f"Relationships: {result.get('relationships_created', 0)}"
        ))
    except Exception as e:
        logger.error(f"build-graph error: {e}")
        _fail(str(e), 500)


@router.post("/rebuild-fts")
def api_rebuild_fts():
    """Rebuild FTS5 index from existing website_chunks table."""
    try:
        count = rebuild_fts()
        reset_fts_cache()
        return _ok({"chunks_indexed": count}, message=f"FTS5 index rebuilt with {count} chunks.")
    except Exception as e:
        logger.error(f"rebuild-fts error: {e}")
        _fail(str(e), 500)


@router.post("/reindex")
def api_reindex(body: ReindexRequest = None):
    """
    Launch a full background reindex pipeline (same as scrape-website with clear_first=True).
    Returns a job_id immediately.
    """
    body = body or ReindexRequest()
    scrape_body = ScrapeRequest(
        force_reindex=True,
        max_pages=60,
        max_depth=3,
        clear_first=body.clear_data,
    )
    return api_scrape_website(scrape_body)


@router.post("/chat")
def api_graph_chat(body: GraphChatRequest):
    """Website-based Graph RAG chat: retrieve context from SKCT website, generate answer."""
    if not body.message or not body.message.strip():
        _fail("Message cannot be empty.", 400)
    try:
        result = answer_graph_question(
            question=body.message.strip(),
            session_id=body.session_id,
        )
        return _ok(result, message="Graph RAG response generated.")
    except RuntimeError as e:
        _fail(str(e), 503)
    except Exception as e:
        logger.error(f"chat error: {e}")
        _fail(str(e), 500)


@router.post("/chat/stream")
def api_graph_chat_stream(body: GraphChatRequest):
    """Streaming plain-text endpoint for Graph RAG chat."""
    if not body.message or not body.message.strip():
        _fail("Message cannot be empty.", 400)

    def token_generator():
        try:
            for token in stream_graph_question(body.message.strip()):
                yield token
        except Exception as e:
            yield f"\n\n⚠️ Stream error: {e}"

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/stats")
def api_stats():
    """Return row counts and FTS status."""
    fts = fts_status()
    return _ok({
        "scraped_pages":  table_count("scraped_pages"),
        "website_chunks": table_count("website_chunks"),
        "page_links":     table_count("page_links"),
        "entities":       table_count("entities"),
        "relationships":  table_count("relationships"),
        "fts5_available": fts["fts5_available"],
        "fts_total_chunks": fts.get("total_chunks", 0),
        "fts_total_pages":  fts.get("total_pages", 0),
    })


@router.get("/website-search")
def api_website_search(query: str, limit: int = 5,
                        page_type: Optional[str] = None):
    """FTS5 search over scraped SKCT website content."""
    if not query or not query.strip():
        _fail("query parameter is required.", 400)
    results = search_website(query.strip(), limit=limit, page_type=page_type)
    return _ok({"query": query, "results": results, "count": len(results)})


@router.get("/scraped-pages")
def api_scraped_pages(limit: int = 30):
    """List recently scraped pages."""
    rows = fetchall(
        "SELECT title, url, page_type, scraped_at FROM scraped_pages "
        "ORDER BY scraped_at DESC LIMIT ?",
        (limit,)
    )
    return _ok({"pages": [dict(r) for r in rows], "count": len(rows)})


@router.get("/related")
def api_related_entities(entity_name: str, limit: int = 20):
    """Graph relationships for a named entity."""
    if not entity_name:
        _fail("entity_name is required.", 400)
    return _ok(get_related_entities(entity_name, limit=limit))


@router.get("/logs")
def api_logs(limit: int = 20):
    """Return latest ingestion logs."""
    rows = fetchall(
        "SELECT source_type, source_name, status, message, rows_inserted, rows_skipped, created_at "
        "FROM ingestion_logs ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    return _ok({"logs": [dict(r) for r in rows]})


@router.delete("/clear")
def api_clear_data():
    """Clear all scraped/graph data (keeps schema intact)."""
    try:
        _clear_website_tables()
        reset_fts_cache()
        return _ok(message="All website data cleared. Run /scrape-website to reingest.")
    except Exception as e:
        logger.error(f"clear error: {e}")
        _fail(str(e), 500)
