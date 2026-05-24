"""
answer_service.py — Improved Graph RAG answer generation for SKCT.

Improvements:
  - Multi-pass retrieval (question → expanded keyword sets)
  - Smart intent detection → targeted page_type filter
  - Chunk de-duplication before prompting
  - Real relevance scoring (no hardcoded 85)
  - Clean website-only system prompt
  - Source citations embedded in answer
  - Streaming support via Ollama API
"""

import re
import json
import logging
import requests
import time
from typing import Iterator
from urllib.parse import urlparse

from backend.app.config import settings
from backend.app.graph_sqlite.db import get_conn
from backend.app.graph_sqlite.fts_search import search_website
from backend.app.graph_sqlite.graph_queries import get_related_entities

logger = logging.getLogger(__name__)

# ── System prompt (website-only, SKCT-specific) ───────────────────────────────
SYSTEM_PROMPT = """You are the official AI Assistant for Sri Krishna College of Technology (SKCT), Coimbatore.

Your knowledge comes ONLY from the SKCT official website (skct.edu.in) and structured knowledge graph.

=== STRICT RULES ===
1. Answer ONLY using the provided [CONTEXT] sections below. Do NOT invent or hallucinate any details.
2. If the context does not contain the answer, say: "I could not find this information on the SKCT website. Please visit skct.edu.in or contact the college directly."
3. Cite your sources: after key facts, add (Source: <page title>) in parentheses.
4. Be precise, professional, and complete. For list questions, include the full retrieved list.
5. Use Markdown formatting: bullets for lists, **bold** for important terms, tables for structured data.
6. Do NOT copy navigation labels, image alt-text, or repeated link text as facts.
7. For contact information: extract exact phone numbers, emails, and addresses from the context — do not say they are missing if they appear anywhere in the context.
8. Do NOT include a <think> block, scratchpad, or reasoning steps in your output — only the final answer.
9. The institution is Sri Krishna College of Technology (SKCT). Do not confuse it with sister institutions unless asked.
"""

# ── Intent → page type mapping ────────────────────────────────────────────────
_INTENT_MAP = [
    # (keywords_in_query, primary_page_type, secondary_types)
    (["placement", "placed", "package", "lpa", "salary", "ctc", "recruit", "campus", "job", "hire", "offer letter"],
     "placement", ["recruiter", "training"]),
    (["recruiter", "company", "companies", "visiting", "mnc", "tcs", "infosys", "wipro"],
     "recruiter", ["placement"]),
    (["training", "internship", "aptitude", "soft skill", "bridge course", "skill"],
     "training", ["placement"]),
    (["hod", "head of department", "faculty", "staff", "professor", "lecturer", "dean"],
     "faculty", ["department"]),
    (["department", "dept", "cse", "ece", "eee", "it ", "mechanical", "civil", "aids", "ai&ds",
      "biotechnology", "automobile", "chemical", "mba", "mca"],
     "department", ["academics", "faculty"]),
    (["course", "programme", "program", "ug", "pg", "b.e", "b.tech", "m.e", "degree", "branch", "offered"],
     "academics", ["department"]),
    (["contact", "phone", "email", "address", "location", "located", "locate", "where is", "reach", "map", "call", "helpline"],
     "contact", ["about"]),
    (["principal", "director", "founder", "chairman", "management", "secretary", "trustee"],
     "principal", ["management", "about"]),
    (["event", "workshop", "seminar", "symposium", "hackathon", "fest", "webinar", "news", "announcement"],
     "event", ["training"]),
    (["research", "publication", "journal", "conference", "patent", "ipr", "funded project"],
     "research", ["industry_connect"]),
    (["syllabus", "curriculum", "regulation", "anna university", "r2021", "r2017", "credit"],
     "regulations", ["academics"]),
    (["exam", "examination", "internal", "coe", "revaluation", "arrear", "result", "mark"],
     "exams", ["regulations"]),
    (["hostel", "accommodation", "residence", "dormitory", "mess", "room"],
     "hostel", ["contact"]),
    (["library", "books", "digital library", "e-journal", "reading"],
     "library", ["academics"]),
    (["sports", "athletic", "cricket", "football", "basketball", "gym", "outdoor", "indoor"],
     "sports", ["event"]),
    (["scholarship", "fee", "financial aid", "merit", "concession"],
     "scholarship", ["about"]),
    (["alumni", "old student", "graduate", "former student"],
     "alumni", ["placement"]),
    (["mou", "collaboration", "industry", "partner", "industry-institute"],
     "industry_connect", ["research"]),
    (["admission", "apply", "application", "tnea", "counselling", "eligibility", "cutoff"],
     "about", ["academics"]),
    (["canteen", "cafeteria", "food", "mess"],
     "general", ["contact"]),
    (["history", "established", "founded", "vision", "mission", "about skct", "institution",
      "naac", "nba", "accreditation", "ranking", "recognition"],
     "about", ["vision_mission", "principal"]),
]

# ── Stop words for keyword extraction ─────────────────────────────────────────
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "about", "tell", "give",
    "me", "us", "more", "information", "details", "show", "what", "which",
    "who", "when", "where", "how", "is", "are", "was", "were", "does", "did",
    "of", "in", "on", "to", "from", "at", "by", "its", "it", "this", "that",
    "has", "have", "had", "do", "be", "been", "can", "could", "would", "should",
    "skct", "college", "sri", "krishna", "technology", "please", "located", "locate",
}

