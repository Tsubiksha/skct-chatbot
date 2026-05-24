"""
website_entity_extractor.py — Entity & relationship extraction for Graph RAG.

Builds a knowledge graph from:
1. Excel academic data  (students, subjects, semesters, departments)
2. Scraped website pages (college, pages, recruiters, departments)

No LLM required — rule-based only.
"""

import json
import logging
import re

from backend.app.graph_sqlite.db import get_conn

logger = logging.getLogger(__name__)

KNOWN_DEPARTMENTS = [
    "Computer Science and Engineering",
    "Artificial Intelligence and Data Science",
    "Information Technology",
    "Electronics and Communication Engineering",
    "Electrical and Electronics Engineering",
    "Mechanical Engineering", "Civil Engineering",
    "Automobile Engineering", "Chemical Engineering",
    "Biotechnology", "Master of Business Administration",
    "Master of Computer Applications",
]

_DEPT_KEYWORDS: dict[str, str] = {
    "computer science and engineering": "Computer Science and Engineering",
    "cse": "Computer Science and Engineering",
    "artificial intelligence and data science": "Artificial Intelligence and Data Science",
    "ai&ds": "Artificial Intelligence and Data Science",
    "aids": "Artificial Intelligence and Data Science",
    "ai and ds": "Artificial Intelligence and Data Science",
    "information technology": "Information Technology",
    "electronics and communication": "Electronics and Communication Engineering",
    "ece": "Electronics and Communication Engineering",
    "electrical and electronics": "Electrical and Electronics Engineering",
    "eee": "Electrical and Electronics Engineering",
    "mechanical engineering": "Mechanical Engineering",
    "civil engineering": "Civil Engineering",
    "mba": "Master of Business Administration",
    "mca": "Master of Computer Applications",
}

_PAGE_ENTITY_MAP = {
    "placement":         [("Placement Cell", "Placement")],
    "recruiter":         [("Recruiter Page", "Recruiter")],
    "training":          [("Training Cell", "Training")],
    "contact":           [("SKCT Contact", "Contact")],
    "regulations":       [("Academic Regulations", "Regulation")],
    "exams":             [("Exam Office", "Rule")],
    "academic_calendar": [("Academic Calendar", "AcademicCalendar")],
    "research":          [("Research Cell", "Research")],
    "event":             [("Events", "Event")],
}

_KNOWN_RECRUITERS = [
    "TCS", "Infosys", "Wipro", "Cognizant", "HCL", "Accenture",
    "Capgemini", "IBM", "Amazon", "Google", "Microsoft", "Zoho",
    "Hexaware", "Mphasis", "L&T Infotech", "Tech Mahindra",
    "NTT Data", "Birlasoft", "Mindtree", "Persistent",
]

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_CODE_RE = re.compile(
    r"\b((?:TNEA|college|counselling|counseling|institution|institute|AICTE|AISHE)\s+(?:counselling\s+)?code)\s*[:\-]?\s*([A-Z0-9/-]{2,})",
    re.I,
)
_TNEA_COLLEGE_INFO_RE = re.compile(r"/CollegeInfo/(\d{4})\.PDF$", re.I)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _upsert_entity(conn, name: str, entity_type: str,
                   source_type: str = "excel",
                   source_id: int = None,
                   metadata: dict = None) -> int | None:
    meta = json.dumps(metadata or {})
    conn.execute(
        """INSERT INTO entities (name, entity_type, source_type, source_id, metadata_json)
           VALUES (?,?,?,?,?)
           ON CONFLICT(name, entity_type) DO UPDATE SET
             metadata_json = COALESCE(excluded.metadata_json, entities.metadata_json)""",
        (name, entity_type, source_type, source_id, meta),
    )
    row = conn.execute(
        "SELECT id FROM entities WHERE name=? AND entity_type=?",
        (name, entity_type)
    ).fetchone()
    return row["id"] if row else None


def _upsert_rel(conn, src_id: int | None, relation: str,
                tgt_id: int | None, props: dict = None):
    if src_id is None or tgt_id is None:
        return
    conn.execute(
        """INSERT OR IGNORE INTO relationships
             (source_entity_id, relation_type, target_entity_id, properties_json)
           VALUES (?,?,?,?)""",
        (src_id, relation, tgt_id, json.dumps(props or {})),
    )


def _add_fact_entity(conn, page_ent_id: int, name: str, entity_type: str,
                     page_id: int, url: str, metadata: dict, stats: dict):
    eid = _upsert_entity(
        conn, name.strip(), entity_type,
        source_type="website", source_id=page_id,
        metadata={"url": url, **metadata},
    )
    stats["entities"] += 1
    _upsert_rel(conn, page_ent_id, "HAS_FACT", eid, metadata)
    stats["relationships"] += 1


