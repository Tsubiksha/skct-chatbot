"""
text_cleaner.py — Improved HTML → clean structured text for Graph RAG.

Improvements:
  - Strips header/footer/nav/aside *blocks* (not just tags)
  - Preserves heading hierarchy as section markers
  - Better table extraction (row | col format)
  - Aggressive noise removal (social share, cookie banners, etc.)
  - Returns richer metadata for downstream chunking
"""

import re
import logging
import hashlib
import json

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

logger = logging.getLogger(__name__)

# ── Tags to remove entirely ──────────────────────────────────────────────────
_REMOVE_TAGS = [
    "script", "style", "noscript", "iframe", "svg", "head",
    "button", "form", "input", "select", "textarea",
    "canvas", "video", "audio", "picture", "source",
    "link", "meta",
]

# ── Block-level elements that are likely navigation / chrome ─────────────────
_NAV_BLOCK_ATTRS = re.compile(
    r"\b(nav|navbar|menu|header|footer|sidebar|breadcrumb|pagination|"
    r"cookie|banner|advertisement|social|share|widget|modal|overlay|"
    r"popup|back-to-top|scroll-top|sticky|fixed-header|site-header|"
    r"site-footer|skip-link|skipnav|topbar|toolbar)\b",
    re.I,
)

# ── Noise phrases to drop after text extraction ──────────────────────────────
_NOISE_PHRASES = [
    "skip to content", "skip to main", "skip navigation",
    "cookie policy", "accept cookies", "we use cookies",
    "privacy policy", "terms of service", "all rights reserved",
    "powered by wordpress", "back to top", "scroll to top",
    "read more", "click here", "learn more", "view all",
    "home »", "you are here:", "breadcrumb",
    "follow us", "subscribe", "newsletter",
    "share this", "like this", "tweet", "facebook", "instagram",
    "copyright ©", "site map", "sitemap",
]

# ── Page type detection rules (URL + title + content) ───────────────────────
_PAGE_TYPE_RULES = [
    ("home",             ["home", "welcome", "index"]),
    ("principal",        ["principal", "director", "founder", "chairman", "secretary"]),
    ("management",       ["management", "trustees", "board", "governing body"]),
    ("vision_mission",   ["vision", "mission", "objective", "goal", "core values"]),
    ("about",            ["about", "institution", "overview", "history", "profile",
                          "established", "founded", "accreditation", "naac", "nba"]),
    ("department",       ["department", "dept", "cse", "ece", "eee", "it dept",
                          "mechanical", "civil", "aids", "ai&ds", "artificial intelligence",
                          "biotechnology", "automobile", "chemical"]),
    ("faculty",          ["faculty", "staff", "professor", "hod", "associate professor",
                          "assistant professor", "teaching staff"]),
    ("placement",        ["placement", "career", "campus recruitment", "placed",
                          "placement cell", "placement record", "placement statistics",
                          "average package", "highest package"]),
    ("recruiter",        ["recruiter", "companies", "recruiters", "top companies",
                          "our recruiters", "hiring companies", "visiting companies"]),
    ("training",         ["training", "internship", "skill development", "soft skill",
                          "aptitude", "bridge course", "placement training"]),
    ("academic_calendar", ["academic calendar", "calendar", "schedule", "important dates"]),
    ("exams",            ["exam", "examination", "internal assessment", "coe",
                          "controller of examination", "revaluation", "arrear"]),
    ("regulations",      ["regulation", "syllabus", "curriculum", "anna university",
                          "r2021", "r2017", "credit system"]),
    ("research",         ["research", "publication", "journal", "conference", "patent",
                          "innovation", "incubation", "startup", "ipr", "funded projects"]),
    ("industry_connect", ["industry", "mou", "collaboration", "partner", "connect",
                          "industry institute"]),
    ("event",            ["event", "symposium", "workshop", "hackathon", "news",
                          "announcement", "fest", "seminar", "guest lecture", "webinar"]),
    ("contact",          ["contact", "address", "phone", "email", "location", "map",
                          "reach us", "contact us", "get in touch"]),
    ("academics",        ["academics", "curriculum", "semester", "course", "programme",
                          "ug", "pg", "b.e", "b.tech", "m.e", "mba", "mca"]),
    ("hostel",           ["hostel", "accommodation", "residence", "dormitory"]),
    ("library",          ["library", "learning centre", "digital library", "books", "e-journal"]),
    ("sports",           ["sports", "athletic", "cricket", "football", "basketball",
                          "badminton", "gym", "yoga", "outdoor", "indoor"]),
    ("alumni",           ["alumni", "alumnae", "graduate", "former student", "old students"]),
    ("scholarship",      ["scholarship", "financial aid", "fee concession", "merit"]),
]


# ── Public API ───────────────────────────────────────────────────────────────

def detect_page_type(url: str, title: str, content: str) -> str:
    """Return a page_type string based on URL, title, and content keywords."""
    if re.match(r"^https?://(www\.)?skct\.edu\.in/?$", url.rstrip("/"), re.I):
        return "home"
    # URL path takes priority
    url_lower = url.lower()
    for page_type, keywords in _PAGE_TYPE_RULES:
        if any(f"/{kw.replace(' ', '-')}" in url_lower or
               f"/{kw.replace(' ', '_')}" in url_lower
               for kw in keywords):
            return page_type
    combined = (url + " " + title + " " + content[:600]).lower()
    for page_type, keywords in _PAGE_TYPE_RULES:
        if any(kw in combined for kw in keywords):
            return page_type
    return "general"