_INTENT_EXPANSIONS = {
    "placement": ["placement cell", "career services", "recruiters", "campus recruitment", "training", "package"],
    "recruiter": ["recruiters", "companies", "placement", "campus recruitment"],
    "training": ["career services training", "placement training", "aptitude", "soft skill"],
    "faculty": ["faculty", "staff", "hod", "head of department", "professor"],
    "department": ["departments", "programmes", "courses", "hod", "faculty"],
    "academics": ["academics", "programmes", "courses offered", "curriculum", "academic calendar"],
    "contact": ["contact us", "phone", "email", "address", "kovaipudur", "coimbatore"],
    "about": ["institution", "about us", "vision mission", "accreditation", "history"],
    "principal": ["principal", "head of the institution", "Sumithra", "Institutionalleaders"],
    "event": ["events", "workshop", "seminar", "symposium", "webinar"],
    "research": ["research and development", "funded projects", "publication", "patent", "ipr"],
    "industry_connect": ["industry connect", "mous", "centre of excellence", "industry supported lab"],
    "regulations": ["regulations", "syllabus", "curriculum"],
    "exams": ["examinations", "controller of examinations", "timetable", "results", "hallticket"],
    "hostel": ["hostel", "accommodation", "mess"],
    "library": ["library", "learning centre", "digital library"],
    "sports": ["sports", "indoor", "outdoor", "gym"],
}

_NOISE_MARKERS = (
    "image file:", "image alt:", "image title:", "link:", "data:image/",
    "page-loader", "go to top", "facebook", "instagram", "youtube",
)


# ── Main public function ──────────────────────────────────────────────────────

def answer_graph_question(question: str, session_id: str | None = None) -> dict:
    """
    Full RAG pipeline: retrieve → assemble context → generate answer.
    Returns dict with: answer, sources, retrieval_meta, session_id.
    """
    question = (question or "").strip()
    if not question:
        return {"answer": "Please ask a question.", "sources": [], "retrieval_meta": {}}

    started_at = time.perf_counter()

    # 1. Detect intent and page types to search
    primary_type, secondary_types = _detect_intent(question)
    logger.info(f"[RAG] Q='{question[:80]}' intent={primary_type} secondary={secondary_types}")

    # 2. Multi-pass retrieval
    chunks = _multi_pass_retrieve(question, primary_type, secondary_types)
    logger.info(
        "[RAG] retrieved %s chunks: %s",
        len(chunks),
        " | ".join(f"{c.get('title', 'untitled')}:{c.get('final_score', c.get('relevance_score', 0))}" for c in chunks[:5]),
    )

    # 3. Get graph context
    graph_ctx = _get_graph_context(question)
    if primary_type == "department" and _is_department_list_question(question):
        graph_ctx = {"relationships": []}

    direct_answer = _direct_answer_if_available(question, primary_type, chunks)
    if direct_answer:
        sources = _extract_sources(chunks)
        return {
            "answer": direct_answer,
            "sources": sources,
            "retrieval_meta": {
                "chunks_used": len(chunks),
                "primary_intent": primary_type,
                "graph_relationships": len(graph_ctx.get("relationships", [])),
                "direct_answer": True,
            },
            "elapsed_seconds": round(time.perf_counter() - started_at, 2),
            "session_id": session_id,
        }

    # 4. Build prompt context
    context_block = _build_context_block(question, chunks, graph_ctx)

    # 5. Generate answer via Ollama
    answer_text = _call_ollama(question, context_block)

    # 6. Format sources
    sources = _extract_sources(chunks)

    return {
        "answer": answer_text,
        "sources": sources,
        "retrieval_meta": {
            "chunks_used": len(chunks),
            "primary_intent": primary_type,
            "graph_relationships": len(graph_ctx.get("relationships", [])),
        },
        "elapsed_seconds": round(time.perf_counter() - started_at, 2),
        "session_id": session_id,
    }


def stream_graph_question(question: str) -> Iterator[str]:
    """
    Streaming version — yields answer tokens one by one.
    """
    question = (question or "").strip()
    if not question:
        yield "Please ask a question."
        return

    primary_type, secondary_types = _detect_intent(question)
    chunks = _multi_pass_retrieve(question, primary_type, secondary_types)
    graph_ctx = _get_graph_context(question)
    if primary_type == "department" and _is_department_list_question(question):
        graph_ctx = {"relationships": []}
    direct_answer = _direct_answer_if_available(question, primary_type, chunks)
    if direct_answer:
        yield direct_answer
        return
    context_block = _build_context_block(question, chunks, graph_ctx)

    yield from _stream_ollama(question, context_block)


# ── Intent detection ──────────────────────────────────────────────────────────

def _detect_intent(question: str) -> tuple[str | None, list[str]]:
    """Return (primary_page_type, secondary_types) based on question keywords."""
    q = question.lower()
    if _is_department_list_question(question) and any(
        kw in q for kw in ("ug", "pg", "phd", "programme", "program", "course", "offered")
    ):
        return "department", ["academics", "faculty"]
    for keywords, primary, secondary in _INTENT_MAP:
        if any(kw in q for kw in keywords):
            return primary, secondary
    return None, []


# ── Multi-pass retrieval ──────────────────────────────────────────────────────

