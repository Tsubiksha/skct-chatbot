"""
graph_router.py — Intent classification for Graph RAG questions.

Uses keyword/rule-based routing — no LLM needed for this step.
Classifies questions into one of five categories so the answer service
knows which retrieval paths to activate.
"""

import re

# ---------------------------------------------------------------------------
# Keyword sets per category
# ---------------------------------------------------------------------------

_ACADEMIC_KEYWORDS = {
    "marks", "score", "scored", "grade", "grades", "result", "results",
    "semester", "sem", "cgpa", "gpa", "pass", "fail", "failed", "arrear",
    "arrears", "highest", "lowest", "average", "topper", "rank",
    "class average", "subject", "subjects", "performance", "attendance",
    "percentage", "percentage marks", "internal", "external", "total marks",
    "my marks", "my cgpa", "my gpa", "my result", "my grade", "my semester",
    "my performance", "academic", "progress", "what did i score",
    "how many subjects", "how many failed",
    # Batch/class queries
    "top student", "best student", "who scored highest", "who is top",
    "batch topper", "class topper", "who got", "who has highest",
    "grade distribution", "pass percentage", "batch size", "total students",
}

_WEBSITE_KEYWORDS = {
    "college", "website", "official", "skct", "department", "faculty",
    "placement", "placements", "hod", "head of department", "principal",
    "dean", "contact", "address", "phone", "email", "rule", "rules",
    "regulation", "regulations", "policy", "event", "events", "announcement",
    "announcements", "scholarship", "hostel", "library", "lab", "sports",
    "about", "vision", "mission", "history", "establishment", "established",
    "estabished", "founded", "started", "since", "accreditation",
    "naac", "nba", "infrastructure", "campus",
    "course", "courses", "program", "programs", "programme", "programmes",
    "offered", "courses offered", "branches", "ug", "pg", "undergraduate",
    "postgraduate", "b.tech", "b.e", "m.e", "mba",
    "tnea", "tnea code", "code", "college code",
}

_GRAPH_KEYWORDS = {
    "related", "connected", "belongs", "belongs to", "teaches", "taught",
    "studied", "relationship", "relationships", "graph", "linked", "link",
    "who taught", "who studies", "which students", "which department",
    "connected to", "what is connected", "show relations",
}

_HYBRID_KEYWORDS = {
    "eligible", "eligibility", "placement eligibility", "compare",
    "according to", "based on", "based on my", "based on college",
    "college rules", "what should i improve", "improvement",
    "placement criteria", "can i apply", "am i eligible",
    "my cgpa and", "my marks and",
}


def _count_hits(text: str, keyword_set: set) -> int:
    """Count how many keywords from the set appear in text."""
    text_lower = text.lower()
    return sum(1 for kw in keyword_set if kw in text_lower)


# ---------------------------------------------------------------------------
# Public router
# ---------------------------------------------------------------------------

RouteType = str  # one of the five categories below

ROUTE_ACADEMIC_SQL    = "academic_sql"
ROUTE_WEBSITE_FTS     = "website_fts"
ROUTE_GRAPH_REL       = "graph_relationship"
ROUTE_HYBRID          = "hybrid"
ROUTE_GENERAL         = "general_graph_chat"


def route_question(question: str) -> RouteType:
    """
    Classify a question into a retrieval route.
    Returns one of the five ROUTE_* constants.
    """
    q = question.strip()

    academic_score = _count_hits(q, _ACADEMIC_KEYWORDS)
    website_score  = _count_hits(q, _WEBSITE_KEYWORDS)
    graph_score    = _count_hits(q, _GRAPH_KEYWORDS)
    hybrid_score   = _count_hits(q, _HYBRID_KEYWORDS)

    # Hybrid wins if it has any hits AND at least one of academic/website also fires
    if hybrid_score >= 1 and (academic_score >= 1 or website_score >= 1):
        return ROUTE_HYBRID

    # Pick the highest-scoring route
    scores = {
        ROUTE_ACADEMIC_SQL: academic_score,
        ROUTE_WEBSITE_FTS:  website_score,
        ROUTE_GRAPH_REL:    graph_score,
    }
    best_route, best_score = max(scores.items(), key=lambda x: x[1])

    if best_score == 0:
        return ROUTE_GENERAL

    return best_route


def explain_route(route: RouteType) -> str:
    """Human-readable description of the route."""
    return {
        ROUTE_ACADEMIC_SQL: "Academic SQL — querying Excel mark/result data",
        ROUTE_WEBSITE_FTS:  "Website FTS — searching scraped college website chunks",
        ROUTE_GRAPH_REL:    "Graph Relationship — traversing entity relationships",
        ROUTE_HYBRID:       "Hybrid — combining academic data + college website info",
        ROUTE_GENERAL:      "General Graph Chat — open-ended question",
    }.get(route, route)
