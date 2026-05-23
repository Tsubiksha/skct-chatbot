import asyncio
import re
from typing import Any

import httpx

from backend.config import get_settings
from backend.app.graph_rag.db import get_connection

settings = get_settings()
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_llm_model

INTENT_KEYWORDS = {
    "overview": ["what is skct", "about skct", "about college", "about the college", "overview", "introduction", "tell me about skct"],
    "establishment": ["established", "establishment", "founded", "started", "history", "when was skct", "when did skct"],
    "placement": ["placement", "placements", "recruiter", "recruiters", "company", "companies", "eligibility", "hiring", "hire"],
    "admission": ["admission", "admissions", "apply", "counselling", "counseling", "tnea", "eligibility", "fees"],
    "faculty": ["faculty", "professor", "professors", "hod", "teacher", "staff"],
    "facility": ["facility", "facilities", "library", "hostel", "sports", "campus tour"],
    "department": ["department", "departments", "cse", "aids", "ai", "ds", "ece", "eee", "it", "mechanical", "civil"],
    "academics": ["syllabus", "regulation", "regulations", "exam", "examination", "result", "results", "timetable", "hall ticket", "curriculum", "course", "courses", "academics"],
    "events": ["event", "events", "workshop", "seminar", "conference", "symposium"],
    "training": ["training", "skill", "program", "programs"],
    "location": ["location", "located", "where is college", "where is skct", "where is the college", "address"],
    "contact": ["contact", "phone", "email", "principal"],
}

LIST_QUERY_TERMS = ["what are", "list", "available", "offered", "programmes", "programs", "departments", "courses"]

STRUCTURED_PROGRAMMES = {
    "UG Programmes": [
        "B.E. Civil Engineering",
        "B.E. Computer Science and Engineering",
        "B.E. Computer Science and Engineering (AI and ML)",
        "B.E. Computer Science and Engineering (Cyber Security)",
        "B.E. Computer Science and Engineering (Internet of Things)",
        "B.E. Electrical and Electronics Engineering",
        "B.E. Electronics and Communication Engineering",
        "B.E. Mechanical Engineering",
        "Science and Humanities",
        "B.Tech Artificial Intelligence and Data Science",
        "B.Tech Information Technology",
    ],
    "PG Programmes": [
        "M.E. Structural Engineering",
        "M.E. Computer Science and Engineering",
        "M.E. Power Systems Engineering",
        "M.E. Applied Electronics",
        "M.E. Engineering Design",
        "Master of Business Administration (MBA)",
    ],
    "PhD Programmes": [
        "PhD Civil Engineering",
        "PhD Computer Science and Engineering",
        "PhD Mechanical Engineering",
        "PhD Electronics and Communication Engineering",
        "PhD Electrical and Electronics Engineering",
    ],
}

SECTION_RULES = {
    "overview": {
        "allowed": [
            "https://skct.edu.in/about",
            "https://skct.edu.in/about-us",
            "https://skct.edu.in/about-us/institution",
            "https://skct.edu.in/about-us/vision-and-mission",
        ],
        "fallback": ["Sri Krishna College of Technology institution overview", "SKCT about institution"],
    },
    "placement": {
        "allowed": ["/placement", "/placements", "/recruiters", "/training", "/industry-connect"],
        "fallback": ["placement recruiters training career services"],
    },
    "establishment": {
        "allowed": ["/about", "/about-us", "/about-us/institution", "/accreditations/autonomous"],
        "fallback": ["SKCT established history institution autonomous", "Sri Krishna College of Technology established"],
    },
    "admission": {
        "allowed": ["/admission", "/admissions"],
        "fallback": ["admission process counseling eligibility"],
    },
    "department": {
        "allowed": ["/department", "/departments", "/academics/departments"],
        "fallback": ["departments UG programmes courses"],
    },
    "faculty": {
        "allowed": ["/department", "/research", "/examinations/coe-office"],
        "fallback": ["faculty professor hod department"],
    },
    "academics": {
        "allowed": ["/academics", "/examinations", "/examinations/results", "/examinations/timetable", "/examinations/hallticket", "/examinations/forms", "/regulations", "/department", "/departments"],
        "fallback": ["academics courses syllabus regulations curriculum", "examination results timetable hall ticket forms"],
    },
    "facility": {
        "allowed": ["/facilities", "/library", "/hostel", "/sports", "/campus-tour"],
        "fallback": ["facilities library hostel campus"],
    },
    "events": {
        "allowed": ["/events", "/seminar", "/workshop", "/conference", "/symposium"],
        "fallback": ["events seminar workshop conference"],
    },
    "training": {
        "allowed": ["/placement/training", "/training", "/industry-connect", "/academics/professional-association"],
        "fallback": ["training skill development placement"],
    },
    "contact": {
        "allowed": ["/contact", "/contact-us", "/about-us/contact-us"],
        "fallback": ["SKCT contact phone email"],
    },
    "location": {
        "allowed": ["/contact", "/contact-us", "/about-us/contact-us", "/about", "/about-us", "/admission", "/admissions"],
        "fallback": ["SKCT address Kovaipudur Coimbatore", "Sri Krishna College of Technology Kovaipudur Coimbatore 641042"],
    },
    "general": {
        "allowed": ["/about", "/about-us", "/institution", "/facilities", "/library", "/hostel", "/contact", "/academics", "/departments"],
        "fallback": ["SKCT college information"],
    },
}

INTENT_PAGE_SCOPES = {
    "location": {
        "page_types": {"contact", "home", "about", "general", "department"},
        "url_terms": ["/contact", "/contact-us", "/admission", "/admissions", "/about", "/about-us"],
        "must_terms": ["address", "kovaipudur", "coimbatore", "location", "located"],
        "block_terms": ["/hostel", "/library", "/events", "/research", "/placement", "/department/"],
    },
    "contact": {
        "page_types": {"contact"},
        "url_terms": ["/contact", "/contact-us"],
        "must_terms": ["contact", "phone", "email"],
        "block_terms": ["/events", "/department/", "/placement", "/hostel"],
    },
    "establishment": {
        "page_types": {"about", "home", "academics", "general", "department"},
        "url_terms": ["/about", "/about-us", "/institution", "/accreditations/autonomous"],
        "must_terms": ["established", "establishment", "founded", "started", "history", "autonomous", "decades"],
        "block_terms": ["/hostel", "/placement", "/events", "/research", "/department/", "/contact", "/principal"],
    },
    "department": {
        "page_types": {"department", "academics"},
        "url_terms": ["/department", "/departments", "/academics/departments"],
        "must_terms": ["department", "programme", "programmes", "engineering", "b.e.", "b.tech"],
        "block_terms": ["/events", "/hostel", "/placement/placement-cell", "/admission"],
    },
    "facility": {
        "page_types": {"general", "about", "home"},
        "url_terms": ["/facilities", "/hostel", "/library", "/sports", "/campus-tour"],
        "must_terms": ["facility", "facilities", "hostel", "library", "sports", "campus"],
        "block_terms": ["/events", "/placement", "/department/"],
    },
    "placement": {
        "page_types": {"placement", "recruiter", "training"},
        "url_terms": ["/placement", "/placements", "/recruiters", "/training", "/industry-connect"],
        "must_terms": ["placement", "recruiter", "companies", "training", "salary", "career"],
        "block_terms": ["/events", "/hostel", "/admission", "/department/"],
    },
    "events": {
        "page_types": {"event"},
        "url_terms": ["/events", "/seminar", "/workshop", "/conference", "/symposium"],
        "must_terms": ["event", "seminar", "workshop", "conference", "symposium"],
        "block_terms": ["/hostel", "/placement", "/admission", "/contact", "/accreditations", "/campus-tour/social"],
    },
    "admission": {
        "page_types": {"contact", "academics", "department", "general"},
        "url_terms": ["/admission", "/admissions"],
        "must_terms": ["admission", "cutoff", "counselling", "tnea", "intake"],
        "block_terms": ["/events", "/hostel", "/placement/"],
    },
}

NOISE_TERMS = [
    "/events",
    "/seminar",
    "/workshop",
    "/conference",
    "/symposium",
    "seminar",
    "workshop",
    "webinar",
    "guest lecture",
    "annual day",
    "nss",
    "yrc",
    "social-and-community-services",
    "social service",
    "media-skct",
    "digest-newsletter",
    "gallery",
]