def _multi_pass_retrieve(
    question: str,
    primary_type: str | None,
    secondary_types: list[str],
    total_limit: int = 6,
) -> list[dict]:
    """
    Retrieve chunks across multiple passes:
    1. Filtered by primary page type
    2. Filtered by secondary page types (if not enough results)
    3. Global search without page-type filter (catch-all)
    Deduplicates and returns top-N by relevance.
    """
    collected: list[dict] = []
    seen_keys: set[str] = set()
    keywords = _extract_keywords(question)
    query_variants = _expanded_queries(question, primary_type)

    def _add_results(results: list[dict]):
        for r in results:
            text = (r.get("chunk_text") or "").strip()
            key = (
                (r.get("url") or "").strip().lower(),
                r.get("chunk_index"),
                text[:160].lower(),
            )
            if text and key not in seen_keys:
                seen_keys.add(key)
                collected.append(r)

    _add_results(_direct_keyword_chunks(question, keywords, primary_type, limit=6))
    _add_results(_direct_intent_chunks(primary_type, limit=5))

    # Principal pages often point to a PDF profile; include it directly when present.
    if primary_type == "principal":
        _add_results(_direct_principal_chunks(limit=3))
    if primary_type == "contact":
        _add_results(_contact_direct_scan())
    if primary_type == "event":
        _add_results(_direct_event_chunks(limit=4))

    # Pass 1: primary page type (more precise)
    if primary_type:
        for variant in query_variants[:2]:
            _add_results(search_website(variant, limit=5, page_type=primary_type, boost_page_type=True))

    # Pass 2: secondary types (broaden if needed)
    if len(collected) < 6:
        for stype in secondary_types[:2]:
            _add_results(search_website(query_variants[0], limit=4, page_type=stype, boost_page_type=True))

    # Pass 3: global/document fallback for facts stored in PDFs or mislabeled pages.
    if len(collected) < 8:
        for variant in query_variants[:3]:
            _add_results(search_website(variant, limit=5, page_type=None, boost_page_type=True))
        _add_results(search_website(query_variants[0], limit=4, page_type="document", boost_page_type=True))

    if not collected:
        logger.warning(f"[RAG] No chunks found for: '{question[:80]}'")
        return []

    # Sort by relevance score descending
    collected.sort(key=lambda r: r.get("relevance_score", 0), reverse=True)

    # De-noise: drop chunks where the question keywords don't appear at all
    scored = _rescore_chunks(collected, keywords, primary_type)
    if primary_type == "contact":
        scored = _filter_contact_chunks(scored)
        total_limit = min(total_limit, 2)
    if primary_type == "department" and _is_department_list_question(question):
        scored = _filter_department_list_chunks(scored, question)
        total_limit = min(total_limit, 2)
    if primary_type == "event" and _is_event_list_question(question):
        scored = _filter_event_chunks(scored)
        total_limit = min(max(total_limit, 8), 10)

    return scored[:total_limit]


def _filter_contact_chunks(chunks: list[dict]) -> list[dict]:
    """For contact/location questions, keep only compact address/contact evidence."""
    filtered = []
    for chunk in chunks:
        text = (chunk.get("chunk_text") or "").lower()
        title = (chunk.get("title") or "").lower()
        url = (chunk.get("url") or "").lower()
        page_type = chunk.get("page_type") or ""
        has_contact_fact = any(
            marker in text
            for marker in ("address", "kovaipudur", "coimbatore", "phone", "email")
        )
        if page_type == "contact" or "contact-us" in url or "contact" in title or has_contact_fact:
            filtered.append(chunk)
    return filtered or chunks


def _is_department_list_question(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in ("available", "list", "all", "what are", "departments", "courses", "programs", "programmes"))


def _filter_department_list_chunks(chunks: list[dict], question: str) -> list[dict]:
    summary = [chunk for chunk in chunks if chunk.get("title") == "SKCT Departments Summary"]
    department_page = [
        chunk for chunk in chunks
        if "academics/departments" in (chunk.get("url") or "").lower()
    ]
    if summary:
        summary = [_trim_department_summary_for_question(summary[0], question)]
        return summary + department_page[:1]
    return chunks


def _trim_department_summary_for_question(chunk: dict, question: str) -> dict:
    groups = _requested_program_groups(question)
    if not groups:
        return chunk
    text = chunk.get("chunk_text") or ""
    lines = text.splitlines()
    kept = [lines[0]] if lines else ["Official department/program pages found in the SKCT website data:"]
    for line in lines[1:]:
        if any(line.startswith(f"{group} Departments/Programs:") for group in groups):
            kept.append(line)
    trimmed = dict(chunk)
    trimmed["chunk_text"] = "\n".join(kept)
    return trimmed


def _requested_program_groups(question: str) -> list[str]:
    q = question.lower()
    groups = []
    if re.search(r"\bug\b|undergraduate", q):
        groups.append("UG")
    if re.search(r"\bpg\b|postgraduate", q):
        groups.append("PG")
    if re.search(r"\bph\.?\s*d\b|doctor", q):
        groups.append("PhD")
    return groups


def _is_event_list_question(question: str) -> bool:
    q = question.lower()
    return any(word in q for word in ("event", "events", "conducted", "organized", "organised", "workshop", "seminar"))


def _filter_event_chunks(chunks: list[dict]) -> list[dict]:
    priority = []
    rest = []
    for chunk in chunks:
        title = (chunk.get("title") or "").lower()
        url = (chunk.get("url") or "").lower()
        text = (chunk.get("chunk_text") or "").lower()
        if chunk.get("title") == "SKCT Events Summary":
            priority.append(chunk)
        elif "previous-events" in url or "event-details" in url or "event-organized" in url or "events" in title:
            priority.append(chunk)
        elif any(word in text for word in ("seminar", "workshop", "conference", "hackathon", "programme", "program")):
            rest.append(chunk)
    return priority + rest


