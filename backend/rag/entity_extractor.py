import re
from collections import defaultdict
from typing import Any

from backend.models import Chunk


DEPARTMENT_PATTERNS = [
    "Computer Science and Engineering",
    "Information Technology",
    "Artificial Intelligence",
    "Electronics and Communication Engineering",
    "Electrical and Electronics Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Management Studies",
]

COMPANY_HINTS = ["TCS", "Infosys", "Wipro", "Cognizant", "Accenture", "Zoho", "Amazon", "IBM", "Capgemini"]

COURSE_KEYWORDS = [
    "Civil Engineering",
    "Computer Science",
    "Information Technology",
    "Artificial Intelligence",
    "Data Science",
    "Cyber Security",
    "Electronics and Communication",
    "Electrical and Electronics",
    "Mechanical Engineering",
    "Structural Engineering",
    "Power Systems",
    "Engineering Design",
]

FACULTY_ROLE_WORDS = {
    "Project",
    "Manager",
    "Deputy",
    "Controller",
    "Coordinator",
    "Director",
    "Principal",
    "Professor",
    "Assistant",
    "Associate",
    "Head",
    "HoD",
}

EVENT_DEPARTMENTS = r"(?:AIDS|AIML|CSE|ECE|EEE|IT|MBA|MECH|CIVIL|SOM)"


class EntityExtractor:
    """Lightweight rules keep ingestion usable on laptops without calling the LLM per chunk."""

    def extract(self, chunks: list[Chunk]) -> dict[str, list[dict[str, Any]]]:
        nodes: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        relationships: list[dict[str, Any]] = []

        for chunk in chunks:
            departments = self._departments(chunk.text)
            faculty = self._faculty(chunk.text)
            courses = self._courses(chunk.text)
            companies = self._companies(chunk.text)
            events = self._events(chunk.text)

            for label, values in [
                ("Department", departments),
                ("Faculty", faculty),
                ("Course", courses),
                ("Company", companies),
                ("Event", events),
            ]:
                for value in values:
                    nodes[label][value] = {"name": value, "source_url": chunk.source_url}

            for department in departments:
                for person in faculty:
                    relationships.append(self._rel(person, department, "FACULTY_BELONGS_TO_DEPARTMENT", chunk.source_url))
                for course in courses:
                    relationships.append(self._rel(department, course, "DEPARTMENT_OFFERS_COURSE", chunk.source_url))
                for company in companies:
                    relationships.append(self._rel(company, department, "COMPANY_HIRED_FROM_DEPARTMENT", chunk.source_url))
                for event in events:
                    relationships.append(self._rel(event, department, "EVENT_CONDUCTED_BY_DEPARTMENT", chunk.source_url))
            for person in faculty:
                for course in courses[:3]:
                    relationships.append(self._rel(person, course, "FACULTY_TEACHES_COURSE", chunk.source_url))

        return {
            "Department": list(nodes["Department"].values()),
            "Faculty": list(nodes["Faculty"].values()),
            "Company": list(nodes["Company"].values()),
            "Course": list(nodes["Course"].values()),
            "Event": list(nodes["Event"].values()),
            "relationships": self._dedupe_relationships(relationships),
        }

    def candidate_names(self, question: str) -> list[str]:
        values = set(self._departments(question) + self._faculty(question) + self._companies(question))
        values.update(word for word in re.findall(r"[A-Z][A-Za-z& ]{3,40}", question) if len(word.split()) <= 5)
        return list(values)[:8]

    def _departments(self, text: str) -> list[str]:
        lowered = text.lower()
        return [name for name in DEPARTMENT_PATTERNS if name.lower() in lowered]

    def _faculty(self, text: str) -> list[str]:
        pattern = r"\b(?:Dr|Prof|Mr|Ms|Mrs)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}"
        names: list[str] = []
        for match in re.findall(pattern, text):
            parts = match.split()
            title = parts[0]
            name_parts: list[str] = []
            for part in parts[1:]:
                if part.strip(".") in FACULTY_ROLE_WORDS:
                    break
                name_parts.append(part)
            if name_parts:
                names.append(" ".join([title, *name_parts]))
        return self._unique(names)

    def _courses(self, text: str) -> list[str]:
        patterns = [
            (
                r"\b((?:B\.?E\.?|B\.?Tech\.?|M\.?E\.?|M\.?Tech\.?)\s+"
                r"[A-Z][A-Za-z &().]{2,90}?)"
                r"(?=\s+(?:B\.?E\.?|B\.?Tech\.?|M\.?E\.?|M\.?Tech\.?|MBA|"
                r"Doctorate|About|HoD|Department|Faculty|Placements|Research)|$)"
            ),
            r"\bMBA\b",
        ]
        values: list[str] = []
        for pattern in patterns:
            values.extend(re.findall(pattern, text))

        courses: list[str] = []
        for value in values:
            course = re.sub(r"\s+", " ", value).strip(" .,-")
            course = re.split(
                r"\s+(?:UG Programmes|PG Programmes|Science and Humanities|Master of|Doctorate|About)\b",
                course,
                maxsplit=1,
            )[0].strip(" .,-")
            if course == "MBA":
                courses.append(course)
                continue
            if re.search(r"\b(are|winner|winners|student|students|free)\b", course, flags=re.IGNORECASE):
                continue
            if any(keyword.lower() in course.lower() for keyword in COURSE_KEYWORDS):
                courses.append(course[:80])
        return self._unique(courses)

    def _companies(self, text: str) -> list[str]:
        lowered = text.lower()
        return [company for company in COMPANY_HINTS if company.lower() in lowered]

    def _events(self, text: str) -> list[str]:
        matches: list[str] = []
        date_first_pattern = (
            r"\b(?:webinar|seminar|workshop|conference|symposium|hackathon|fdp)\s+"
            r"\d{1,2}\s+[A-Z][a-z]{2}\s+"
            r"([A-Z][A-Za-z0-9 &:,'’()./-]{5,90}?)"
            r"(?=\s+(?:" + EVENT_DEPARTMENTS + r"\s+)?"
            r"(?:webinar|seminar|workshop|conference|symposium|hackathon|fdp|$))"
        )
        matches.extend(re.findall(date_first_pattern, text, flags=re.IGNORECASE))
        if "Smart India Hackathon" in text:
            matches.append("Smart India Hackathon")

        events: list[str] = []
        for match in matches:
            event = re.sub(r"\b" + EVENT_DEPARTMENTS + r"\b", " ", match)
            event = re.sub(r"\s+", " ", event).strip(" .,-")
            if re.search(r"\b[A-Z]$", event):
                continue
            if len(event.split()) >= 2 and "brochure" not in event.lower():
                events.append(event[:90])
        return self._unique(events)

    def _rel(self, source: str, target: str, rel_type: str, source_url: str) -> dict[str, str]:
        return {"source": source, "target": target, "type": rel_type, "source_url": source_url}

    def _unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = re.sub(r"\s+", " ", value).strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                result.append(normalized)
        return result[:20]

    def _dedupe_relationships(self, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        result: list[dict[str, Any]] = []
        for rel in relationships:
            key = (rel["source"].lower(), rel["type"], rel["target"].lower())
            if key not in seen:
                seen.add(key)
                result.append(rel)
        return result