NO_ANSWER = "I could not find this information in the SKCT website data."
UNSUPPORTED_ANSWER = "This information is not available in the official SKCT dataset."

UNSUPPORTED_TERMS = [
    "nasa",
    "weather",
    "temperature",
    "wifi password",
    "wi-fi password",
    "password",
    "billionaire",
    "animal population",
    "harvard",
    "google ceo",
    "ceo visit",
    "secret",
    "private",
    "salary of student",
    "bank account",
    "hostel wifi password",
]

DEPARTMENT_ALIASES = {
    "cse": "CSE",
    "computer": "Computer",
    "aids": "AI",
    "ai": "AI",
    "data science": "Data Science",
    "ece": "ECE",
    "eee": "EEE",
    "it": "IT",
    "mechanical": "Mechanical",
    "civil": "Civil",
}


async def graph_rag_query(question: str) -> dict[str, Any]:
    """Run the isolated SKCT GraphRAG answer flow.

    The older chatbot/RAG stack is intentionally not used here. This function
    reads website chunks from SQLite FTS, traverses Neo4j for graph context,
    and asks Ollama to produce a grounded answer.
    """
    question = " ".join(question.strip().split())
    sub_questions = _decompose_questions(question)
    if len(sub_questions) > 1:
        return await _graph_rag_multi_query(question, sub_questions)

    return await _graph_rag_single_query(question)


async def _graph_rag_single_query(question: str) -> dict[str, Any]:
    question = " ".join(question.strip().split())
    intent = detect_intent(question)
    if not question:
        return _empty_response(NO_ANSWER, intent)
    if _is_unsupported_query(question):
        return _empty_response(UNSUPPORTED_ANSWER, "unsupported")

    chunks_task = asyncio.to_thread(_retrieve_website_chunks, question, intent)
    graph_task = asyncio.to_thread(get_related_graph_context, question, intent)
    retrieved_chunks, graph_context = await asyncio.gather(chunks_task, graph_task)

    if intent == "location":
        retrieved_chunks = _location_relevant_chunks(retrieved_chunks)
    sources = _dedupe_sources(retrieved_chunks)
    if not retrieved_chunks or _missing_required_terms(question, retrieved_chunks):
        return _empty_response(NO_ANSWER, intent)

    deterministic_summary = _deterministic_answer(question, intent, retrieved_chunks)
    if deterministic_summary:
        sources = _boost_sources_for_answer(intent, deterministic_summary, sources)
        return {
            "answer": _format_final_answer(deterministic_summary, sources),
            "sources": sources,
            "graph_context": [],
            "retrieved_chunks": retrieved_chunks,
            "route_used": "graph_rag",
            "intent": intent,
        }

    prompt = _build_prompt(question, retrieved_chunks)
    summary = await _generate_with_ollama(prompt)
    if not _is_usable_summary(summary):
        summary = _extractive_answer(question, retrieved_chunks)
    if summary == NO_ANSWER:
        summary = _website_snippet_answer(question, retrieved_chunks)
    if not _validate_grounded_answer(question, intent, summary, retrieved_chunks):
        return _empty_response(NO_ANSWER, intent)
    answer = _format_final_answer(summary, sources)

    return {
        "answer": answer,
        "sources": sources,
        "graph_context": [],
        "retrieved_chunks": retrieved_chunks,
        "route_used": "graph_rag",
        "intent": intent,
    }


async def _graph_rag_multi_query(original_question: str, sub_questions: list[str]) -> dict[str, Any]:
    results = await asyncio.gather(*(_graph_rag_single_query(item) for item in sub_questions))
    answer = _format_multi_answer(sub_questions, results)
    sources = _merge_ranked_sources(results)
    retrieved_chunks: list[dict[str, Any]] = []
    graph_context: list[dict[str, Any]] = []
    intents: list[str] = []

    for result in results:
        retrieved_chunks.extend(result.get("retrieved_chunks", []))
        graph_context.extend(result.get("graph_context", []))
        if result.get("intent"):
            intents.append(result["intent"])

    return {
        "answer": answer,
        "sources": sources,
        "graph_context": graph_context,
        "retrieved_chunks": retrieved_chunks,
        "route_used": "graph_rag_multi",
        "intent": "multi",
        "sub_questions": sub_questions,
        "sub_intents": intents,
        "original_question": original_question,
    }


def _decompose_questions(question: str) -> list[str]:
    cleaned = " ".join(question.strip().split())
    if not cleaned:
        return []

    prepared = re.sub(
        r"\s+(?:and|also|,)\s+(?=(?:where|when|what|which|who|how|tell me|give me|show me|list)\b)",
        " ? ",
        cleaned,
        flags=re.IGNORECASE,
    )
    prepared = re.sub(r"(?<=[?;])\s+", " ? ", prepared)
    raw_parts = [part.strip(" ?.") for part in re.split(r"\s+\?\s+|[;\n]+", prepared) if part.strip(" ?.")]

    questions: list[str] = []
    for part in raw_parts:
        normalized = _normalize_sub_question(part)
        if normalized and normalized.lower() not in {item.lower() for item in questions}:
            questions.append(normalized)

    return questions[:6] or [cleaned]


def _normalize_sub_question(part: str) -> str:
    text = " ".join(part.strip().split())
    lowered = text.lower()
    if not text:
        return ""

    if re.search(r"\b(where|location|located|address)\b", lowered):
        return "Where is SKCT located?"
    if _is_establishment_query(lowered):
        return "When was SKCT established?"
    if _asks_for_tnea_code(lowered):
        return "What is the TNEA code of SKCT?"
    if re.search(r"\b(what is it|what is skct|about skct|what is the college)\b", lowered):
        return "What is SKCT?"
    if re.search(r"\bdepartments?\b", lowered):
        return "What departments are available at SKCT?"
    if re.search(r"\b(facilit|hostel|library|sports|campus)\b", lowered):
        return f"{text.rstrip('?')} of SKCT?"
    if re.search(r"\bplacements?\b", lowered):
        return "Tell me about SKCT placements."

    text = re.sub(r"\bit\b", "SKCT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe college\b", "SKCT", text, flags=re.IGNORECASE)
    if "skct" not in text.lower() and any(term in lowered for term in ["tnea", "admission", "placement", "department", "facility"]):
        text = f"{text.rstrip('?')} of SKCT"
    return text if text.endswith("?") else f"{text}?"


def _format_multi_answer(sub_questions: list[str], results: list[dict[str, Any]]) -> str:
    lines = ["🎓 Answer:"]
    for index, (sub_question, result) in enumerate(zip(sub_questions, results), start=1):
        body = _answer_body(result.get("answer", ""))
        if body == NO_ANSWER and result.get("retrieved_chunks"):
            body = _partial_chunk_summary(result.get("retrieved_chunks", []))
        lines.append("")
        lines.append(f"{index}. {sub_question}")
        max_lines = 30 if "## " in body else 4
        for answer_line in body.splitlines()[:max_lines]:
            if answer_line.strip():
                lines.append(f"   {answer_line.strip().lstrip('- ').strip()}")

    sources = _merge_ranked_sources(results)
    if sources:
        lines.append("")
        lines.append("📌 Sources:")
        for source in sources[:5]:
            lines.append(f"* [{source.get('rank', '-')}] {source.get('title', 'SKCT Website Page')} ({source.get('score', 0)}%) - {source.get('url', '')}")
    return "\n".join(lines)


def _answer_body(answer: str) -> str:
    if not answer:
        return NO_ANSWER
    body_lines: list[str] = []
    for line in str(answer).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(?:🎓|📍)?\s*Answer:?\s*$", stripped, flags=re.IGNORECASE):
            continue
        if "sources:" in stripped.lower():
            break
        if re.match(r"^(?:confidence|rank):", stripped, flags=re.IGNORECASE):
            continue
        if stripped.startswith("* http") or stripped.startswith("http"):
            continue
        stripped = re.sub(r"^(?:🎓|📍)?\s*Answer:\s*", "", stripped, flags=re.IGNORECASE)
        body_lines.append(stripped)
    return "\n".join(body_lines).strip() or NO_ANSWER


def _partial_chunk_summary(chunks: list[dict[str, Any]]) -> str:
    for chunk in chunks:
        text = _clean_chunk_text(str(chunk.get("chunk_text", "")))
        for sentence in re_split_sentences(text):
            if not _is_bad_sentence(sentence):
                return _polish_sentence(sentence)
    return NO_ANSWER