def _extract_contact_and_code_facts(conn, page_ent_id: int, page_id: int,
                                    url: str, title: str, content: str,
                                    stats: dict):
    text = f"{title}\n{content}"

    tnea_url_match = _TNEA_COLLEGE_INFO_RE.search(url)
    if tnea_url_match:
        code = tnea_url_match.group(1)
        _add_fact_entity(
            conn, page_ent_id, f"TNEA Counselling Code: {code}", "Code",
            page_id, url, {"label": "TNEA Counselling Code", "value": code}, stats,
        )

    seen_codes = set()
    for match in _CODE_RE.finditer(text):
        label = re.sub(r"\s+", " ", match.group(1)).strip().title()
        value = match.group(2).strip().strip(".,;")
        key = (label.lower(), value.upper())
        if key in seen_codes:
            continue
        seen_codes.add(key)
        _add_fact_entity(
            conn, page_ent_id, f"{label}: {value}", "Code",
            page_id, url, {"label": label, "value": value}, stats,
        )

    for email in sorted(set(_EMAIL_RE.findall(text))):
        _add_fact_entity(
            conn, page_ent_id, email, "Email",
            page_id, url, {"value": email}, stats,
        )

    seen_phones = set()
    phone_lines = [
        line for line in text.splitlines()
        if any(marker in line.lower() for marker in ["tel:", "phone", "mobile", "contact", "call", "fax"])
    ]
    for line in phone_lines:
        for raw in _PHONE_RE.findall(line):
            phone = re.sub(r"\s+", " ", raw).strip(" .,-()")
            digits = re.sub(r"\D", "", phone)
            if len(digits) < 10 or len(digits) > 13 or digits in seen_phones:
                continue
            if re.search(r"\b\d{1,2}[.-]\d{1,2}[.-]\d{2,4}\b", phone):
                continue
            if re.fullmatch(r"\d{4}[-/]\d{4}", phone):
                continue
            if re.search(r"\b20\d{2}\b", phone):
                continue
            if len(digits) == 13 and not digits.startswith("91"):
                continue
            seen_phones.add(digits)
            _add_fact_entity(
                conn, page_ent_id, phone, "Phone",
                page_id, url, {"digits": digits}, stats,
            )

    lines = [re.sub(r"\s+", " ", line).strip() for line in content.splitlines()]
    for idx, line in enumerate(lines):
        if line.lower().rstrip(":") == "address":
            block = [part for part in lines[idx + 1:idx + 5] if part]
            if block:
                _add_fact_entity(
                    conn, page_ent_id, "Address: " + ", ".join(block), "Address",
                    page_id, url, {"value": ", ".join(block)}, stats,
                )

    for idx, line in enumerate(lines):
        clean = re.sub(r"\s+", " ", line).strip()
        lower = clean.lower()
        if (
            20 <= len(clean) <= 220
            and any(kw in lower for kw in ["address", "kovaipudur", "641 042", "pincode", "pin code"])
        ):
            _add_fact_entity(
                conn, page_ent_id, clean, "Address",
                page_id, url, {"value": clean}, stats,
            )
        if "kovaipudur" in lower:
            block = [part for part in lines[idx:idx + 4] if part]
            value = ", ".join(block)
            if "coimbatore" in value.lower() and ("641042" in value or "641 042" in value):
                _add_fact_entity(
                    conn, page_ent_id, "Address: " + value, "Address",
                    page_id, url, {"value": value}, stats,
                )


# ---------------------------------------------------------------------------
# Phase 1 — Excel academic graph
# ---------------------------------------------------------------------------

