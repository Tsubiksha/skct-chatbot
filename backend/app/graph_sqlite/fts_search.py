"""
fts_search.py — Improved SQLite FTS5 search for SKCT Graph RAG.

Improvements:
  - Sanitized FTS5 query building (handles punctuation, stops, quotes)
  - Multi-term OR search for broader recall
  - Phrase matching for multi-word queries
  - Page-type boosting (relevant page types ranked higher)
  - Score normalisation returned with each result
  - Falls back to LIKE search if FTS5 unavailable or query fails
"""

import re
import logging
from backend.app.graph_sqlite.db import get_conn

logger = logging.getLogger(__name__)

_FTS_AVAILABLE: bool | None = None

# Stop-words to exclude from FTS query terms
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "about", "tell", "give",
    "more", "information", "details", "show", "what", "which", "who", "when",
    "where", "how", "is", "are", "was", "were", "does", "did", "of", "in",
    "on", "to", "from", "at", "by", "its", "it", "this", "that", "these",
    "those", "has", "have", "had", "do", "be", "been", "can", "could",
    "would", "should", "me", "my", "your", "our", "their",
}

# Page types to boost when detected in query
_PAGE_TYPE_BOOSTS = {
    "placement":    ["placement", "placed", "recruiter", "package", "lpa", "career", "campus", "company", "companies"],
    "department":   ["department", "dept", "cse", "ece", "eee", "mech", "civil", "aids", "it", "biotechnology"],
    "faculty":      ["faculty", "staff", "hod", "professor", "professor", "teaching", "head"],
    "contact":      ["contact", "phone", "email", "address", "location", "reach", "map"],
    "about":        ["about", "established", "founded", "history", "naac", "nba", "accreditation"],
    "training":     ["training", "internship", "aptitude", "skill", "soft skill"],
    "event":        ["event", "workshop", "seminar", "symposium", "hackathon", "fest"],
    "academics":    ["course", "programme", "program", "b.e", "b.tech", "ug", "pg", "mba", "mca"],
    "research":     ["research", "publication", "journal", "patent", "project", "funded"],
    "regulations":  ["regulation", "syllabus", "curriculum", "anna university", "r2021"],
    "hostel":       ["hostel", "accommodation", "residence"],
    "library":      ["library", "books", "e-journal", "digital"],
}


def search_website(
    query: str,
    limit: int = 10,
    page_type: str | None = None,
    boost_page_type: bool = True,
) -> list[dict]:
    """
    Search scraped SKCT website chunks.
    Returns results ordered by relevance (FTS5 BM25 + page-type boost).
    Falls back to LIKE search if FTS5 unavailable.
    """
    if not query or not query.strip():
        return []

    conn = get_conn()
    try:
        if _check_fts(conn):
            results = _fts_multi_pass(conn, query, limit * 2, page_type)
            if results is None:
                results = _like_search(conn, query, limit * 2, page_type)
        else:
            results = _like_search(conn, query, limit * 2, page_type)

        if not results:
            return []

        # Apply page-type boost scoring
        if boost_page_type:
            results = _apply_boost(results, query)

        # Deduplicate by chunk text prefix
        seen_prefixes: set[str] = set()
        deduped = []
        for r in results:
            prefix = (r.get("chunk_text") or "")[:120].strip().lower()
            if prefix and prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                deduped.append(r)

        return deduped[:limit]

    except Exception as e:
        logger.error(f"[FTS] Search error: {e}")
        try:
            return _like_search(conn, query, limit, page_type)[:limit]
        except Exception as e2:
            logger.error(f"[FTS] LIKE fallback also failed: {e2}")
            return []
    finally:
        conn.close()


def fts_status() -> dict:
    """Return FTS availability and chunk count."""
    conn = get_conn()
    try:
        avail = _check_fts(conn)
        count = conn.execute("SELECT COUNT(*) FROM website_chunks").fetchone()[0]
        page_count = conn.execute("SELECT COUNT(*) FROM scraped_pages").fetchone()[0]
    except Exception:
        avail = False
        count = 0
        page_count = 0
    finally:
        conn.close()
    return {
        "fts5_available": avail,
        "total_chunks": count,
        "total_pages": page_count,
    }


def reset_fts_cache():
    """Call this after rebuilding the FTS index."""
    global _FTS_AVAILABLE
    _FTS_AVAILABLE = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_fts(conn) -> bool:
    global _FTS_AVAILABLE
    if _FTS_AVAILABLE is not None:
        return _FTS_AVAILABLE
    try:
        conn.execute("SELECT rowid FROM website_chunks_fts LIMIT 1")
        _FTS_AVAILABLE = True
    except Exception:
        _FTS_AVAILABLE = False
        logger.warning("[FTS] FTS5 unavailable — using LIKE fallback.")
    return _FTS_AVAILABLE