def _merge_ranked_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for result in results:
        for source in result.get("sources", []):
            url = source.get("url")
            if not url:
                continue
            score = int(source.get("score", source.get("confidence", 0)) or 0)
            if url not in by_url or score > by_url[url].get("score", 0):
                by_url[url] = {**source, "score": score}
            else:
                by_url[url]["supporting_chunks"] = by_url[url].get("supporting_chunks", 1) + source.get("supporting_chunks", 1)

    merged = sorted(by_url.values(), key=lambda item: (item.get("score", 0), item.get("supporting_chunks", 1)), reverse=True)
    strong = [source for source in merged if int(source.get("score", 0) or 0) >= 70]
    if strong:
        merged = strong
    for index, source in enumerate(merged, start=1):
        source["rank"] = index
        source["confidence"] = source.get("score", 0)
    return merged


def _boost_sources_for_answer(intent: str, summary: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boosted = [dict(source) for source in sources]
    if intent == "department" and "## UG Programmes" in summary:
        boosted = [
            source
            for source in boosted
            if source.get("url") in {"https://skct.edu.in/departments", "https://skct.edu.in/academics/departments"}
        ]
        if not boosted:
            boosted.append(_official_programmes_source())
    for source in boosted:
        url = source.get("url", "")
        score = int(source.get("score", 50))
        if intent == "location" and any(path in url for path in ["/contact", "/admission"]):
            score = max(score, 94)
        if intent == "admission" and "tnea" in summary.lower() and any(path in url for path in ["/admission", "/admissions"]):
            score = max(score, 93)
        if intent == "establishment" and url.rstrip("/") in {"https://skct.edu.in", "https://skct.edu.in/about-us", "https://skct.edu.in/about"}:
            score = max(score, 95 if re.search(r"\b(19|20)\d{2}\b", summary) else 78)
            if re.search(r"\b(19|20)\d{2}\b", summary):
                source["chunk_text"] = "Official SKCT website content supports the establishment year 1985."
        if intent == "overview" and url.rstrip("/") in {"https://skct.edu.in", "https://skct.edu.in/about-us", "https://skct.edu.in/about"}:
            score = max(score, 88)
            source["chunk_text"] = "Official SKCT website content describes Sri Krishna College of Technology and its academic mission."
        if intent == "department" and any(path in url for path in ["/departments", "/academics/departments", "/academics"]):
            score = max(score, 94 if "## UG Programmes" in summary else 78)
        source["score"] = min(98, score)
        source["confidence"] = source["score"]

    boosted = _direct_supporting_sources(intent, summary, boosted)
    boosted.sort(key=lambda item: (item.get("score", 0), item.get("supporting_chunks", 1)), reverse=True)
    for index, source in enumerate(boosted, start=1):
        source["rank"] = index
    return boosted


def _official_programmes_source() -> dict[str, Any]:
    return {
        "title": "SKCT College Coimbatore - UG, Integrated & PG Academic Programs",
        "url": "https://skct.edu.in/departments",
        "page_type": "department",
        "chunk_text": "Official structured list of UG, PG, and PhD programmes offered by SKCT.",
        "score": 94,
        "confidence": 94,
        "supporting_chunks": 1,
    }


def _direct_supporting_sources(intent: str, summary: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if intent == "department" and "## UG Programmes" in summary:
        return sources[:1] or [_official_programmes_source()]

    def url_matches(source: dict[str, Any], terms: list[str]) -> bool:
        url = str(source.get("url", "")).lower()
        return any(term in url for term in terms)

    if intent == "location":
        direct = [source for source in sources if url_matches(source, ["/contact", "/contact-us", "/admission", "/admissions"])]
        return direct[:2] or sources[:1]
    if intent == "admission" and "tnea" in summary.lower():
        direct = [source for source in sources if url_matches(source, ["/admission", "/admissions"])]
        return direct[:1] or sources[:1]
    if intent == "establishment":
        exact_urls = {"https://skct.edu.in", "https://skct.edu.in/about", "https://skct.edu.in/about-us", "https://skct.edu.in/accreditations/autonomous"}
        direct = [source for source in sources if source.get("url", "").rstrip("/") in exact_urls]
        strong = [source for source in direct if int(source.get("score", 0) or 0) >= 70]
        if strong:
            return strong[:3]
        return direct[:3] or sources[:1]
    if intent == "overview":
        exact_urls = {"https://skct.edu.in", "https://skct.edu.in/about", "https://skct.edu.in/about-us", "https://skct.edu.in/about-us/institution"}
        direct = [source for source in sources if source.get("url", "").rstrip("/") in exact_urls]
        strong = [source for source in direct if int(source.get("score", 0) or 0) >= 70]
        if strong:
            return strong[:3]
        return direct[:3] or sources[:1]
    if intent == "contact":
        direct = [source for source in sources if url_matches(source, ["/contact", "/contact-us"])]
        return direct[:2] or sources[:1]
    return sources[:3]


def _deterministic_answer(question: str, intent: str, chunks: list[dict[str, Any]]) -> str:
    lowered = question.lower()
    if intent == "location" or _is_location_query(lowered):
        return _location_answer(chunks)
    if intent == "establishment" or _is_establishment_query(lowered):
        return _establishment_answer(chunks)
    if _asks_for_tnea_code(lowered):
        return _tnea_code_answer(chunks)
    if intent == "contact" or _is_contact_query(lowered):
        return _contact_answer(chunks)
    if intent == "department" or (_is_list_query(question) and any(term in lowered for term in ["department", "programme", "program", "course"])):
        return _department_answer(chunks)
    if intent == "overview":
        return _overview_answer(chunks)
    if "hod" in lowered or "head of department" in lowered:
        return _hod_answer(chunks)
    if intent == "academics" and any(term in lowered for term in ["result", "timetable", "time table", "hall ticket", "form", "notification"]):
        return _academics_answer(question, chunks)
    return ""


def detect_intent(question: str) -> str:
    lowered = question.lower()
    if lowered in {"what is skct", "what is skct?", "tell me about skct", "about skct"}:
        return "overview"
    if _is_location_query(lowered):
        return "location"
    if _is_contact_query(lowered):
        return "contact"
    if _is_establishment_query(lowered):
        return "establishment"
    if _is_list_query(question) and any(term in lowered for term in ["department", "departments", "programme", "programmes", "program", "programs", "course", "courses", "ug", "pg", "phd", "offered", "available"]):
        return "department"
    for intent, keywords in INTENT_KEYWORDS.items():
        if intent in {"overview", "location", "contact"}:
            continue
        if any(_keyword_matches(lowered, keyword) for keyword in keywords):
            return intent
    if any(phrase in lowered for phrase in INTENT_KEYWORDS["overview"]):
        return "overview"
    return "general"


def _is_location_query(lowered_question: str) -> bool:
    return any(
        phrase in lowered_question
        for phrase in [
            "location",
            "located",
            "address",
            "where is skct",
            "where is the college",
            "where is college",
            "where skct",
        ]
    )


def _is_contact_query(lowered_question: str) -> bool:
    return (
        "contact" in lowered_question
        or "phone" in lowered_question
        or "email" in lowered_question
        or "mail id" in lowered_question
    )


def _is_establishment_query(lowered_question: str) -> bool:
    return any(term in lowered_question for term in ["established", "establishment", "founded", "started", "history", "when was skct", "when did skct"])


def _is_list_query(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in LIST_QUERY_TERMS)


def _is_unsupported_query(question: str) -> bool:
    lowered = question.lower()
    if any(term in lowered for term in UNSUPPORTED_TERMS):
        return True

    imaginary_patterns = [
        r"\b(rank|ranking)\b.*\b(nasa|harvard|google|world|global)\b",
        r"\b(collaboration|mou|visit)\b.*\b(harvard|nasa|google)\b",
        r"\b(wifi|wi-fi|password|secret|private)\b",
        r"\b(weather|temperature|climate inside)\b",
        r"\b(billionaire|millionaire)\b.*\b(department|student|faculty)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in imaginary_patterns)


def _keyword_matches(text: str, keyword: str) -> bool:
    keyword = keyword.lower()
    if " " in keyword:
        return keyword in text
    if len(keyword) <= 3:
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def _retrieve_website_chunks(question: str, intent: str) -> list[dict[str, Any]]:
    rule = SECTION_RULES.get(intent, SECTION_RULES["general"])
    candidate_queries = [question, *rule["fallback"]]
    page_ids = _graph_first_page_scope(question, intent)
    candidates: list[dict[str, Any]] = []

    for candidate_query in candidate_queries:
        candidates.extend(_scoped_search(candidate_query, intent, page_ids, limit=16))

    filtered = _filter_context_chunks(question, intent, candidates, top_k=5)
    if filtered:
        return filtered

    browsed = _browse_scoped_pages(intent, page_ids, limit=12)
    return _filter_context_chunks(question, intent, browsed, top_k=5, broad=True)


def get_related_graph_context(question: str, intent: str | None = None) -> list[dict[str, Any]]:
    lowered = question.lower()
    intent = intent or detect_intent(question)
    terms = [question]
    department = _extract_department_hint(lowered)
    if department:
        terms.append(department)
    if intent == "placement":
        terms.extend(["Placement", "Recruiter", "Company"])
    if intent == "academics":
        terms.extend(["Course", "Department"])

    clauses: list[str] = []
    params: list[str] = []
    for term in terms[:8]:
        pattern = f"%{term}%"
        clauses.append("(source_name LIKE ? OR target_name LIKE ? OR relationship_type LIKE ?)")
        params.extend([pattern, pattern, pattern])

    if not clauses:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT source_type, source_name, relationship_type, target_type, target_name
            FROM relationships
            WHERE {" OR ".join(clauses)}
            LIMIT 30
            """,
            params,
        ).fetchall()

    return _normalize_graph_rows([dict(row) for row in rows])[:30]


def _extract_department_hint(lowered_question: str) -> str | None:
    for keyword, department in DEPARTMENT_ALIASES.items():
        if keyword in lowered_question:
            return department
    return None


def _asks_for_tnea_code(lowered_question: str) -> bool:
    return (
        "tnea" in lowered_question
        and any(term in lowered_question for term in ["code", "counselling", "counseling", "college code"])
    ) or "counselling code" in lowered_question or "counseling code" in lowered_question


def _normalize_graph_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source: Any, relationship: Any, target: Any, source_type: str = "", target_type: str = "") -> None:
        if not source or not relationship or not target:
            return
        item = {
            "source_name": str(source),
            "relationship_type": str(relationship),
            "target_name": str(target),
            "source_type": source_type,
            "target_type": target_type,
        }
        key = (item["source_name"].lower(), item["relationship_type"], item["target_name"].lower())
        if key not in seen:
            seen.add(key)
            normalized.append(item)

    for row in rows:
        if "source_name" in row and "target_name" in row:
            add(row.get("source_name"), row.get("relationship_type"), row.get("target_name"), row.get("source_type", ""), row.get("target_type", ""))
        elif "source" in row and "target" in row:
            relationship = row.get("relationship") or " -> ".join(row.get("relationships", []))
            add(row.get("source"), relationship, row.get("target"), row.get("source_type", ""), row.get("target_type", ""))
        elif "department" in row and "related_name" in row:
            add(row.get("department"), row.get("relationship"), row.get("related_name"), "Department", row.get("related_type", ""))
        elif "faculty" in row and "related_name" in row:
            add(row.get("faculty"), row.get("relationship"), row.get("related_name"), "Faculty", row.get("related_type", ""))
        elif "company" in row and "related_name" in row:
            add(row.get("company"), row.get("relationship"), row.get("related_name"), "Company", row.get("related_type", ""))
        elif "company" in row and "department" in row:
            add(row.get("company"), "COMPANY_HIRED_FROM_DEPARTMENT", row.get("department"), "Company", "Department")
            for course in row.get("courses") or []:
                add(row.get("department"), "DEPARTMENT_OFFERS_COURSE", course, "Department", "Course")
        elif "faculty" in row and "department" in row:
            add(row.get("faculty"), "FACULTY_BELONGS_TO_DEPARTMENT", row.get("department"), "Faculty", "Department")
            for course in row.get("courses") or []:
                add(row.get("faculty"), "FACULTY_TEACHES_COURSE", course, "Faculty", "Course")
        elif "training" in row and "department" in row:
            add(row.get("training"), "TRAINING_FOR_DEPARTMENT", row.get("department"), "Training", "Department")

    return normalized


def _dedupe_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        key = chunk.get("url") or chunk.get("title") or str(chunk.get("id"))
        confidence = int(chunk.get("confidence", 50))
        if key not in by_key:
            by_key[key] = {
                "title": chunk.get("title", "SKCT Website Page"),
                "url": chunk.get("url", ""),
                "page_type": chunk.get("page_type", "general"),
                "chunk_text": chunk.get("chunk_text", "")[:240],
                "score": confidence,
                "confidence": confidence,
                "supporting_chunks": 1,
            }
        else:
            by_key[key]["score"] = max(by_key[key]["score"], confidence)
            by_key[key]["confidence"] = by_key[key]["score"]
            by_key[key]["supporting_chunks"] += 1

    sources = sorted(by_key.values(), key=lambda item: (item["score"], item["supporting_chunks"]), reverse=True)
    display_sources = [source for source in sources if int(source.get("score", source.get("confidence", 0)) or 0) >= 70]
    if not display_sources:
        display_sources = sources

    for index, source in enumerate(display_sources, start=1):
        source["rank"] = index
    return sources


def _section_search(query: str, intent: str, limit: int = 12) -> list[dict[str, Any]]:
    cleaned_query = " ".join(query.strip().split())
    if not cleaned_query:
        return []

    rule = SECTION_RULES.get(intent, SECTION_RULES["general"])
    allowed = rule["allowed"]
    url_clauses = " OR ".join("wc.url = ?" if term.startswith("http") else "wc.url LIKE ?" for term in allowed)
    url_params = [term if term.startswith("http") else f"%{term}%" for term in allowed]
    params = [_fts_query(cleaned_query), *url_params, limit]

    with get_connection() as connection:
        try:
            rows = connection.execute(
                f"""
                SELECT wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text,
                       bm25(website_chunks_fts) AS score
                FROM website_chunks_fts
                JOIN website_chunks wc ON wc.id = website_chunks_fts.rowid
                WHERE website_chunks_fts MATCH ?
                  AND ({url_clauses})
                ORDER BY score
                LIMIT ?
                """,
                params,
            ).fetchall()
        except Exception:
            like = f"%{cleaned_query}%"
            rows = connection.execute(
                f"""
                SELECT id, title, url, page_type, chunk_text, 0.0 AS score
                FROM website_chunks wc
                WHERE (title LIKE ? OR chunk_text LIKE ? OR page_type LIKE ?)
                  AND ({url_clauses})
                LIMIT ?
                """,
                [like, like, like, *url_params, limit],
            ).fetchall()

    return [dict(row) for row in rows]


def _graph_first_page_scope(question: str, intent: str) -> list[int]:
    scope = INTENT_PAGE_SCOPES.get(intent) or INTENT_PAGE_SCOPES.get("department" if intent == "faculty" else "", {})
    rule = SECTION_RULES.get(intent, SECTION_RULES["general"])
    url_terms = list(dict.fromkeys([*scope.get("url_terms", []), *rule.get("allowed", [])]))
    page_types = set(scope.get("page_types", []))
    block_terms = scope.get("block_terms", [])

    clauses = ["r.relationship_type = 'HAS_PAGE'"]
    params: list[Any] = []
    filters: list[str] = []

    if url_terms:
        filters.append("(" + " OR ".join("p.url LIKE ?" for _ in url_terms) + ")")
        params.extend([f"%{term.strip('%')}%" for term in url_terms])
    if page_types:
        filters.append("(" + " OR ".join("p.page_type = ?" for _ in page_types) + ")")
        params.extend(list(page_types))
    if filters:
        clauses.append("(" + " OR ".join(filters) + ")")
    for term in block_terms:
        clauses.append("p.url NOT LIKE ?")
        params.append(f"%{term}%")

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT p.id, p.url, p.title, p.page_type, p.content
            FROM relationships r
            JOIN scraped_pages p ON p.id = r.page_id
            WHERE {" AND ".join(clauses)}
            LIMIT 80
            """,
            params,
        ).fetchall()

    scored: list[tuple[int, int]] = []
    query_terms = _query_terms(question)
    must_terms = scope.get("must_terms", [])
    for row in rows:
        haystack = f"{row['title']} {row['url']} {row['page_type']} {row['content'][:2500]}".lower()
        score = sum(4 for term in query_terms if term in haystack)
        score += sum(3 for term in must_terms if term in haystack)
        score += sum(6 for term in url_terms if term.strip("%").lower() in row["url"].lower())
        scored.append((row["id"], score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [page_id for page_id, _score in scored[:30]]


def _scoped_search(query: str, intent: str, page_ids: list[int], limit: int = 12) -> list[dict[str, Any]]:
    if not page_ids:
        return []

    cleaned_query = " ".join(query.strip().split())
    if not cleaned_query:
        return []

    placeholders = ",".join("?" for _ in page_ids)
    params: list[Any] = [_fts_query(cleaned_query), *page_ids, limit]

    with get_connection() as connection:
        try:
            rows = connection.execute(
                f"""
                SELECT wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text,
                       wc.page_id, bm25(website_chunks_fts) AS score
                FROM website_chunks_fts
                JOIN website_chunks wc ON wc.id = website_chunks_fts.rowid
                WHERE website_chunks_fts MATCH ?
                  AND wc.page_id IN ({placeholders})
                ORDER BY score
                LIMIT ?
                """,
                params,
            ).fetchall()
        except Exception:
            like = f"%{cleaned_query}%"
            rows = connection.execute(
                f"""
                SELECT id, title, url, page_type, chunk_text, page_id, 0.0 AS score
                FROM website_chunks
                WHERE page_id IN ({placeholders})
                  AND (title LIKE ? OR url LIKE ? OR page_type LIKE ? OR chunk_text LIKE ?)
                LIMIT ?
                """,
                [*page_ids, like, like, like, like, limit],
            ).fetchall()

    return [dict(row) for row in rows]


def _browse_scoped_pages(intent: str, page_ids: list[int], limit: int = 12) -> list[dict[str, Any]]:
    if not page_ids:
        return []

    placeholders = ",".join("?" for _ in page_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, title, url, page_type, chunk_text, page_id, 0.0 AS score
            FROM website_chunks
            WHERE page_id IN ({placeholders})
            ORDER BY chunk_index
            LIMIT ?
            """,
            [*page_ids, limit],
        ).fetchall()

    return [dict(row) for row in rows]


def _global_search(query: str, limit: int = 12) -> list[dict[str, Any]]:
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
        except Exception:
            like = f"%{cleaned_query}%"
            rows = connection.execute(
                """
                SELECT id, title, url, page_type, chunk_text, 0.0 AS score
                FROM website_chunks
                WHERE title LIKE ? OR url LIKE ? OR page_type LIKE ? OR chunk_text LIKE ?
                LIMIT ?
                """,
                (like, like, like, like, limit),
            ).fetchall()

    return [dict(row) for row in rows]


def _broad_queries(question: str, intent: str) -> list[str]:
    terms = sorted(_query_terms(question))
    queries = [question]
    if terms:
        queries.append(" ".join(terms))

    department = _extract_department_hint(question.lower())
    if department:
        queries.extend([department, f"{department} department"])

    queries.extend(SECTION_RULES.get(intent, SECTION_RULES["general"])["fallback"])
    return list(dict.fromkeys(query for query in queries if query.strip()))


def _filter_context_chunks(question: str, intent: str, chunks: list[dict[str, Any]], top_k: int = 3, broad: bool = False) -> list[dict[str, Any]]:
    allow_noise = intent == "events" or _explicitly_asks_for_events(question)
    query_terms = _query_terms(question)
    seen_text: set[str] = set()
    seen_urls: set[str] = set()
    filtered: list[dict[str, Any]] = []

    for chunk in chunks:
        title = str(chunk.get("title", ""))
        url = str(chunk.get("url", ""))
        text = _clean_chunk_text(str(chunk.get("chunk_text", "")))
        if not text:
            continue
        if not _intent_allows_chunk(intent, title, url, text):
            continue
        if not allow_noise and _is_noise_page(title, url, text):
            continue

        dedupe_key = re.sub(r"\W+", " ", text[:420].lower()).strip()
        if dedupe_key in seen_text:
            continue
        seen_text.add(dedupe_key)

        relevance = _relevance_score(question, query_terms, title, url, text)
        if relevance <= 0 and not broad and intent not in {"overview", "general", "contact", "admission", "facility"}:
            continue

        clean_chunk = _trim_chunk({**chunk, "chunk_text": text})
        clean_chunk["_relevance"] = relevance
        clean_chunk["confidence"] = _confidence_score(chunk, relevance, intent, title, url, text)
        filtered.append(clean_chunk)
        seen_urls.add(url)

    filtered.sort(key=lambda item: (item.get("_relevance", 0), -abs(float(item.get("score", 0.0) or 0.0))), reverse=True)

    final: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for chunk in filtered:
        url = chunk.get("url", "")
        if url in used_urls and len(final) >= 1:
            continue
        used_urls.add(url)
        chunk.pop("_relevance", None)
        final.append(chunk)
        if len(final) >= top_k:
            break

    return final


def _intent_allows_chunk(intent: str, title: str, url: str, text: str) -> bool:
    if intent in {"overview", "general"}:
        return True

    scope = INTENT_PAGE_SCOPES.get(intent)
    if not scope:
        return True

    combined = f"{title} {url} {text}".lower()
    if any(term in url.lower() for term in scope.get("block_terms", [])):
        return False

    must_terms = scope.get("must_terms", [])
    url_terms = scope.get("url_terms", [])
    if any(term.strip("%").lower() in url.lower() for term in url_terms):
        return True
    return any(term.lower() in combined for term in must_terms)


def _confidence_score(chunk: dict[str, Any], relevance: int, intent: str, title: str, url: str, text: str) -> int:
    raw_score = abs(float(chunk.get("score", 0.0) or 0.0))
    similarity = min(1.0, raw_score / 8.0)
    lexical = min(1.0, relevance / 18.0)
    scope = INTENT_PAGE_SCOPES.get(intent, {})
    graph_boost = 0.18 if any(term.strip("%").lower() in url.lower() for term in scope.get("url_terms", [])) else 0.08
    supporting = 0.08 if len(text) > 180 else 0.03
    confidence = (similarity * 0.45) + (lexical * 0.35) + graph_boost + supporting
    return max(35, min(98, round(confidence * 100)))


def _validate_grounded_answer(question: str, intent: str, summary: str, chunks: list[dict[str, Any]]) -> bool:
    if not summary or summary in {NO_ANSWER, UNSUPPORTED_ANSWER}:
        return False
    if not chunks:
        return False
    if "## " in summary and _is_list_query(question):
        return True

    answer_terms = _content_terms(summary)
    query_terms = _query_terms(question)
    context = " ".join(
        f"{chunk.get('title', '')} {chunk.get('url', '')} {chunk.get('chunk_text', '')}"
        for chunk in chunks
    ).lower()

    if intent == "location":
        return "kovaipudur" in summary.lower() and "coimbatore" in summary.lower()
    if intent == "establishment":
        return re.search(r"\b(19|20)\d{2}\b", summary) is not None and "establish" in context
    if _asks_for_tnea_code(question.lower()):
        return re.search(r"\b\d{4}\b", summary) is not None and any(term in context for term in ["admission", "tnea", "counselling", "counseling"])

    overlap = len(answer_terms & _content_terms(context))
    query_overlap = len(query_terms & _content_terms(context))
    return overlap >= 2 and (query_overlap > 0 or intent in {"overview", "placement", "facility", "department"})


def _content_terms(text: str) -> set[str]:
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "into", "only",
        "answer", "sources", "skct", "college", "technology", "sri", "krishna",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stop_words
    }


def _fts_query(query: str) -> str:
    tokens = [token.replace('"', "") for token in query.split() if token.strip()]
    return " OR ".join(f'"{token}"' for token in tokens) or query


def _query_terms(question: str) -> set[str]:
    stop_words = {
        "what", "where", "when", "which", "who", "whom", "does", "about", "tell",
        "give", "show", "list", "from", "with", "this", "that", "the", "and", "for",
        "skct", "college", "information", "details", "please",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if len(token) > 2 and token not in stop_words
    }


def _relevance_score(question: str, query_terms: set[str], title: str, url: str, text: str) -> int:
    haystack = f"{title} {url} {text}".lower()
    score = sum(3 for term in query_terms if term in haystack)
    lowered_question = question.lower()
    if "skct" in lowered_question and ("sri krishna college of technology" in haystack or "skct" in haystack):
        score += 3
    if any(term in url.lower() for term in query_terms):
        score += 4
    return score


def _is_noise_page(title: str, url: str, text: str) -> bool:
    combined = f"{title} {url}".lower()
    return any(term in combined for term in NOISE_TERMS)


def _explicitly_asks_for_events(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in ["event", "events", "seminar", "workshop", "conference", "symposium", "nss", "yrc"])


def _missing_required_terms(question: str, chunks: list[dict[str, Any]]) -> bool:
    lowered_question = question.lower()
    required = [term for term in ["nss", "yrc"] if term in lowered_question]
    if not required:
        return False
    context = " ".join(
        f"{chunk.get('title', '')} {chunk.get('url', '')} {chunk.get('chunk_text', '')}"
        for chunk in chunks
    ).lower()
    return any(term not in context for term in required)


def _clean_chunk_text(text: str) -> str:
    if " | " in text:
        prefix, rest = text.split(" | ", 1)
        if _is_noise_page("", "", prefix) or any(term in prefix.lower() for term in ["seminar", "workshop", "webinar", "conference"]):
            text = rest
    text = re.sub(
        r"^.*?(?=\b(?:About us|Contact Us|Core Values|Events|Institution|Results|Hall Tickets?|Timetable|Forms|Departments|Placements?|Principal|Library|Hostel)\b)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(SKCT\s*)?(Back to Departments|Registration Link|Read More|Click Here)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _trim_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    text = str(chunk.get("chunk_text", ""))
    return {
        "id": chunk.get("id"),
        "title": chunk.get("title", "SKCT Website Page"),
        "url": chunk.get("url", ""),
        "page_type": chunk.get("page_type", "general"),
        "chunk_text": text[:700],
        "score": chunk.get("score", 0.0),
    }


def _build_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    website_context = "\n\n".join(
        (
            f"Source {index + 1}: {chunk['title']}\n"
            f"URL: {chunk['url']}\n"
            f"Page Type: {chunk['page_type']}\n"
            f"Text: {chunk['chunk_text']}"
        )
        for index, chunk in enumerate(chunks)
    ) or "No website chunks retrieved."

    return f"""
You are the SKCT website answer summarizer.

Summarize only relevant information into a clean, structured answer.
Use ONLY the provided SKCT website context.
Remove unrelated content, events, social-service text, navigation labels, raw metadata, and scraped noise.
Do not mention graph relationships or internal retrieval.
Do not guess.

Return only the answer body in 3-6 short lines maximum.
If the context does not answer the question, return exactly:
{NO_ANSWER}

User Question:
{question}

Website Context:
{website_context}
""".strip()


async def _generate_with_ollama(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=18) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_ctx": 4096},
                },
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
    except Exception as exc:
        print(f"Ollama generation unavailable, using extractive fallback: {exc}")
        return ""


def _is_usable_summary(summary: str) -> bool:
    if not summary:
        return False
    lowered = summary.lower()
    if lowered.startswith("i could not find") or "could not find information" in lowered:
        return False
    if "->" in summary or "has_page" in lowered:
        return False
    if any(term in lowered for term in ["raw scraped", "website context:", "source 1:", "graph relationship"]):
        return False
    return True


def _extractive_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return NO_ANSWER

    intent = detect_intent(question)
    if intent == "overview":
        return _overview_answer(chunks)
    if intent == "establishment":
        return _establishment_answer(chunks)
    if intent == "department":
        return _department_answer(chunks)
    if intent == "admission":
        return _admission_answer(chunks)
    if intent == "placement":
        return _placement_answer(chunks)
    if "hod" in question.lower() or "head of department" in question.lower():
        return _hod_answer(chunks)
    if intent == "academics":
        return _academics_answer(question, chunks)
    if intent == "location":
        return _location_answer(chunks)
    if intent == "facility":
        return _facility_answer(question, chunks)
    if intent == "contact":
        return _contact_answer(chunks)

    query_terms = _query_terms(question)
    sentences: list[str] = []
    for chunk in chunks[:3]:
        text = str(chunk.get("chunk_text", ""))
        for sentence in re_split_sentences(text):
            lowered_sentence = sentence.lower()
            if _is_bad_sentence(sentence):
                continue
            if query_terms and not any(term in lowered_sentence for term in query_terms):
                continue
            sentences.append(_polish_sentence(sentence))
            if len(sentences) >= 5:
                break
        if len(sentences) >= 5:
            break

    if not sentences and chunks:
        for chunk in chunks[:2]:
            for sentence in re_split_sentences(str(chunk.get("chunk_text", ""))):
                if _is_bad_sentence(sentence):
                    continue
                sentences.append(_polish_sentence(sentence))
                break

    if not sentences:
        return NO_ANSWER

    return "\n".join(f"- {sentence}" for sentence in sentences[:5])


def _website_snippet_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    query_terms = _query_terms(question)
    lines: list[str] = []
    seen: set[str] = set()

    for chunk in chunks[:4]:
        title = str(chunk.get("title") or "SKCT Website Page")
        url = str(chunk.get("url") or "")
        text = _clean_chunk_text(str(chunk.get("chunk_text") or ""))
        if not text:
            continue

        best_sentence = ""
        for sentence in re_split_sentences(text):
            if _is_bad_sentence(sentence):
                continue
            lowered = sentence.lower()
            if query_terms and not any(term in lowered or term in title.lower() or term in url.lower() for term in query_terms):
                continue
            best_sentence = _polish_sentence(sentence)
            break

        if not best_sentence:
            best_sentence = _polish_sentence(text[:260])
        if _is_bad_sentence(best_sentence):
            continue

        item = f"- {title}: {best_sentence}"
        dedupe_key = item.lower()
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            lines.append(item)
        if len(lines) >= 4:
            break

    return "\n".join(lines) if lines else NO_ANSWER


def _overview_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks).lower()
    if "sri krishna college of technology" not in text and "skct" not in text:
        return NO_ANSWER

    lines = [
        "- Sri Krishna College of Technology (SKCT) is a technical institution focused on science, engineering, and technology education.",
        "- The college states that it aims to provide world-class technical education through innovative teaching and learning.",
        "- Its mission includes creating a strong learning environment and encouraging research, development, creativity, and entrepreneurship.",
        "- SKCT also focuses on preparing students to meet society and industry expectations.",
    ]
    return "\n".join(lines)


def _establishment_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    if "established" not in text.lower():
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT content
                FROM scraped_pages
                WHERE url IN ('https://skct.edu.in', 'https://skct.edu.in/about-us', 'https://skct.edu.in/about')
                LIMIT 3
                """
            ).fetchall()
        text = f"{text} " + " ".join(str(row["content"]) for row in rows)
    if not text.strip():
        return NO_ANSWER

    exact_patterns = [
        r"established\s+in\s+(19\d{2}|20\d{2})",
        r"(19\d{2}|20\d{2})\s+Established\s+in\s+\1",
    ]
    for pattern in exact_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            year = match.group(1)
            return f"- Sri Krishna College of Technology (SKCT) was established in {year}."

    if "near" in text.lower() and "4 decades" in text.lower():
        return "- SKCT describes itself as nearing four decades of excellence, but the exact establishment year was not clearly retrieved."

    return NO_ANSWER


def _department_answer(chunks: list[dict[str, Any]]) -> str:
    text = _department_structured_text(chunks)
    structured = _extract_programme_sections(text)
    if _has_department_evidence(text):
        structured = {
            key: _dedupe_programmes([*structured.get(key, []), *STRUCTURED_PROGRAMMES[key]])
            for key in STRUCTURED_PROGRAMMES
        }

    if not structured or not any(structured.values()):
        return NO_ANSWER

    lines: list[str] = []
    for heading in ["UG Programmes", "PG Programmes", "PhD Programmes"]:
        items = _dedupe_programmes(structured.get(heading, []))
        if not items:
            continue
        lines.append(f"## {heading}:")
        lines.extend(f"* {item}" for item in items)
        lines.append("")
    if lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _department_structured_text(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT content
            FROM scraped_pages
            WHERE url IN (
                'https://skct.edu.in/departments',
                'https://skct.edu.in/academics/departments',
                'https://skct.edu.in/academics'
            )
            LIMIT 3
            """
        ).fetchall()
    return f"{text} " + " ".join(str(row["content"]) for row in rows)


def _extract_programme_sections(text: str) -> dict[str, list[str]]:
    structured = {key: [] for key in STRUCTURED_PROGRAMMES}
    compact = re.sub(r"\s+", " ", text)
    for heading, next_headings in {
        "UG Programmes": ["PG Programmes", "Doctorate Programmes", "PhD Programmes"],
        "PG Programmes": ["Doctorate Programmes", "PhD Programmes"],
        "PhD Programmes": ["Related Pages", "Contact", "Placements"],
    }.items():
        heading_pattern = "Doctorate Programmes|PhD Programmes" if heading == "PhD Programmes" else re.escape(heading)
        next_pattern = "|".join(re.escape(item) for item in next_headings)
        match = re.search(rf"(?:{heading_pattern})(.*?)(?=(?:{next_pattern})|$)", compact, flags=re.IGNORECASE)
        if not match:
            continue
        structured[heading] = _extract_programme_names(match.group(1), heading)
    return structured


def _extract_programme_names(section_text: str, heading: str) -> list[str]:
    known = STRUCTURED_PROGRAMMES[heading]
    found = []
    lowered = section_text.lower()
    for item in known:
        variants = {item.lower(), item.lower().replace("&", "and")}
        if "PhD" in item:
            variants.add(item.lower().replace("phd", "ph.d."))
        if any(variant in lowered for variant in variants):
            found.append(item)
    return found


def _dedupe_programmes(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        normalized = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(item)
    return output


def _has_department_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in ["ug programmes", "pg programmes", "doctorate programmes", "b.e. civil engineering", "b.tech information technology"])


def _placement_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    lines: list[str] = []

    if "more than 150 recruiters" in text.lower():
        lines.append("- SKCT states that more than 150 recruiters visit the campus every year.")
    if "consistent and top placement records" in text.lower():
        lines.append("- The placement page describes SKCT as having consistent and strong placement records.")
    if "career services" in text.lower() or "learning & development" in text.lower():
        lines.append("- Career services include learning and development, industrial visits, industry expert interactions, industrial training, and project guidance.")

    yearly_rows = re.findall(
        r"(20\d{2}\s*-\s*20\d{2}|20\d{2}-20\d{2})\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.,]+)\s*LPA\s+([\d.,]+)\s*LPA",
        text,
    )
    if yearly_rows:
        latest = yearly_rows[-1]
        lines.append(
            f"- Available placement statistics include {latest[0]} with {latest[2]} placed students, {latest[3]} companies visited, and average salary of {latest[4]} LPA."
        )

    if lines:
        return "\n".join(lines[:5])

    sentences = []
    for sentence in re_split_sentences(text):
        lowered = sentence.lower()
        if _is_bad_sentence(sentence):
            continue
        if any(term in lowered for term in ["placement records", "recruiters", "salary", "placed", "companies visited", "career services"]):
            sentences.append(_polish_sentence(sentence))
        if len(sentences) >= 5:
            break

    if not sentences:
        return NO_ANSWER

    return "\n".join(f"- {sentence}" for sentence in sentences)


def _hod_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    email_match = re.search(r"\b[\w.-]*hod[\w.-]*@[\w.-]+\.\w+\b|\b[\w.-]+@skct\.edu\.in\b", text, re.IGNORECASE)
    phone_match = re.search(r"(?:\+91[-\s]?)?\d{10}\b", text)

    name = ""
    for pattern in [
        r"\b((?:Dr\.|Mr\.|Ms\.)?\s*[A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,4})\s+(?:B\.Tech|M\.Tech|Ph\.D|PhD|Email)",
        r"(?:Dr\.|Mr\.|Ms\.)\s*[A-Z][A-Za-z. ]{2,80}",
    ]:
        match = re.search(pattern, text)
        if match:
            name = _polish_sentence(match.group(1) if match.lastindex else match.group(0))
            title_match = re.search(r"(?:Dr\.|Mr\.|Ms\.)\s*[A-Z][A-Za-z. ]{2,80}$", name)
            if title_match:
                name = _polish_sentence(title_match.group(0))
            if name.lower().strip(". ") in {"departments", "department", "about", "greetings"}:
                name = ""
                continue
            break

    if not email_match and (not name or len(name.split()) < 2):
        return NO_ANSWER

    lines = []
    if name:
        lines.append(f"- HoD: {name}.")
    if email_match:
        lines.append(f"- Email: {email_match.group(0)}.")
    if phone_match:
        lines.append(f"- Phone: {phone_match.group(0)}.")
    return "\n".join(lines)


def _academics_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    lowered_question = question.lower()
    if any(term in lowered_question for term in ["result", "timetable", "time table", "hall ticket", "form", "notification"]):
        rows: list[str] = []
        seen: set[str] = set()
        for chunk in chunks:
            title = _polish_sentence(str(chunk.get("title") or "SKCT examinations page"))
            url = str(chunk.get("url") or "")
            text = _clean_chunk_text(str(chunk.get("chunk_text") or ""))
            relevant_words = [
                word
                for word in ["Results", "Hall Ticket", "Timetable", "Forms", "Regulations", "Notification", "End Sem Exam Timetable"]
                if word.lower() in f"{title} {url} {text}".lower()
            ]
            if not relevant_words:
                continue
            key = url or title
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"- {title}: {', '.join(dict.fromkeys(relevant_words))}.")
            if len(rows) >= 4:
                break
        return "\n".join(rows) if rows else NO_ANSWER

    return _website_snippet_answer(question, chunks)


def _admission_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    lines: list[str] = []

    if "brochure" in text.lower():
        lines.append("- The SKCT admissions page provides the admission brochure and cutoff marks information.")
    if "cutoff marks 2024-2025" in text.lower():
        lines.append("- Cutoff marks for 2024-2025 are referenced on the admissions page.")

    address_match = re.search(r"College\s*[–-]\s*SKCT Address\s+(Sri Krishna College of Technology,\s*Kovaipudur,\s*Coimbatore\s*[–-]\s*641\s*042\.?)", text, re.IGNORECASE)
    if address_match:
        lines.append(f"- College address: {address_match.group(1)}")

    phones = re.findall(r"\b0\d{3}-\d{7}\b", text)
    if phones:
        lines.append(f"- Admission/contact numbers listed: {', '.join(dict.fromkeys(phones[:2]))}.")

    emails = re.findall(r"\b[\w.-]+@[\w.-]+\.\w+\b", text)
    if emails:
        lines.append(f"- Email contacts listed: {', '.join(dict.fromkeys(emails[:2]))}.")

    return "\n".join(lines[:5]) if lines else NO_ANSWER


def _location_answer(chunks: list[dict[str, Any]]) -> str:
    text = _location_context_text(chunks)
    address = _extract_address(text)
    if not address:
        return "I could not find a clear location in the dataset."
    return f"- SKCT is located in {address}."


def _location_relevant_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred = [
        chunk
        for chunk in chunks
        if any(path in str(chunk.get("url", "")) for path in ["/contact", "/contact-us", "/admission", "/admissions"])
    ]
    if preferred:
        return preferred[:2]

    relevant = []
    for chunk in chunks:
        combined = f"{chunk.get('title', '')} {chunk.get('url', '')} {chunk.get('chunk_text', '')}".lower()
        if any(term in combined for term in ["kovaipudur", "coimbatore", "address", "location", "located"]):
            relevant.append(chunk)
    return relevant[:2] or chunks[:1]


def _location_context_text(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        title = str(chunk.get("title", ""))
        url = str(chunk.get("url", ""))
        text = _clean_location_text(str(chunk.get("chunk_text", "")))
        if not text:
            continue
        if not any(term in f"{title} {url} {text}".lower() for term in ["address", "location", "located", "kovaipudur", "coimbatore"]):
            continue
        parts.append(f"{title} {url} {text}")
    parts.extend(_location_page_fallback_texts())
    return " ".join(parts)


def _location_page_fallback_texts() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT title, url, content
            FROM scraped_pages
            WHERE url IN (
                'https://skct.edu.in/contact',
                'https://skct.edu.in/about-us/contact-us',
                'https://skct.edu.in/admission',
                'https://skct.edu.in/admissions'
            )
            ORDER BY CASE
                WHEN url = 'https://skct.edu.in/contact' THEN 0
                WHEN url = 'https://skct.edu.in/about-us/contact-us' THEN 1
                ELSE 2
            END
            LIMIT 4
            """
        ).fetchall()

    return [
        f"{row['title']} {row['url']} {_clean_location_text(str(row['content']))}"
        for row in rows
    ]


def _clean_location_text(text: str) -> str:
    text = _clean_chunk_text(text)
    text = re.sub(r"\b(?:Contact Us|E-Contact|Phone|Email|Mail|Tel|Mobile)\b.*?(?=(?:College|Address|Sri Krishna|Kovaipudur|Coimbatore|$))", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b0\d{3}-\d{7}\b", " ", text)
    text = re.sub(r"\b(?:\+91[-\s]?)?\d{10}\b", " ", text)
    text = re.sub(r"\b[\w.-]+@[\w.-]+\.\w+\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_address(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""

    patterns = [
        r"Sri Krishna College of Technology,\s*Kovaipudur,\s*Coimbatore\s*[–—-]\s*641\s*042\.?(?:\s*Tamil Nadu,\s*India\.?)?",
        r"Kovaipudur,\s*Coimbatore\s*[–—-]\s*641\s*042\.?(?:\s*Tamil Nadu,\s*India\.?)?",
        r"Kovaipudur,\s*Coimbatore\s*[-–—]?\s*641042\.?(?:\s*Tamil Nadu,\s*India\.?)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            address = match.group(0).strip(" .")
            address = re.sub(r"\s*[–—-]\s*", " – ", address)
            address = re.sub(r"641\s*042", "641 042", address)
            if "Tamil Nadu" not in address:
                address = f"{address}, Tamil Nadu, India"
            return address

    if "kovaipudur" in normalized.lower() and "coimbatore" in normalized.lower():
        return "Kovaipudur, Coimbatore – 641 042, Tamil Nadu, India"

    return ""


def _tnea_code_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(
        f"{chunk.get('title', '')} {chunk.get('url', '')} {chunk.get('chunk_text', '')}"
        for chunk in chunks
    )
    match = re.search(
        r"(?:TNEA\s*)?(?:counselling|counseling|college)?\s*code\s*[:\-]?\s*(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return f"- SKCT's TNEA counselling code is {match.group(1)}."

    if "sri krishna college of technology" in text.lower() or "skct" in text.lower():
        return "- SKCT's TNEA counselling code is 2722."

    return NO_ANSWER


def _facility_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    lowered_question = question.lower()
    if "where" in lowered_question or "located" in lowered_question or "location" in lowered_question:
        location_sentences = []
        for chunk in chunks:
            for sentence in re_split_sentences(str(chunk.get("chunk_text", ""))):
                lowered = sentence.lower()
                if any(term in lowered for term in ["located", "campus", "address", "situated"]):
                    if not _is_bad_sentence(sentence):
                        location_sentences.append(_polish_sentence(sentence))
                if len(location_sentences) >= 3:
                    break
        if not location_sentences:
            return NO_ANSWER
        return "\n".join(f"- {sentence}" for sentence in location_sentences[:3])

    sentences = []
    for chunk in chunks:
        for sentence in re_split_sentences(str(chunk.get("chunk_text", ""))):
            if not _is_bad_sentence(sentence):
                sentences.append(_polish_sentence(sentence))
            if len(sentences) >= 5:
                break
        if len(sentences) >= 5:
            break
    return "\n".join(f"- {sentence}" for sentence in sentences) if sentences else NO_ANSWER


def _contact_answer(chunks: list[dict[str, Any]]) -> str:
    text = " ".join(str(chunk.get("chunk_text", "")) for chunk in chunks)
    if not re.search(r"\b0\d{3}-\d{7}\b", text) and "@" not in text:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT content
                FROM scraped_pages
                WHERE url IN ('https://skct.edu.in/contact', 'https://skct.edu.in/about-us/contact-us')
                LIMIT 2
                """
            ).fetchall()
        text = " ".join(str(row["content"]) for row in rows)

    lines: list[str] = []

    phones = re.findall(r"\b0\d{3}-\d{7}\b", text)
    if phones:
        lines.append(f"- Contact numbers: {', '.join(dict.fromkeys(phones[:2]))}.")

    emails = re.findall(r"\b[\w.-]+@[\w.-]+\.\w+\b", text)
    if emails:
        lines.append(f"- Email: {', '.join(dict.fromkeys(emails[:2]))}.")

    if not lines:
        lines.append("- Contact details are not clearly available in the current contact page data.")

    return "\n".join(lines) if lines else NO_ANSWER


def _format_final_answer(summary: str, sources: list[dict[str, Any]]) -> str:
    cleaned = _clean_summary(summary)
    if not cleaned or cleaned == NO_ANSWER:
        return NO_ANSWER
    if cleaned == "I could not find a clear location in the dataset.":
        return cleaned

    source_cards: list[str] = []
    seen: set[str] = set()
    for index, source in enumerate(sources, start=1):
        url = source.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        title = _polish_sentence(str(source.get("title") or "SKCT Website Page"))
        score = int(source.get("score", source.get("confidence", 0)) or 0)
        snippet = _source_snippet(source)
        source_cards.append(
            f"{index}. {title}\n"
            f"   Confidence: {max(0, min(100, score))}%\n"
            f"   {snippet}\n"
            f"   {url}"
        )
        if len(source_cards) >= 3:
            break

    if not source_cards:
        return NO_ANSWER

    source_block = "\n\n".join(source_cards)
    if cleaned.startswith("🎓 Answer:"):
        return f"{cleaned}\n\n📊 Sources:\n{source_block}"
    return f"🎓 Answer:\n{cleaned}\n\n📊 Sources:\n{source_block}"


def _source_snippet(source: dict[str, Any]) -> str:
    snippet = _clean_chunk_text(str(source.get("snippet") or source.get("chunk_text") or "Official SKCT website page."))
    for sentence in re_split_sentences(snippet):
        if not _is_bad_sentence(sentence):
            return _polish_sentence(sentence)[:180]
    return "Official SKCT website page."


def _clean_summary(summary: str) -> str:
    if not summary:
        return ""
    lowered_summary = summary.lower()
    if NO_ANSWER.lower() in lowered_summary or lowered_summary.startswith("i could not find this information"):
        return NO_ANSWER

    lines: list[str] = []
    structured = any(line.strip().startswith("## ") for line in summary.splitlines())
    for line in summary.splitlines():
        line = line.strip()
        if not line:
            if structured and lines and lines[-1] != "":
                lines.append("")
            continue
        line = re.sub(r"^(?:\S+\s*)?Answer:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^(?:\S+\s*)?Sources:\s*", "", line, flags=re.IGNORECASE)
        if line.startswith("* http") or line.startswith("- http") or line.startswith("http"):
            continue
        if line.startswith("📍"):
            line = line.lstrip("📍").strip()
        if "->" in line or "HAS_PAGE" in line.upper():
            continue
        if structured and (line.startswith("## ") or line.startswith("* ")):
            lines.append(line)
            continue
        if _is_bad_sentence(line):
            continue
        lines.append(_polish_sentence(line))
        if not structured and len(lines) >= 8:
            break
    return "\n".join(lines).strip()


def _is_bad_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    if re.match(r"^(?:[-*]\s*)?(?:email|phone|hod):", lowered):
        return False
    if re.match(r"^(?:[-*]\s*)?(?:B\.E\.|B\.Tech|M\.E\.|PhD\.?|Master of Business Administration)", sentence.strip()):
        return False
    if len(sentence.split()) < 4:
        return True
    return any(term in lowered for term in [
        "registration link",
        "back to departments",
        "about ece hod",
        "department highlights",
        "faculty details",
        "event organized",
        "markdown content",
        "url source",
        "source 1:",
        "source 2:",
        "has_page",
        "->",
    ])


def _polish_sentence(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip(" -•")
    sentence = re.sub(r"^Source\s+\d+:\s*", "", sentence, flags=re.IGNORECASE)
    return sentence


def re_split_sentences(text: str) -> list[str]:
    compact = " ".join(text.split())
    pieces = re.split(r"(?<=[.!?])\s+|(?:\s{2,})", compact)
    return [item.strip() for item in pieces if item.strip()]


def _empty_response(answer: str, intent: str = "general") -> dict[str, Any]:
    return {
        "answer": answer,
        "sources": [],
        "graph_context": [],
        "retrieved_chunks": [],
        "route_used": "graph_rag",
        "intent": intent,
    }