def clean_html(html: str, url: str = "") -> tuple[str, str]:
    """
    Parse HTML, strip navigation/chrome, extract clean structured text.
    Returns (title, cleaned_text).
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Extract title early
    title_tag = soup.find("title")
    raw_title = title_tag.get_text(strip=True) if title_tag else ""
    raw_title = re.sub(r"\s*[|\-–]\s*SKCT.*$", "", raw_title, flags=re.I).strip()
    raw_title = re.sub(r"\s+", " ", raw_title).strip()

    # 2. Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # 3. Remove script/style/meta tags first
    for tag_name in _REMOVE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # 4. Remove navigation/chrome blocks (by id/class heuristics)
    for el in soup.find_all(True):
        if getattr(el, "attrs", None) is None:
            continue
        el_id    = " ".join(el.get("id", "").split()) if el.get("id") else ""
        el_class = " ".join(el.get("class", [])) if el.get("class") else ""
        combined = f"{el_id} {el_class}"
        if _NAV_BLOCK_ATTRS.search(combined):
            el.decompose()

    # 5. Remove semantic nav/header/footer/aside elements
    for tag_name in ("header", "footer", "nav", "aside"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # 6. Extract structured JSON-LD metadata
    metadata_lines = _extract_jsonld_metadata(soup)

    # 7. Find main content area
    main = (
        soup.find("main") or
        soup.find(id=re.compile(r"^(main|content|primary|page-content|main-content)$", re.I)) or
        soup.find(class_=re.compile(r"\b(main-content|page-content|entry-content|post-content|article-content)\b", re.I)) or
        soup.find("article") or
        soup.find(class_=re.compile(r"\b(entry|post|article)\b", re.I)) or
        soup.body or
        soup
    )

    # 8. Extract structured text preserving headings and tables
    text_parts = []
    if metadata_lines:
        text_parts.extend(metadata_lines)

    _extract_structured_text(main, text_parts)

    # 9. Clean and deduplicate lines
    lines = _clean_lines(text_parts)

    cleaned = "\n".join(lines)
    if not raw_title and lines:
        raw_title = lines[0][:120]

    return raw_title, cleaned


def content_hash(text: str) -> str:
    """SHA-256 hash of cleaned content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_useful(text: str, min_chars: int = 120) -> bool:
    """Return True if the cleaned text has enough useful content."""
    return len(text.strip()) >= min_chars


# ── Internal helpers ─────────────────────────────────────────────────────────

def _extract_structured_text(element, parts: list[str], depth: int = 0):
    """
    Recursively walk the DOM, extracting text with structural markers.
    Headings get a '## ' prefix so chunker can detect section boundaries.
    Tables are rendered as pipe-delimited rows.
    """
    if element is None:
        return

    if isinstance(element, NavigableString):
        text = str(element).strip()
        if text and len(text) > 2:
            parts.append(text)
        return

    tag_name = getattr(element, "name", None)
    if not tag_name:
        return

    # Headings — emit as section markers
    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        heading_text = element.get_text(" ", strip=True)
        if heading_text and len(heading_text) > 2:
            level = int(tag_name[1])
            prefix = "#" * level
            parts.append(f"\n{prefix} {heading_text}\n")
        return

    # Tables — render as pipe-delimited
    if tag_name == "table":
        table_text = _extract_table(element)
        if table_text:
            parts.append(table_text)
        return

    # Lists — add bullet markers
    if tag_name in ("ul", "ol"):
        for li in element.find_all("li", recursive=False):
            li_text = li.get_text(" ", strip=True)
            if li_text and len(li_text) > 2:
                parts.append(f"• {li_text}")
        return

    # Paragraphs and divs — recurse
    for child in element.children:
        _extract_structured_text(child, parts, depth + 1)


def _extract_table(table) -> str:
    """Extract a table as pipe-delimited text rows."""
    rows = []
    for tr in table.find_all("tr"):
        cells = []
        for cell in tr.find_all(["th", "td"]):
            cell_text = cell.get_text(" ", strip=True)
            cells.append(re.sub(r"\s+", " ", cell_text).strip())
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows) if rows else ""


def _extract_jsonld_metadata(soup: BeautifulSoup) -> list[str]:
    """Extract name/description/address/telephone/email from JSON-LD."""
    values: list[str] = []
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        try:
            data = json.loads(script.string or "")
            _flatten_jsonld(data, values)
        except Exception:
            continue
    return values


def _flatten_jsonld(data, values: list[str]):
    if isinstance(data, dict):
        for key in ("name", "description", "address", "telephone", "email",
                    "streetAddress", "addressLocality", "postalCode"):
            value = data.get(key)
            if isinstance(value, dict):
                _flatten_jsonld(value, values)
            elif isinstance(value, str) and len(value) > 3:
                values.append(f"{key}: {value}")
        for value in data.values():
            if isinstance(value, (dict, list)):
                _flatten_jsonld(value, values)
    elif isinstance(data, list):
        for item in data:
            _flatten_jsonld(item, values)


def _clean_lines(raw_parts: list[str]) -> list[str]:
    """Normalize, deduplicate, and filter noise from extracted text lines."""
    lines = []
    seen: set[str] = set()

    for part in raw_parts:
        for line in part.splitlines():
            # Normalize whitespace
            line = line.replace("\u00a0", " ").replace("\xa0", " ")
            line = re.sub(r"\s+", " ", line).strip()

            if not line or len(line) < 3:
                continue

            # Skip navigation noise
            line_lower = line.lower()
            if any(noise in line_lower for noise in _NOISE_PHRASES):
                continue

            # Skip very short non-alphabetic lines (pagination, icons)
            if len(line) < 8 and not re.search(r"[a-zA-Z]{3}", line):
                continue

            # Skip lines that are just URLs
            if re.match(r"^https?://\S+$", line):
                continue

            # Deduplicate (but preserve heading markers)
            key = line_lower if not line.startswith("#") else line
            if key in seen:
                continue
            seen.add(key)

            lines.append(line)

    return lines