def _expanded_queries(question: str, primary_type: str | None) -> list[str]:
    """Build a compact set of intent-aware search queries."""
    queries = [question]
    keywords = _extract_keywords(question)
    if keywords:
        queries.append(" ".join(keywords[:6]))
    if primary_type:
        for expansion in _INTENT_EXPANSIONS.get(primary_type, [])[:4]:
            if expansion.lower() not in question.lower():
                queries.append(f"{question} {expansion}")
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        clean = re.sub(r"\s+", " ", query).strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            deduped.append(clean)
    return deduped


def _direct_keyword_chunks(
    question: str,
    keywords: list[str],
    primary_type: str | None,
    limit: int = 6,
) -> list[dict]:
    """Pull exact title/url/content candidates before FTS ranking."""
    terms = [t for t in keywords if len(t) >= 4][:5]
    if primary_type:
        terms.append(primary_type)
    if not terms:
        terms = [question.strip()]

    conn = get_conn()
    try:
        clauses = []
        params: list[str | int] = []
        for term in terms:
            like = f"%{term}%"
            clauses.append("(lower(title) LIKE lower(?) OR lower(url) LIKE lower(?) OR lower(chunk_text) LIKE lower(?))")
            params.extend([like, like, like])
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT title, url, page_type, chunk_text, chunk_index
            FROM website_chunks
            WHERE {" OR ".join(clauses)}
            ORDER BY
                CASE WHEN lower(title) LIKE lower(?) OR lower(url) LIKE lower(?) THEN 0 ELSE 1 END,
                CASE WHEN page_type = ? THEN 0 ELSE 1 END,
                length(chunk_text) DESC
            LIMIT ?
            """,
            params[:-1] + [f"%{terms[0]}%", f"%{terms[0]}%", primary_type or "", params[-1]],
        ).fetchall()
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "page_type": r["page_type"],
                "chunk_text": r["chunk_text"],
                "chunk_index": r["chunk_index"],
                "score": 0,
                "relevance_score": 0.72,
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug(f"[RAG] Direct keyword lookup failed: {e}")
        return []
    finally:
        conn.close()


def _direct_intent_chunks(primary_type: str | None, limit: int = 5) -> list[dict]:
    """Known high-value rows for intents whose pages are commonly mislabeled."""
    if not primary_type:
        return []

    url_patterns = {
        "contact": ["%/about-us/contact-us%"],
        "department": ["%/departments%", "%/academics/departments%"],
        "hostel": ["%/campus-tour/hostel%"],
        "placement": ["%/placement/placement-cell%", "%/placement/recruiters%", "%/training%"],
        "research": ["%/research/rd-cell%", "%/research/funded-projects%", "%/research/ipr-cell%"],
        "library": ["%/campus-tour/library%"],
        "sports": ["%/campus-tour/sports%"],
        "event": ["%/previous-events%", "%/events%", "%/event-details%", "%/event-organized%"],
        "industry_connect": ["%/industry-connect/mous%", "%/industry-connect/centre-of-excellence%"],
        "exams": ["%/examinations/coe-office%", "%/examinations/results%", "%/examinations/timetable%"],
    }.get(primary_type, [])

    rows = []
    conn = get_conn()
    try:
        if primary_type == "department":
            rows.append(_department_summary_chunk(conn))
        if primary_type == "contact":
            rows.append(_contact_fact_chunk(conn))
        if primary_type == "event":
            rows.append(_event_summary_chunk(conn))
        for pattern in url_patterns:
            rows.extend(conn.execute(
                """
                SELECT title, url, page_type, chunk_text, chunk_index
                FROM website_chunks
                WHERE lower(url) LIKE lower(?)
                ORDER BY chunk_index
                LIMIT 2
                """,
                (pattern,),
            ).fetchall())
        return [
            {
                "title": row["title"] if hasattr(row, "keys") else row["title"],
                "url": row["url"] if hasattr(row, "keys") else row["url"],
                "page_type": row["page_type"] if hasattr(row, "keys") else row["page_type"],
                "chunk_text": row["chunk_text"] if hasattr(row, "keys") else row["chunk_text"],
                "chunk_index": row["chunk_index"] if hasattr(row, "keys") and "chunk_index" in row.keys() else 0,
                "score": 0,
                "relevance_score": 0.9,
            }
            for row in rows[:limit]
            if row
        ]
    except Exception as e:
        logger.debug(f"[RAG] Direct intent lookup failed for {primary_type}: {e}")
        return []
    finally:
        conn.close()


def _department_summary_chunk(conn) -> dict:
    rows = conn.execute(
        """
        SELECT DISTINCT title, url
        FROM scraped_pages
        WHERE lower(url) LIKE '%/department/%'
        ORDER BY title
        LIMIT 300
        """
    ).fetchall()
    groups: dict[str, list[str]] = {"UG": [], "PG": [], "PhD": [], "Other": []}
    seen_slugs: set[str] = set()
    for row in rows:
        parsed = urlparse(row["url"] or "")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 2 or parts[0].lower() != "department":
            continue

        slug = parts[1].lower()
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        title = _clean_department_title(row["title"] or "", slug)
        if not title:
            continue
        lowered_title = title.lower()
        if lowered_title.startswith("phd"):
            groups["PhD"].append(title)
        elif lowered_title.startswith(("m.e.", "master")):
            groups["PG"].append(title)
        elif lowered_title.startswith(("b.e.", "b.tech")):
            groups["UG"].append(title)
        else:
            groups["Other"].append(title)

    parts = ["Official department/program pages found in the SKCT website data:"]
    for label in ("UG", "PG", "PhD", "Other"):
        if groups[label]:
            parts.append(f"{label} Departments/Programs: " + "; ".join(groups[label]))
    text = "\n".join(parts)
    return {
        "title": "SKCT Departments Summary",
        "url": "https://skct.edu.in/departments",
        "page_type": "department",
        "chunk_text": text,
        "chunk_index": 0,
    }


def _clean_department_title(title: str, slug: str = "") -> str:
    slug_titles = {
        "computer-science-and-engineering-artificial-intelligence-and-machine-learning":
            "B.E. Computer Science and Engineering (Artificial Intelligence and Machine Learning)",
        "science-and-humanities": "Science and Humanities",
        "phd-electronics-and-communication-engineering": "PhD Electronics and Communication Engineering",
    }
    if slug in slug_titles:
        return slug_titles[slug]
    title = re.sub(r"\s*-\s*Sri Krishna College of Technology\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*-\s*SKCT College(?: Coimbatore)?\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*-\s*SKCT Coimbatore\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*-\s*SKCT college Coimbatore\s*$", "", title, flags=re.I).strip()
    title = title.replace("PhD.", "PhD")
    return re.sub(r"\s+", " ", title).strip()


def _event_summary_chunk(conn) -> dict:
    rows = conn.execute(
        """
        SELECT title, url, page_type, chunk_text
        FROM website_chunks
        WHERE lower(url) LIKE '%previous-events%'
           OR lower(url) LIKE '%event-details%'
           OR lower(url) LIKE '%event-organized%'
           OR lower(title) LIKE '%event%'
        ORDER BY
            CASE
                WHEN lower(url) LIKE '%previous-events%' THEN 0
                WHEN lower(url) LIKE '%event-details%' THEN 1
                WHEN lower(url) LIKE '%event-organized%' THEN 2
                ELSE 3
            END,
            chunk_index
        LIMIT 60
        """
    ).fetchall()

    events: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for event in _extract_event_items(row["chunk_text"] or ""):
            key = event.lower()
            if key not in seen:
                seen.add(key)
                events.append(event)
            if len(events) >= 40:
                break
        if len(events) >= 40:
            break

    text = "Events found in SKCT website data:\n" + "\n".join(f"- {event}" for event in events[:40])
    return {
        "title": "SKCT Events Summary",
        "url": "https://skct.edu.in/previous-events",
        "page_type": "event",
        "chunk_text": text,
        "chunk_index": 0,
    }


def _extract_event_items(text: str) -> list[str]:
    text = re.sub(r"Structured name:[^\n]+", " ", text)
    text = re.sub(r"Image (?:alt|title|file):[^\n]+", " ", text)
    text = re.sub(r"Link:[^\n]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    event_words = (
        "seminar", "workshop", "conference", "hackathon", "symposium", "webinar",
        "camp", "awareness", "lecture", "contest", "fdp", "programme", "program",
        "training", "meet", "challenge", "course", "celebration",
    )
    candidates: list[str] = []
    title_pattern = re.compile(
        r"(?:^|\s)(?:\d{1,3}\s+)?([A-Z][A-Z0-9&@ .:/,'()–-]{10,}?)"
        r"(?=\s+(?:\d{4}-\d{2}-\d{2}|Department|SKCT|Sri Krishna|Venue|Date|Dear|Faculty|A lecture|All are|Objective:))"
    )
    candidates.extend(match.group(1) for match in title_pattern.finditer(text))

    dated_pattern = re.compile(
        r"(?:\d{1,3}\s+)?(?:\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2})\s+"
        r"([A-Z][A-Z0-9&@ .:/,'()–-]{10,}?)(?=\s+(?:SEMINAR|WORKSHOP|CONTEST|FDP|GUEST|FACULTY|[0-9]{1,4}\b|Structured|$))"
    )
    candidates.extend(match.group(1) for match in dated_pattern.finditer(text))

    events = []
    for part in candidates:
        part = part.strip(" -;,.")
        if len(part) < 12 or len(part) > 180:
            continue
        if "http" in part.lower() or "data.skct" in part.lower():
            continue
        lowered = part.lower()
        if not any(word in lowered for word in event_words):
            continue
        part = re.sub(r"^\d+\s+", "", part)
        part = re.sub(r"\s+", " ", part).strip()
        if part:
            events.append(part)
    return events


def _direct_event_chunks(limit: int = 4) -> list[dict]:
    conn = get_conn()
    try:
        summary = _event_summary_chunk(conn)
        rows = conn.execute(
            """
            SELECT title, url, page_type, chunk_text, chunk_index
            FROM website_chunks
            WHERE lower(url) LIKE '%previous-events%'
               OR lower(url) LIKE '%event-details%'
               OR lower(url) LIKE '%event-organized%'
            ORDER BY
                CASE
                    WHEN lower(url) LIKE '%previous-events%' THEN 0
                    WHEN lower(url) LIKE '%event-details%' THEN 1
                    WHEN lower(url) LIKE '%event-organized%' THEN 2
                    ELSE 3
                END,
                chunk_index
            LIMIT ?
            """,
            (max(1, limit - 1),),
        ).fetchall()
        chunks = [{
            "title": summary["title"],
            "url": summary["url"],
            "page_type": summary["page_type"],
            "chunk_text": summary["chunk_text"],
            "chunk_index": 0,
            "score": 0,
            "relevance_score": 1.1,
        }]
        chunks.extend(
            {
                "title": r["title"],
                "url": r["url"],
                "page_type": r["page_type"],
                "chunk_text": r["chunk_text"],
                "chunk_index": r["chunk_index"],
                "score": 0,
                "relevance_score": 0.95,
            }
            for r in rows
        )
        return chunks
    finally:
        conn.close()


def _contact_fact_chunk(conn) -> dict:
    rows = conn.execute(
        """
        SELECT name, entity_type
        FROM entities
        WHERE entity_type IN ('Email', 'Phone', 'Address')
          AND (
                name IN ('info@skct.edu.in', 'principal@skct.edu.in', '0422-2984567', '0422-2984568')
             OR lower(name) LIKE '%kovaipudur%'
             OR lower(name) LIKE '%coimbatore%641 042%'
          )
        ORDER BY
            CASE entity_type WHEN 'Phone' THEN 0 WHEN 'Email' THEN 1 WHEN 'Address' THEN 2 ELSE 3 END,
            name
        LIMIT 80
        """
    ).fetchall()
    grouped: dict[str, list[str]] = {"Phone": [], "Email": [], "Address": []}
    for row in rows:
        value = _clean_contact_value(row["name"])
        etype = row["entity_type"]
        if value not in grouped.get(etype, []):
            grouped.setdefault(etype, []).append(value)
    grouped["Address"] = _best_contact_addresses(grouped.get("Address", []))
    parts = []
    for label in ("Phone", "Email", "Address"):
        if grouped.get(label):
            parts.append(f"{label}: " + "; ".join(grouped[label]))
    text = "SKCT contact facts extracted from the knowledge graph. " + " ".join(parts)
    return {
        "title": "SKCT Contact Facts",
        "url": "https://skct.edu.in/about-us/contact-us",
        "page_type": "contact",
        "chunk_text": text,
        "chunk_index": 0,
    }


def _clean_contact_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"^Address:\s*", "", value, flags=re.I)
    value = value.replace(",,", ",")
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s*[-_.]\s*(?=641\s*0?42)", " - ", value)
    return value.strip(" ,.;")


def _best_contact_addresses(addresses: list[str]) -> list[str]:
    """Keep the canonical location facts short so the LLM answers faster."""
    clean = []
    for address in addresses:
        lowered = address.lower()
        if "link:" in lowered or "event" in lowered or "venue:" in lowered:
            continue
        if "kovaipudur" in lowered and "coimbatore" in lowered:
            clean.append(address)

    def score(address: str) -> tuple[int, int]:
        lowered = address.lower()
        points = 0
        if "sri krishna college of technology" in lowered:
            points += 4
        if "contact us" in lowered:
            points += 3
        if "641" in lowered:
            points += 2
        if "tamil nadu" in lowered or "tamilnadu" in lowered:
            points += 1
        return (points, -len(address))

    clean = sorted(dict.fromkeys(clean), key=score, reverse=True)
    if clean:
        return clean[:2]
    return addresses[:2]


def _direct_principal_chunks(limit: int = 3) -> list[dict]:
    """Fetch high-signal principal profile chunks, including imported PDF data."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT title, url, page_type, chunk_text
            FROM website_chunks
            WHERE (
                    lower(title) LIKE '%principal%'
                 OR lower(url) LIKE '%principal%'
                 OR lower(chunk_text) LIKE '%principal%'
            )
              AND (
                    lower(chunk_text) LIKE '%sumithra%'
                 OR lower(chunk_text) LIKE '%prof.%'
                 OR lower(chunk_text) LIKE '%dr.%'
                 OR lower(chunk_text) LIKE '%principal%'
            )
            ORDER BY
                CASE WHEN lower(title) LIKE '%sumithra%' OR lower(url) LIKE '%sumithra%' THEN 0 ELSE 1 END,
                CASE WHEN page_type = 'document' THEN 0 ELSE 1 END,
                chunk_index
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "page_type": r["page_type"],
                "chunk_text": r["chunk_text"],
                "score": 0,
                "relevance_score": 1.2,
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug(f"[RAG] Direct principal lookup failed: {e}")
        return []
    finally:
        conn.close()


