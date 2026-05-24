"""
prompts.py — Prompt templates for Graph RAG answer generation.
Context assembled from SQL facts, website chunks, and graph relationships.
"""

import json
import re
from typing import Any

_SNIPPET_STOPWORDS = {
    "the", "and", "for", "with", "about", "tell", "give", "more", "information",
    "details", "detail", "show", "what", "which", "who", "when", "where", "how",
    "is", "are", "was", "were", "does", "did", "of", "in", "on", "to", "from",
    "skct", "college", "sri", "krishna", "technology",
}

SYSTEM_PROMPT = """You are an intelligent academic assistant for Sri Krishna College of Technology (SKCT), AI&DS B Section, Batch 2023.

You have access to real academic data for 60 students across Semesters 1-5.

=== ANNA UNIVERSITY GRADING SYSTEM ===
Grade Letter → Grade Points:
  O = 10 (Outstanding)
  A+ = 9 (Excellent)
  A  = 8 (Very Good)
  B+ = 7 (Good)
  B  = 6 (Above Average)
  C  = 5 (Average)
  U  = 0 (FAIL / Reappearance needed)
  '-' = Not registered / Elective not chosen

CGPA = Average of Grade Points across all registered subjects (Anna University standard)
The field 'ug_cgpa' in the data = official CGPA from placement records
The field 'computed_cgpa' = CGPA computed from grade letters in semester results

=== DATA SOURCES ===
1. EXCEL ACADEMIC DATA — real grade letters (O/A+/A/B+/B/C/U), grade points, semester-wise results
2. OFFICIAL WEBSITE DATA — scraped from skct.edu.in (placements, departments, rules, contacts)
3. GRAPH RELATIONSHIPS — entity connections between students, subjects, departments

=== STRICT RULES ===
- Answer ONLY using the provided context sections below.
- If ACADEMIC SQL FACTS section has data → USE IT. Do NOT say data is missing.
- ug_cgpa IS the official CGPA. computed_cgpa is calculated from grade letters.
- Grade points ARE the basis for CGPA — avg_grade_points = CGPA equivalent.
- When context has data: give a precise, structured answer.
- Use bullet points or tables for academic data.
- For large answers, use compact Markdown sections with clear headings and complete every section.
- Do not stop mid-sentence. Prefer a concise but complete answer over an unfinished long answer.
- Do NOT invent any numbers not present in the context.
- Return only the final answer. Do not include hidden reasoning, scratchpad text, or <think> blocks.
- The institution in user-facing answers is Sri Krishna College of Technology (SKCT). Ignore scraped navigation labels for sister institutions unless the user explicitly asks about them.
- Treat page navigation, image alt text, repeated links, and "Structured name" boilerplate as low-confidence context. Prefer actual tables, headings, descriptions, and official page content.
"""


def build_context_block(
    question: str,
    route: str,
    sql_facts: dict | None = None,
    website_chunks: list[dict] | None = None,
    graph_facts: dict | None = None,
    student_identifier: str | None = None,
) -> str:
    """Build the full prompt context string to send to Ollama."""
    parts = []
    parts.append(f"=== USER QUESTION ===\n{question}\n")

    if student_identifier:
        parts.append(f"=== STUDENT CONTEXT ===\nRegister No / Name: {student_identifier}\n")

    parts.append(f"=== RETRIEVAL ROUTE ===\n{route}\n")

    # --- Academic SQL facts ---
    if sql_facts and any(v for v in sql_facts.values() if v):
        parts.append("=== ACADEMIC SQL FACTS (from Excel data) ===")
        parts.append(_format_sql_facts(sql_facts))
        parts.append("")

    # --- Website chunks ---
    if website_chunks:
        parts.append("=== OFFICIAL COLLEGE WEBSITE DATA ===")
        for i, chunk in enumerate(website_chunks[:8], 1):
            title = chunk.get("title") or "Untitled"
            url   = chunk.get("url", "")
            text  = _website_context_snippet(chunk.get("chunk_text", ""), question)
            parts.append(f"[Source {i}] {title}\nURL: {url}\n{text}")
        parts.append("")

    # --- Graph relationships ---
    if graph_facts and graph_facts.get("relationships"):
        parts.append("=== GRAPH RELATIONSHIPS ===")
        parts.append(_format_graph_facts(graph_facts))
        parts.append("")

    # If no context at all
    if not sql_facts and not website_chunks and not graph_facts:
        parts.append(
            "=== NOTICE ===\n"
            "No matching data was retrieved. Tell the user what you cannot answer "
            "and suggest they try: providing a register number, using the website search tab, "
            "or running a full reindex."
        )

    parts.append("=== ANSWER INSTRUCTIONS ===")
    instruction_text = (
        "Answer the user question using the context above.\n"
        "Be precise with numbers. Show calculations when relevant.\n"
        "Mention which data source each fact comes from.\n"
        "For contact details, extract exact phone numbers, email IDs, and addresses from visible text, tel: links, and mailto: links.\n"
        "Do not say a contact detail is missing when it appears in any provided source chunk.\n"
        "Format long answers with Markdown headings, bullets, and tables where useful.\n"
        "If the answer is large, keep wording compact but finish the response completely.\n"
        "Do NOT add information outside the provided context."
    )
    q_lower = question.lower()
    if (
        any(term in q_lower for term in ["department", "departments", "course", "courses", "program", "programs", "programme", "programmes", "branch", "branches"])
        and any(term in q_lower for term in ["available", "offered", "list", "what", "which"])
    ):
        instruction_text += (
            "\nFor list-style questions, give only the requested list and essential labels from the overview/table chunks. "
            "Do not add descriptions, facilities, research details, years, intakes, or accreditation unless the user asks for them. "
            "Do not infer missing departments from unrelated subpages."
        )
    if "engineering" in q_lower and any(term in q_lower for term in ["department", "departments", "course", "courses", "program", "programs", "programme", "programmes"]):
        instruction_text += (
            "\nBecause the user asked for engineering departments/programs, include only engineering entries such as B.E., B.Tech., and M.E. items. "
            "Exclude MBA, Science and Humanities, generic Ph.D. categories, navigation labels, and sister-institution names unless directly requested."
        )
    parts.append(instruction_text)

    return "\n".join(parts)


