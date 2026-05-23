import re

DEPARTMENTS = {
    "CSE": "Computer Science and Engineering",
    "AI & DS": "Artificial Intelligence and Data Science",
    "AIDS": "Artificial Intelligence and Data Science",
    "ECE": "Electronics and Communication Engineering",
    "EEE": "Electrical and Electronics Engineering",
    "IT": "Information Technology",
    "Civil": "Civil Engineering",
    "Mechanical": "Mechanical Engineering",
}

RECRUITERS = [
    "TCS",
    "Infosys",
    "Wipro",
    "Cognizant",
    "Accenture",
    "Zoho",
    "Amazon",
    "IBM",
    "Capgemini",
    "HCL",
]


def detect_page_type(url: str, title: str, content: str) -> str:
    haystack = f"{url} {title} {content[:2000]}".lower()
    checks = [
        ("placement", ["placement", "placements"]),
        ("recruiter", ["recruiter", "recruiters", "companies visited"]),
        ("training", ["training", "career development"]),
        ("department", ["department", "cse", "ece", "eee", "aids", "mechanical", "civil"]),
        ("faculty", ["faculty", "professor", "assistant professor"]),
        ("academics", ["academics", "course", "curriculum", "program"]),
        ("regulations", ["regulation", "regulations", "syllabus"]),
        ("event", ["event", "events", "seminar", "workshop", "conference"]),
        ("contact", ["contact", "phone", "email"]),
        ("research", ["research", "publication", "patent"]),
        ("about", ["vision", "mission", "about"]),
    ]
    for page_type, keywords in checks:
        if any(keyword in haystack for keyword in keywords):
            return page_type
    return "home" if url.rstrip("/").endswith("skct.edu.in") else "general"


def extract_entities_and_relationships(page_id: int, title: str, url: str, page_type: str, content: str) -> tuple[list[dict], list[dict]]:
    entities: list[dict] = [
        {"entity_type": "College", "name": "Sri Krishna College of Technology", "page_id": page_id},
        {"entity_type": "Page", "name": title, "page_id": page_id},
    ]
    relationships: list[dict] = [
        {
            "source_type": "College",
            "source_name": "Sri Krishna College of Technology",
            "relationship_type": "HAS_PAGE",
            "target_type": "Page",
            "target_name": title,
            "page_id": page_id,
        }
    ]

    haystack = f"{title} {url} {content}"
    lowered = haystack.lower()

    for alias, full_name in DEPARTMENTS.items():
        if alias.lower() in lowered or full_name.lower() in lowered:
            entities.append({"entity_type": "Department", "name": full_name, "page_id": page_id})
            relationships.append(_rel("Page", title, "MENTIONS", "Department", full_name, page_id))
            relationships.append(_rel("Department", full_name, "PART_OF", "College", "Sri Krishna College of Technology", page_id))

    if "placement" in lowered:
        entities.append({"entity_type": "Placement", "name": "SKCT Placements", "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Placement", "SKCT Placements", page_id))
        relationships.append(_rel("Placement", "SKCT Placements", "PART_OF", "College", "Sri Krishna College of Technology", page_id))

    if "training" in lowered:
        entities.append({"entity_type": "Training", "name": "Training Programs", "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Training", "Training Programs", page_id))

    for recruiter in RECRUITERS:
        if recruiter.lower() in lowered:
            entities.append({"entity_type": "Recruiter", "name": recruiter, "page_id": page_id})
            relationships.append(_rel("Page", title, "MENTIONS", "Recruiter", recruiter, page_id))

    faculty_names = re.findall(r"\b(?:Dr|Prof|Mr|Ms|Mrs)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}", content)
    for name in faculty_names[:25]:
        entities.append({"entity_type": "Faculty", "name": re.sub(r"\s+", " ", name).strip(), "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Faculty", name, page_id))

    if page_type == "event":
        entities.append({"entity_type": "Event", "name": title, "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Event", title, page_id))

    if page_type == "regulations":
        entities.append({"entity_type": "Regulation", "name": title, "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Regulation", title, page_id))

    if page_type == "contact":
        entities.append({"entity_type": "Contact", "name": "SKCT Contact Details", "page_id": page_id})
        relationships.append(_rel("Page", title, "MENTIONS", "Contact", "SKCT Contact Details", page_id))

    return _unique(entities), _unique_relationships(relationships)


def _rel(source_type: str, source_name: str, rel_type: str, target_type: str, target_name: str, page_id: int) -> dict:
    return {
        "source_type": source_type,
        "source_name": source_name,
        "relationship_type": rel_type,
        "target_type": target_type,
        "target_name": target_name,
        "page_id": page_id,
    }


def _unique(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = (item["entity_type"], item["name"], item["page_id"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_relationships(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = (
            item["source_type"],
            item["source_name"],
            item["relationship_type"],
            item["target_type"],
            item["target_name"],
            item["page_id"],
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