def _direct_answer_if_available(question: str, primary_type: str | None, chunks: list[dict]) -> str | None:
    """Return deterministic answers for high-confidence fact lookups."""
    q = question.lower()
    if primary_type != "principal":
        return None
    if not any(word in q for word in ["who", "name", "principal", "head"]):
        return None

    text = "\n".join(chunk.get("chunk_text") or "" for chunk in chunks[:4])
    patterns = [
        r"Prof\.\s*([A-Z][A-Za-z. ]*Sumithra[A-Za-z. ]*),\s*Principal",
        r"Name of the Head of the institution\s+(Dr\.\s*Sumithra\s*M\s*G)\s+Designation\s+Principal",
        r"(Dr\.\s*Sumithra\s*M\s*G)\s+Designation\s+Principal",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip()
            if not name.lower().startswith(("dr.", "prof.")):
                name = f"Prof. {name}"
            return (
                f"The Principal of Sri Krishna College of Technology (SKCT) is "
                f"**{name}**. (Source: SumithraPrincipalSKCT.pdf)"
            )
    return None


def _extract_keywords(question: str) -> list[str]:
    """Extract meaningful keywords from question (no stop-words, ≥3 chars)."""
    tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOP_WORDS]


def _rescore_chunks(chunks: list[dict], keywords: list[str], primary_type: str | None) -> list[dict]:
    """
    Re-rank chunks by keyword hit density.
    Chunks with more keyword matches rank higher.
    """
    for chunk in chunks:
        text = (chunk.get("chunk_text") or "").lower()
        title = (chunk.get("title") or "").lower()
        url = (chunk.get("url") or "").lower()
        page_type = chunk.get("page_type") or ""
        hits = sum(1 for kw in keywords if kw in text)
        title_hits = sum(1 for kw in keywords if kw in title)
        url_hits = sum(1 for kw in keywords if kw in url)
        coverage = hits / max(1, len(keywords))
        noise_count = sum(text.count(marker) for marker in _NOISE_MARKERS)

        base = chunk.get("relevance_score", 0)
        density_bonus = min(0.35, (coverage * 0.18) + (hits * 0.025))
        source_bonus = (title_hits * 0.12) + (url_hits * 0.08)
        if primary_type and page_type == primary_type:
            source_bonus += 0.12
        if page_type == "document" and any(kw in title or kw in url for kw in keywords):
            source_bonus += 0.12
        if primary_type == "contact" and "contact-us" in url:
            source_bonus += 0.45
        if primary_type == "contact" and (
            "kovaipudur" in text
            or "coimbatore" in text
            or "address:" in text
            or "location" in title
        ):
            source_bonus += 0.35
        if primary_type == "placement" and ("placement-cell" in url or "recruiters" in url):
            source_bonus += 0.25
        if primary_type == "hostel" and "campus-tour/hostel" in url:
            source_bonus += 0.35
        if primary_type == "department" and (url.rstrip("/").endswith("/departments") or "academics/departments" in url):
            source_bonus += 0.3
        noise_penalty = min(0.35, noise_count * 0.015)
        if "sitemap" in title or url.rstrip("/").endswith("/sitemap"):
            noise_penalty += 0.45
        if "/events" in url and primary_type not in {"event", None}:
            noise_penalty += 0.25
        chunk["final_score"] = round(base + density_bonus + source_bonus - noise_penalty, 4)

    return sorted(chunks, key=lambda c: c.get("final_score", 0), reverse=True)


