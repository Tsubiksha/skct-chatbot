import sys
import logging
from pathlib import Path

# Ensure project root and backend/ are always on sys.path regardless of how uvicorn is started
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../graphrag/
_BACKEND_DIR  = Path(__file__).resolve().parents[1]   # .../graphrag/backend/
for _p in [str(_PROJECT_ROOT), str(_BACKEND_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("backend.app.graph_sqlite").setLevel(logging.INFO)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SKCT College AI Assistant",
    description="Production-grade GraphRAG backend with FastAPI, Ollama, and SQLite.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Initialize user/chat database (auth + conversations + messages) ──────────
from backend.database import init_db as init_user_db
init_user_db()

# ── Initialize Graph RAG SQLite database ────────────────────────────────────
from backend.app.graph_sqlite.init_db import init_db as init_graph_rag_db
try:
    init_graph_rag_db()
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning(f"Graph RAG DB init skipped: {_e}")

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "SKCT AI Assistant Backend is running."}

# ── Auth & Chat routes (user authentication + conversation management) ────────
from backend.app.routes import auth, chat
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat Operations"])

# ── Graph RAG pipeline routes (website scraping + FTS + Ollama) ──────────────
from backend.app.graph_sqlite.router import router as graph_sqlite_router
app.include_router(graph_sqlite_router, prefix="/api/graph-rag", tags=["Graph RAG"])

# ── Backward-compatible /query endpoint ─────────────────────────────────────
from pydantic import BaseModel
from typing import Optional

class _QueryRequest(BaseModel):
    question: Optional[str] = None
    query: Optional[str] = None
    top_k: int = 3

@app.post("/query")
async def query_root_endpoint(request: _QueryRequest):
    q = request.question or request.query
    if not q:
        raise HTTPException(status_code=400, detail="Query or question content is required")
    try:
        from backend.app.graph_sqlite.answer_service import answer_graph_question
        res = answer_graph_question(q)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