def _build_fts_query(query: str) -> str | None:
    """
    Build a safe FTS5 query expression from a natural language query.
    Returns None if no usable terms remain.

    Strategy:
    1. Extract alphanumeric tokens ≥ 3 chars, skip stop-words
    2. Wrap 2+ word phrases in quotes for phrase matching
    3. Join remaining individual terms with OR
    """
    # Normalize
    query = query.strip()
    if not query:
        return None

    # Remove special FTS5 operator chars that cause syntax errors
    sanitized = re.sub(r'[^\w\s]', ' ', query)

    tokens = [
        t.lower() for t in sanitized.split()
        if len(t) >= 3 and t.lower() not in _STOP_WORDS
    ]

    if not tokens:
        return None

    terms: list[str] = []

    # If original query has multiple meaningful words → add phrase variant
    if len(tokens) >= 2:
        phrase = " ".join(tokens)
        terms.append(f'"{phrase}"')

    # Add individual terms for broader recall
    for t in tokens:
        terms.append(f'"{t}"')

    return " OR ".join(terms)


def _fts_multi_pass(
    conn,
    query: str,
    limit: int,
    page_type: str | None,
) -> list[dict] | None:
    """
    Run FTS5 query. On failure, automatically tries a simpler single-term fallback.
    Returns None only if FTS itself is unavailable.
    """
    fts_query = _build_fts_query(query)
    if not fts_query:
        return None

    # Pass 1: full multi-term query
    result = _run_fts(conn, fts_query, limit, page_type)
    if result is not None:
        return result

    # Pass 2: simplified — individual terms only
    tokens = [
        t.lower() for t in re.sub(r'[^\w\s]', ' ', query).split()
        if len(t) >= 3 and t.lower() not in _STOP_WORDS
    ]
    if tokens:
        simple_query = " OR ".join(f'"{t}"' for t in tokens[:5])
        result = _run_fts(conn, simple_query, limit, page_type)
        if result is not None:
            return result

    return []


def _run_fts(
    conn,
    fts_expression: str,
    limit: int,
    page_type: str | None,
) -> list[dict] | None:
    """Execute a single FTS5 query. Returns None on FTS syntax error."""
    try:
        if page_type:
            sql = """
                SELECT wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text,
                       bm25(website_chunks_fts) AS score
                FROM website_chunks wc
                JOIN website_chunks_fts fts ON fts.rowid = wc.id
                WHERE website_chunks_fts MATCH ?
                  AND wc.page_type = ?
                ORDER BY score
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_expression, page_type, limit)).fetchall()
        else:
            sql = """
                SELECT wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text,
                       bm25(website_chunks_fts) AS score
                FROM website_chunks wc
                JOIN website_chunks_fts fts ON fts.rowid = wc.id
                WHERE website_chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_expression, limit)).fetchall()

        return [_row_to_dict(r) for r in rows]

    except Exception as e:
        logger.debug(f"[FTS] Query failed ({e!r}) — will try fallback")
        return None


def _like_search(
    conn,
    query: str,
    limit: int,
    page_type: str | None,
) -> list[dict]:
    """LIKE-based fallback search."""
    like = f"%{query}%"
    if page_type:
        rows = conn.execute(
            """SELECT id, title, url, page_type, chunk_text, 0 AS score
               FROM website_chunks
               WHERE (chunk_text LIKE ? OR title LIKE ?)
                 AND page_type = ?
               LIMIT ?""",
            (like, like, page_type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, title, url, page_type, chunk_text, 0 AS score
               FROM website_chunks
               WHERE chunk_text LIKE ? OR title LIKE ?
               LIMIT ?""",
            (like, like, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _apply_boost(results: list[dict], query: str) -> list[dict]:
    """
    Apply page-type relevance boost based on query keywords.
    Returns results sorted by boosted score (descending).
    """
    query_lower = query.lower()

    # Detect relevant page types from query
    relevant_types: set[str] = set()
    for ptype, keywords in _PAGE_TYPE_BOOSTS.items():
        if any(kw in query_lower for kw in keywords):
            relevant_types.add(ptype)

    for r in results:
        # BM25 score from SQLite is negative (lower = better). Normalise to 0–1.
        raw_score = r.get("score", 0) or 0
        # Convert negative BM25 to positive similarity-style score
        normalised = max(0.0, min(1.0, 1.0 / (1.0 + abs(raw_score))))

        # Boost if page type matches query intent
        if r.get("page_type") in relevant_types:
            normalised = min(1.0, normalised + 0.25)

        # Boost if query terms appear in title
        title_lower = (r.get("title") or "").lower()
        tokens = [t for t in re.sub(r'[^\w\s]', ' ', query_lower).split()
                  if len(t) >= 3 and t not in _STOP_WORDS]
        title_hits = sum(1 for t in tokens if t in title_lower)
        if title_hits:
            normalised = min(1.0, normalised + 0.1 * title_hits)

        r["relevance_score"] = round(normalised, 4)

    return sorted(results, key=lambda r: r.get("relevance_score", 0), reverse=True)


def _row_to_dict(r) -> dict:
    """Safely convert a sqlite3.Row or tuple to dict."""
    try:
        return {
            "title":           r["title"],
            "url":             r["url"],
            "page_type":       r["page_type"],
            "chunk_text":      r["chunk_text"],
            "score":           r["score"] if "score" in r.keys() else 0,
            "relevance_score": 0.0,
        }
    except (TypeError, IndexError):
        return {
            "title":           r[1] if len(r) > 1 else "",
            "url":             r[2] if len(r) > 2 else "",
            "page_type":       r[3] if len(r) > 3 else "",
            "chunk_text":      r[4] if len(r) > 4 else "",
            "score":           r[5] if len(r) > 5 else 0,
            "relevance_score": 0.0,
        }