# ── Context building ──────────────────────────────────────────────────────────

def _build_context_block(
    question: str,
    chunks: list[dict],
    graph_ctx: dict,
) -> str:
    """Assemble the full context string to send alongside the question."""
    parts: list[str] = []

    # Website chunks
    if chunks:
        parts.append("=== WEBSITE CONTEXT ===")
        for i, chunk in enumerate(chunks[:6], 1):
            title = chunk.get("title") or "SKCT Page"
            url   = chunk.get("url") or ""
            ptype = chunk.get("page_type") or ""
            text  = _clean_chunk_for_prompt(chunk.get("chunk_text") or "", question)
            score = chunk.get("final_score", chunk.get("relevance_score", 0))
            parts.append(
                f"\n[Source {i}] {title} ({ptype})\n"
                f"URL: {url}\n"
                f"Relevance: {score:.2f}\n"
                f"{text}"
            )
        parts.append("")

    # Graph relationships
    rels = graph_ctx.get("relationships", [])
    if rels:
        parts.append("=== KNOWLEDGE GRAPH CONTEXT ===")
        for r in rels[:5]:
            src  = r.get("source_name", "?")
            rel  = r.get("relation_type", "?")
            tgt  = r.get("target_name", "?")
            parts.append(f"  {src} --[{rel}]--> {tgt}")
        parts.append("")

    if not parts:
        parts.append(
            "=== NOTICE ===\n"
            "No matching data was found in the knowledge base for this question. "
            "The website may not have been scraped yet, or the topic is not covered on skct.edu.in."
        )

    parts.append("=== END OF CONTEXT ===")
    return "\n".join(parts)