def _website_context_snippet(text: str, question: str, max_chars: int = 1200) -> str:
    """Keep the most relevant window from long scraped website chunks."""
    text = _clean_website_text(text)
    q_lower = question.lower()
    is_list_query = (
        any(term in q_lower for term in ["department", "departments", "course", "courses", "program", "programs", "programme", "programmes", "branch", "branches"])
        and any(term in q_lower for term in ["available", "offered", "list", "what", "which"])
    )
    if is_list_query:
        max_chars = 2400

    if not text or len(text) <= max_chars:
        return text or ""

    text_lower = text.lower()
    query_tokens = [
        token
        for token in re.findall(r"[a-z0-9@.+-]{3,}", q_lower)
        if token not in _SNIPPET_STOPWORDS
    ]
    evidence_patterns = []
    if any(term in q_lower for term in ["contact", "phone", "email", "address", "location"]):
        evidence_patterns.extend([
            r"\b[\w.+-]+@[\w.-]+\.\w+\b",
            r"\b(?:\+91[-\s]?)?\d{3,5}[-\s]?\d{6,8}\b",
            r"\bkovaipudur\b",
            r"\bcoimbatore\b",
            r"\baddress\b",
        ])
    if any(term in q_lower for term in ["tnea", "code", "counselling"]):
        evidence_patterns.extend([r"\b2722\b", r"\btnea\b", r"\bcollege code\b"])
    if any(term in q_lower for term in ["establish", "established", "founded", "history", "since"]):
        evidence_patterns.extend([r"\b19\d{2}\b", r"\bestablished\b", r"\bfounded\b"])
    if any(term in q_lower for term in ["course", "courses", "program", "programme", "department", "branch"]):
        evidence_patterns.extend([
            r"\bdepartments\s+undergraduate programmes?\b",
            r"\bundergraduate programmes?\s+s\.?no\.?\s+department\b",
            r"table:\s*s\.?no\.?\s+department\s+year",
            r"\bundergraduate programmes?\b",
            r"\bpostgraduate\b",
            r"\bb\.?e\.?\b",
            r"\bb\.?tech\b",
            r"\bm\.?e\.?\b",
            r"\bmba\b",
        ])
    if any(term in q_lower for term in ["placement", "recruiter", "training", "career"]):
        evidence_patterns.extend([r"\bplacement\b", r"\brecruiters?\b", r"\btraining\b", r"\bcareer\b", r"\b\d+\+?\b"])
    if any(term in q_lower for term in ["hostel", "library", "sports", "facility", "facilities"]):
        evidence_patterns.extend([r"\bhostel\b", r"\blibrary\b", r"\bsports?\b", r"\bfacilit(?:y|ies)\b"])

    evidence_matches = []
    token_matches = []
    for token in query_tokens:
        idx = text_lower.find(token)
        if idx >= 0:
            token_matches.append(idx)
    for pattern in evidence_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            evidence_matches.append(match.start())
            break

    matches = evidence_matches or token_matches
    if not matches:
        return text[:max_chars]

    center = min(matches)
    start = max(0, center - (80 if is_list_query else max_chars // 4))
    end = min(len(text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _clean_website_text(text: str) -> str:
    """Remove high-noise scraped website boilerplate before prompting."""
    if not text:
        return ""
    text = re.sub(r"Structured name:\s*Sri Krishna College of Engineering and Technology\s*", "", text, flags=re.I)
    text = re.sub(r"Image (?:alt|title|file):\s*[^ ]+(?:\s+[^:]{0,80})?", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_sql_facts(facts: dict) -> str:
    """Convert SQL facts dict to a readable string for the LLM."""
    if not facts:
        return "(No academic data)"

    lines = []

    # ---- Student profile ----
    student = facts.get("student", {})
    reg      = facts.get("register_no", student.get("register_no", ""))
    name     = facts.get("name", student.get("name", ""))
    ug_cgpa  = facts.get("ug_cgpa") or student.get("ug_cgpa")
    comp_cgpa = facts.get("computed_cgpa")

    if reg or name:
        lines.append(
            f"STUDENT: {name or 'N/A'} | Reg: {reg or 'N/A'} | "
            f"Dept: {student.get('department','N/A')} | "
            f"Branch: {student.get('branch','N/A')}"
        )
        if ug_cgpa is not None:
            lines.append(f"  Official CGPA (placement records): {ug_cgpa}")
        if comp_cgpa is not None:
            lines.append(f"  Computed CGPA (avg of grade points): {comp_cgpa}")
        if student.get("arrears_count"):
            lines.append(f"  Arrears: {student.get('arrears_count')} | History: {student.get('history_of_arrears')}")

    # ---- Full results list ----
    results = facts.get("results", [])
    if results:
        lines.append(f"\nGRADE RECORDS ({len(results)} subjects):")
        lines.append(f"{'Sem':<4} {'Subject':<40} {'Code':<10} {'Grade':<6} {'GP':<6} {'Status':<8}")
        lines.append("-" * 80)
        for r in results[:40]:
            sem   = str(r.get("semester_no", "?"))
            subj  = str(r.get("subject_name", "?"))[:38]
            code  = str(r.get("subject_code", "") or "")[:9]
            grade = str(r.get("grade", "?"))
            gp    = str(r.get("grade_points", "?"))
            stat  = str(r.get("result_status", "?"))
            lines.append(f"{sem:<4} {subj:<40} {code:<10} {grade:<6} {gp:<6} {stat:<8}")

    # ---- Semester averages ----
    sem_avgs = facts.get("semester_averages", [])
    if sem_avgs:
        lines.append("\nSEMESTER SUMMARY:")
        lines.append(f"{'Sem':<4} {'AvgGP':<8} {'AvgGPA':<8} {'AvgCGPA':<9} {'Subj':<6} {'Pass':<6} {'Fail':<5}")
        lines.append("-" * 55)
        for s in sem_avgs:
            lines.append(
                f"{str(s.get('semester_no','?')):<4} "
                f"{str(s.get('avg_grade_points','?')):<8} "
                f"{str(s.get('avg_gpa','?')):<8} "
                f"{str(s.get('avg_cgpa','?')):<9} "
                f"{str(s.get('subjects_count','?')):<6} "
                f"{str(s.get('passed_count','?')):<6} "
                f"{str(s.get('failed_count','?')):<5}"
            )

    # ---- Best semester ----
    best = facts.get("best_semester")
    if best:
        lines.append(
            f"\nBEST SEMESTER: Sem {best.get('semester_no','?')} — "
            f"Avg Grade Points: {best.get('avg_grade_points','?')} | "
            f"CGPA: {best.get('avg_cgpa','?')} | "
            f"Subjects: {best.get('subjects_count','?')}"
        )

    # ---- Lowest subjects ----
    lowest = facts.get("lowest_subjects", [])
    if lowest:
        lines.append("\nLOWEST GRADE SUBJECTS:")
        for s in lowest:
            lines.append(
                f"  Sem {s.get('semester_no','?')} | {s.get('subject_name','?')} | "
                f"Grade: {s.get('grade','?')} | GP: {s.get('grade_points','?')} | {s.get('result_status','?')}"
            )

    # ---- Highest subjects ----
    highest = facts.get("highest_subjects", [])
    if highest:
        lines.append("\nHIGHEST GRADE SUBJECTS:")
        for s in highest:
            lines.append(
                f"  Sem {s.get('semester_no','?')} | {s.get('subject_name','?')} | "
                f"Grade: {s.get('grade','?')} | GP: {s.get('grade_points','?')} | {s.get('result_status','?')}"
            )

    # ---- Toppers ----
    toppers = facts.get("toppers", [])
    if toppers:
        cgpa_src = facts.get("cgpa_source", "")
        note     = facts.get("note", "")
        lines.append(f"\nTOP STUDENTS BY CGPA:")
        if cgpa_src:
            lines.append(f"  Source: {cgpa_src}")
        if note:
            lines.append(f"  Note: {note}")
        for i, t in enumerate(toppers, 1):
            cgpa_val = t.get('cgpa') or t.get('avg_grade_points') or t.get('avg_grade_points')
            lines.append(
                f"  {i}. {t.get('name', t.get('register_no','?'))} "
                f"({t.get('register_no','?')}) — CGPA: {cgpa_val}"
            )

    # ---- Failed students ----
    failed = facts.get("failed_students", [])
    if failed:
        lines.append(f"\nFAILED STUDENTS ({len(failed)}):")
        for f in failed[:20]:
            lines.append(
                f"  {f.get('name', f.get('register_no','?'))} | "
                f"{f.get('subject_name','?')} | Sem {f.get('semester_no','?')} | "
                f"Grade: {f.get('grade','?')}"
            )

    # ---- Class averages ----
    class_avgs = facts.get("class_averages", [])
    if class_avgs:
        lines.append("\nCLASS AVERAGES:")
        for c in class_avgs:
            lines.append(
                f"  {c.get('subject_name','?')} (Sem {c.get('semester_no','?')}) — "
                f"Class Avg GP: {c.get('class_avg_grade_points','?')} | "
                f"Students: {c.get('student_count','?')} | "
                f"Pass: {c.get('pass_count','?')} | Fail: {c.get('fail_count','?')}"
            )

    # ---- Progress / trajectory ----
    progress = facts.get("progress", [])
    if progress:
        lines.append("\nACADEMIC PROGRESS (semester-wise):")
        for p in progress:
            lines.append(
                f"  Sem {p.get('semester_no','?')} | "
                f"Avg GP: {p.get('avg_grade_points','?')} | "
                f"CGPA: {p.get('cgpa','?')} | "
                f"Passed: {p.get('passed','?')} | Failed: {p.get('failed','?')}"
            )

    # ---- Subject graph ----
    subject_graph = facts.get("subject_graph", [])
    if subject_graph:
        lines.append(f"\nSUBJECT GRAPH ({len(subject_graph)} subjects):")
        for s in subject_graph[:20]:
            lines.append(
                f"  Sem {s.get('semester_no','?')} | {s.get('subject_name','?')} | "
                f"Grade: {s.get('grade','?')} | GP: {s.get('grade_points','?')}"
            )

    # ---- Grade distribution ----
    grade_dist = facts.get("grade_distribution", [])
    if grade_dist:
        lines.append("\nGRADE DISTRIBUTION:")
        for g in grade_dist:
            lines.append(f"  {g.get('grade','?')}: {g.get('count','?')} students")

    # ---- All students summary ----
    if facts.get("total_students"):
        lines.append(f"\nTOTAL STUDENTS IN BATCH: {facts.get('total_students')}")

    # ---- Relationships ----
    relationships = facts.get("relationships", [])
    if relationships:
        lines.append("\nGRAPH RELATIONSHIPS:")
        for r in relationships[:15]:
            lines.append(
                f"  {r.get('source_name','?')} --[{r.get('relation_type','?')}]--> "
                f"{r.get('target_name','?')}"
            )

    return "\n".join(lines) if lines else "(No structured data available)"


def _format_graph_facts(facts: dict) -> str:
    if not facts:
        return "(No graph data)"
    lines = []
    relationships = facts.get("relationships", [])
    for r in relationships[:20]:
        props = r.get("properties_json", "{}")
        try:
            p = json.loads(props) if isinstance(props, str) else props
            pstr = " | ".join(f"{k}={v}" for k, v in p.items() if v) if p else ""
        except Exception:
            pstr = ""
        lines.append(
            f"  {r.get('source_name','?')} ({r.get('source_type','?')}) "
            f"--[{r.get('relation_type','?')}]--> "
            f"{r.get('target_name','?')} ({r.get('target_type','?')})"
            + (f" [{pstr}]" if pstr else "")
        )
    return "\n".join(lines) if lines else "(No relationships found)"