def _build_academic_graph(conn) -> dict:
    """
    Build entities and relationships from students/results/subjects tables.

    Entities created:
      College → Department → Batch → Student
      Semester → Subject
    Relationships:
      College  HAS_DEPT   Department
      Dept     HAS_BATCH  Batch
      Batch    HAS_STUDENT Student
      Student  STUDIED    Subject (with grade, semester)
      Subject  IN_SEM     Semester
    """
    stats = {"entities": 0, "relationships": 0}

    # ── College ──────────────────────────────────────────────────────────────
    college_id = _upsert_entity(
        conn, "Sri Krishna College of Technology", "College",
        metadata={"url": "https://skct.edu.in/", "short_name": "SKCT"}
    )
    stats["entities"] += 1

    # ── Department ───────────────────────────────────────────────────────────
    dept_name = "Artificial Intelligence and Data Science"
    dept_id = _upsert_entity(conn, dept_name, "Department",
                              metadata={"college": "SKCT", "code": "AI&DS"})
    stats["entities"] += 1
    _upsert_rel(conn, college_id, "HAS_DEPARTMENT", dept_id)
    stats["relationships"] += 1

    # ── Semesters ─────────────────────────────────────────────────────────────
    sem_ids: dict[int, int] = {}
    for row in conn.execute("SELECT DISTINCT semester_no FROM semesters ORDER BY semester_no"):
        sem_no = row["semester_no"]
        if sem_no is None:
            continue
        sid = _upsert_entity(conn, f"Semester {sem_no}", "Semester",
                              metadata={"semester_no": sem_no, "department": dept_name})
        sem_ids[sem_no] = sid
        stats["entities"] += 1
        _upsert_rel(conn, dept_id, "HAS_SEMESTER", sid)
        stats["relationships"] += 1

    # ── Subjects ──────────────────────────────────────────────────────────────
    subj_ids: dict[str, int] = {}
    for row in conn.execute(
        "SELECT DISTINCT subject_name, subject_code, semester_no FROM subjects"
    ):
        subj_name = row["subject_name"] or ""
        subj_code = row["subject_code"] or ""
        sem_no    = row["semester_no"]
        if not subj_name:
            continue
        key = f"{subj_code}::{subj_name}::{sem_no}"
        sid = _upsert_entity(conn, subj_name, "Subject",
                              metadata={"code": subj_code, "semester_no": sem_no,
                                        "department": dept_name})
        subj_ids[key] = sid
        stats["entities"] += 1
        if sem_no in sem_ids:
            _upsert_rel(conn, sem_ids[sem_no], "HAS_SUBJECT", sid,
                        {"subject_code": subj_code})
            stats["relationships"] += 1

    # ── Batches ───────────────────────────────────────────────────────────────
    batch_ids: dict[str, int] = {}
    for row in conn.execute("SELECT DISTINCT batch FROM students WHERE batch IS NOT NULL"):
        batch = row["batch"]
        bid = _upsert_entity(conn, f"Batch {batch}", "Batch",
                              metadata={"year": batch, "department": dept_name})
        batch_ids[batch] = bid
        stats["entities"] += 1
        _upsert_rel(conn, dept_id, "HAS_BATCH", bid)
        stats["relationships"] += 1

    # ── Students ──────────────────────────────────────────────────────────────
    student_ids: dict[str, int] = {}
    for stu in conn.execute("SELECT register_no, name, batch, ug_cgpa FROM students"):
        reg  = stu["register_no"]
        name = stu["name"] or reg
        batch = stu["batch"]
        cgpa  = stu["ug_cgpa"]

        stu_id = _upsert_entity(conn, reg, "Student",
                                 metadata={"name": name, "register_no": reg,
                                           "batch": batch, "cgpa": cgpa,
                                           "department": dept_name})
        student_ids[reg] = stu_id
        stats["entities"] += 1

        # Student → Batch
        if batch and batch in batch_ids:
            _upsert_rel(conn, stu_id, "MEMBER_OF", batch_ids[batch])
            stats["relationships"] += 1

    # ── Student STUDIED Subject ────────────────────────────────────────────
    for res in conn.execute(
        """SELECT register_no, subject_name, subject_code, semester_no,
                  grade, grade_points, result_status
           FROM results"""
    ):
        reg       = res["register_no"]
        subj_name = res["subject_name"] or ""
        subj_code = res["subject_code"] or ""
        sem_no    = res["semester_no"]
        grade     = res["grade"] or ""
        gp        = res["grade_points"]
        status    = res["result_status"] or ""

        stu_id = student_ids.get(reg)
        key    = f"{subj_code}::{subj_name}::{sem_no}"
        subj_id = subj_ids.get(key)

        if stu_id and subj_id:
            _upsert_rel(conn, stu_id, "STUDIED", subj_id,
                        {"grade": grade, "grade_points": gp,
                         "semester_no": sem_no, "status": status})
            stats["relationships"] += 1

    return stats


# ---------------------------------------------------------------------------
# Phase 2 — Website page graph (optional, skipped if no pages)
# ---------------------------------------------------------------------------