def _clean_chunk_for_prompt(text: str, question: str = "") -> str:
    """Remove high-noise boilerplate from chunk text before prompting."""
    if not text:
        return ""
    # Remove scraper artifacts
    text = re.sub(r"Structured name:\s*Sri Krishna College[^\n]*", "", text, flags=re.I)
    text = re.sub(r"Image (?:alt|title|file):\s*[^\n]+", "", text)
    text = re.sub(r"Link:\s*\S+ -> \S+\n?", "", text)
    text = re.sub(r"\[SKCT[^\]]*\]\n?", "", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) <= 1200:
        return text
    keywords = _extract_keywords(question)
    hit_positions = [
        idx for kw in keywords[:6]
        for idx in [text.lower().find(kw.lower())]
        if idx >= 0
    ]
    if hit_positions:
        start = max(0, min(hit_positions) - 240)
        end = min(len(text), start + 1200)
        if end == len(text):
            start = max(0, end - 1200)
        clipped = text[start:end].strip()
        if start > 0:
            clipped = "... " + clipped
    else:
        clipped = text[:1200].strip()
    clipped = clipped.rsplit(" ", 1)[0].strip()
    return clipped + " ..."


# ── Graph context ──────────────────────────────────────────────────────────────

def _get_graph_context(question: str) -> dict:
    """Retrieve graph relationships for key entities mentioned in the question."""
    keywords = _extract_keywords(question)
    if not keywords:
        return {"relationships": []}

    # Try the most specific keyword first; extra graph lookups add noticeable latency.
    all_rels: list[dict] = []
    seen_rels: set[str] = set()
    for kw in keywords[:1]:
        try:
            result = get_related_entities(kw, limit=5)
            for r in result.get("relationships", []):
                key = f"{r.get('source_name')}_{r.get('relation_type')}_{r.get('target_name')}"
                if key not in seen_rels:
                    seen_rels.add(key)
                    all_rels.append(r)
        except Exception as e:
            logger.debug(f"[RAG] Graph query failed for '{kw}': {e}")

    return {"relationships": all_rels[:8]}


