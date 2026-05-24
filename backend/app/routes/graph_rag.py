"""
graph_rag.py — Legacy route stub.
Delegates everything to backend.app.graph_sqlite.router.
Kept for backward compatibility only.
"""
from fastapi import APIRouter
from backend.app.graph_sqlite.router import router as _gs_router

# Re-export the graph_sqlite router under the same prefix
router = _gs_router