def _build_website_graph(conn, college_id: int) -> dict:
    stats = {"entities": 0, "relationships": 0}

    pages = conn.execute(
        "SELECT id, url, title, page_type, content FROM scraped_pages"
    ).fetchall()

    if not pages:
        return stats

    for page in pages:
        page_id   = page["id"]
        url       = page["url"] or ""
        title     = page["title"] or ""
        page_type = page["page_type"] or "general"
        content   = page["content"] or ""

        page_ent_id = _upsert_entity(conn, url, "Page", source_type="website",
                                      source_id=page_id,
                                      metadata={"title": title,
                                                "page_type": page_type, "url": url})
        stats["entities"] += 1
        _upsert_rel(conn, college_id, "HAS_PAGE", page_ent_id)
        stats["relationships"] += 1

        # Page-type entities
        for pt, defs in _PAGE_ENTITY_MAP.items():
            if page_type == pt:
                for ent_name, ent_type in defs:
                    eid = _upsert_entity(conn, ent_name, ent_type,
                                         source_type="website", source_id=page_id,
                                         metadata={"url": url})
                    stats["entities"] += 1
                    _upsert_rel(conn, page_ent_id, "MENTIONS", eid)
                    _upsert_rel(conn, eid, "PART_OF", college_id)
                    stats["relationships"] += 2

        # Department mentions
        text_lower = (title + " " + content[:500]).lower()
        for kw, canonical in _DEPT_KEYWORDS.items():
            if kw in text_lower:
                dept_id = _upsert_entity(conn, canonical, "Department",
                                          metadata={"college": "SKCT"})
                stats["entities"] += 1
                _upsert_rel(conn, page_ent_id, "MENTIONS", dept_id)
                stats["relationships"] += 1
                break

        # Recruiters
        if page_type in ("recruiter", "placement"):
            for company in _KNOWN_RECRUITERS:
                if company.lower() in content.lower():
                    rid = _upsert_entity(conn, company, "Recruiter",
                                          source_type="website",
                                          metadata={"source_page": url})
                    stats["entities"] += 1
                    _upsert_rel(conn, page_ent_id, "MENTIONS", rid)
                    stats["relationships"] += 1

        _extract_contact_and_code_facts(
            conn, page_ent_id, page_id, url, title, content, stats
        )

    page_entities_by_source_id = {
        row["source_id"]: row["id"]
        for row in conn.execute(
            "SELECT id, source_id FROM entities WHERE entity_type='Page' AND source_type='website'"
        ).fetchall()
    }
    page_entities_by_url = {
        row["name"]: row["id"]
        for row in conn.execute(
            "SELECT id, name FROM entities WHERE entity_type='Page' AND source_type='website'"
        ).fetchall()
    }
    links = conn.execute(
        "SELECT source_page_id, target_url, link_text, depth FROM page_links"
    ).fetchall()
    for link in links:
        src_id = page_entities_by_source_id.get(link["source_page_id"])
        tgt_id = page_entities_by_url.get(link["target_url"])
        if src_id and tgt_id:
            _upsert_rel(conn, src_id, "LINKS_TO", tgt_id, {
                "text": link["link_text"],
                "depth": link["depth"],
            })
            stats["relationships"] += 1

    return stats


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_website_entities(force: bool = False) -> dict:
    """
    Build full knowledge graph from Excel + website data.
    Always runs even if there are no scraped pages.
    """
    conn = get_conn()
    total = {"entities": 0, "relationships": 0}

    try:
        # Clear existing graph so we start fresh
        conn.execute("DELETE FROM relationships")
        conn.execute("DELETE FROM entities")

        # Phase 1: Academic graph (always available from Excel)
        s1 = _build_academic_graph(conn)
        total["entities"]      += s1["entities"]
        total["relationships"] += s1["relationships"]
        logger.info(f"[Graph] Academic: {s1['entities']} entities, {s1['relationships']} rels")

        # Get college entity id for Phase 2
        college_row = conn.execute(
            "SELECT id FROM entities WHERE name='Sri Krishna College of Technology'"
        ).fetchone()
        college_id = college_row["id"] if college_row else None

        # Phase 2: Website graph (optional)
        page_count = conn.execute("SELECT COUNT(*) FROM scraped_pages").fetchone()[0]
        s2 = {"entities": 0, "relationships": 0}
        if page_count > 0 and college_id:
            s2 = _build_website_graph(conn, college_id)
            total["entities"]      += s2["entities"]
            total["relationships"] += s2["relationships"]
            logger.info(f"[Graph] Website: {s2['entities']} entities, {s2['relationships']} rels")

        conn.commit()
        logger.info(
            f"[Graph] Total: {total['entities']} entities, "
            f"{total['relationships']} relationships"
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "status":                "ok",
        "entities_created":      total["entities"],
        "relationships_created": total["relationships"],
        "pages_processed":       page_count if 'page_count' in dir() else 0,
    }