# ── Ollama integration ────────────────────────────────────────────────────────

def _call_ollama(question: str, context_block: str) -> str:
    """
    Call Ollama synchronously, return generated answer text.
    Handles connection errors gracefully.
    """
    prompt = _build_user_prompt(question, context_block)
    ollama_url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    model = settings.OLLAMA_LLM_MODEL or settings.LLM_MODEL or "llama3.2:3b"
    options = _ollama_options(question)
    logger.info("[RAG] calling Ollama model=%s options=%s prompt_chars=%s", model, options, len(prompt))

    try:
        started_at = time.perf_counter()
        resp = requests.post(
            ollama_url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "options": options,
            },
            timeout=(10, None),
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("[RAG] Ollama completed in %.2fs", time.perf_counter() - started_at)
        return (
            data.get("message", {}).get("content")
            or data.get("response")
            or "I was unable to generate an answer. Please try again."
        )
    except requests.exceptions.ConnectTimeout:
        return "⚠️ Could not connect to the Ollama LLM service in time. Please ensure Ollama is running."
    except requests.exceptions.ConnectionError:
        return (
            "⚠️ Could not connect to the Ollama LLM service. "
            "Please ensure Ollama is running: `ollama serve`"
        )
    except Exception as e:
        logger.error(f"[RAG] Ollama error: {e}")
        return f"⚠️ An error occurred while generating the answer: {str(e)}"


def _stream_ollama(question: str, context_block: str) -> Iterator[str]:
    """Streaming Ollama call — yields tokens."""
    prompt = _build_user_prompt(question, context_block)
    ollama_url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    model = settings.OLLAMA_LLM_MODEL or settings.LLM_MODEL or "llama3.2:3b"
    options = _ollama_options(question)

    try:
        with requests.post(
            ollama_url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                "stream": True,
                "options": options,
            },
            stream=True,
            timeout=(10, None),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content") or data.get("response") or ""
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.ConnectTimeout:
        yield "\n\n⚠️ Could not connect to Ollama in time. Please ensure Ollama is running."
    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ Ollama not running. Please start it with `ollama serve`."
    except Exception as e:
        yield f"\n\n⚠️ Error: {e}"


def _build_user_prompt(question: str, context_block: str) -> str:
    extra_instruction = ""
    if _is_department_list_question(question):
        groups = _requested_program_groups(question)
        group_text = f" Include only the requested group(s): {', '.join(groups)}." if groups else ""
        extra_instruction = (
            "For this department/program list question, include every department/program "
            "listed in the SKCT Departments Summary context. Put each programme on its own "
            "top-level Markdown bullet. Do not nest, combine, summarize, or omit programmes. "
            "Keep the same UG, PG, PhD, and Other grouping when present; do not move items between groups. Do not "
            f"add contact information unless the user asks for contact details.{group_text}\n"
        )
    elif _is_event_list_question(question):
        extra_instruction = (
            "For this events question, use the SKCT Events Summary and event page context. "
            "Return a complete, well-formatted Markdown answer grouped by event type where possible. "
            "Do not stop mid-list, and do not add contact information unless asked.\n"
        )
    return (
        f"{context_block}\n\n"
        f"=== USER QUESTION ===\n{question}\n\n"
        f"{extra_instruction}"
        "Answer the question using ONLY the context above. "
        "Be precise, cite sources, and use Markdown formatting.\n\n"
        "ANSWER:"
    )


def _ollama_options(question: str) -> dict:
    if _is_department_list_question(question) or _is_event_list_question(question):
        return {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_ctx": 4096,
            "num_predict": 2048,
        }
    return {
        "temperature": 0.1,
        "top_p": 0.9,
        "num_ctx": 3072,
        "num_predict": 1024,
    }


def _extract_sources(chunks: list[dict]) -> list[dict]:
    """Build a deduplicated source list from retrieved chunks."""
    seen_urls: set[str] = set()
    sources: list[dict] = []
    for chunk in chunks:
        url = chunk.get("url") or ""
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append({
                "title":     chunk.get("title") or "SKCT Page",
                "url":       url,
                "page_type": chunk.get("page_type") or "general",
                "score":     round(chunk.get("final_score", chunk.get("relevance_score", 0)), 3),
            })
    return sources[:8]


# ── Contact direct scan (fallback) ──────────────────────────────────────────────
def _contact_direct_scan() -> list[dict]:
    """Direct LIKE scan for contact details when FTS may miss them."""
    from backend.app.graph_sqlite.db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT title, url, page_type, chunk_text
            FROM website_chunks
            WHERE page_type = 'contact'
               OR chunk_text LIKE '%phone%'
               OR chunk_text LIKE '%email%'
               OR chunk_text LIKE '%address%'
               OR chunk_text LIKE '%coimbatore%'
            LIMIT 6
        """).fetchall()
        return [
            {
                "title": r["title"], "url": r["url"],
                "page_type": r["page_type"], "chunk_text": r["chunk_text"],
                "relevance_score": 0.5, "final_score": 0.5,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"[RAG] Contact scan failed: {e}")
        return []
    finally:
        conn.close()
