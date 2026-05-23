import re
from dataclasses import dataclass
from typing import Any

from backend.app.graph.neo4j_service import Neo4jService
from backend.app.graph_rag.db import get_connection, init_db

DEPARTMENT_ALIASES = {
    "cse": "Computer Science and Engineering",
    "computer science": "Computer Science and Engineering",
    "ai": "Artificial Intelligence and Data Science",
    "aids": "Artificial Intelligence and Data Science",
    "ai & ds": "Artificial Intelligence and Data Science",
    "ece": "Electronics and Communication Engineering",
    "eee": "Electrical and Electronics Engineering",
    "it": "Information Technology",
    "civil": "Civil Engineering",
    "mechanical": "Mechanical Engineering",
}

COURSE_PATTERNS = [
    r"\bArtificial Intelligence\b",
    r"\bMachine Learning\b",
    r"\bData Science\b",
    r"\bComputer Science\b",
    r"\bElectronics\b",
    r"\bCivil Engineering\b",
    r"\bMechanical Engineering\b",
]

COMPANIES = ["TCS", "Infosys", "Wipro", "Cognizant", "Accenture", "Zoho", "Amazon", "IBM", "Capgemini", "HCL"]


@dataclass
class BuildSummary:
    pages_processed: int = 0
    nodes_created: int = 0
    relationships_created: int = 0


class GraphBuilder:
    """Builds Neo4j graph data from the separate SQLite GraphRAG database."""

    def __init__(self, neo4j: Neo4jService | None = None):
        self.neo4j = neo4j or Neo4jService()

    def build_from_sqlite(self) -> dict[str, int]:
        init_db()
        summary = BuildSummary()
        self._create_constraints()
        self.neo4j.create_node("College", "Sri Krishna College of Technology", {"short_name": "SKCT"})
        summary.nodes_created += 1

        with get_connection() as connection:
            pages = connection.execute("SELECT id, title, url, page_type, content FROM scraped_pages").fetchall()
            relationships = connection.execute(
                """
                SELECT source_type, source_name, relationship_type, target_type, target_name, page_id
                FROM relationships
                """
            ).fetchall()

        for page in pages:
            summary.pages_processed += 1
            self._insert_page_graph(dict(page), summary)

        for relationship in relationships:
            mapped = self._map_sqlite_relationship(dict(relationship))
            if mapped:
                self.neo4j.create_relationship(**mapped)
                summary.relationships_created += 1

        return summary.__dict__

    def _create_constraints(self) -> None:
        labels = ["College", "Department", "Faculty", "Course", "Company", "Placement", "Event", "Recruiter", "Training", "Regulation"]
        for label in labels:
            self.neo4j.run_query(f"CREATE CONSTRAINT {label.lower()}_name IF NOT EXISTS FOR (n:{label}) REQUIRE n.name IS UNIQUE")

    def _insert_page_graph(self, page: dict[str, Any], summary: BuildSummary) -> None:
        text = f"{page['title']} {page['url']} {page['content']}"
        lowered = text.lower()
        page_type = page["page_type"]
        source_url = page["url"]

        if page_type == "placement":
            self.neo4j.create_node("Placement", "SKCT Placements", {"source_url": source_url})
            self.neo4j.create_relationship("Placement", "SKCT Placements", "PART_OF", "College", "Sri Krishna College of Technology", {"source_url": source_url})
            summary.nodes_created += 1
            summary.relationships_created += 1

        if page_type == "training" or "training" in lowered:
            self.neo4j.create_node("Training", "SKCT Training Programs", {"source_url": source_url})
            summary.nodes_created += 1

        if page_type == "event":
            self.neo4j.create_node("Event", page["title"], {"source_url": source_url})
            summary.nodes_created += 1

        if page_type == "regulations":
            self.neo4j.create_node("Regulation", page["title"], {"source_url": source_url})
            summary.nodes_created += 1

        departments = self._detect_departments(lowered)
        courses = self._detect_courses(text)
        companies = self._detect_companies(text)
        faculty = self._detect_faculty(text)

        for department in departments:
            self.neo4j.create_node("Department", department, {"source_url": source_url})
            self.neo4j.create_relationship("Department", department, "PART_OF", "College", "Sri Krishna College of Technology", {"source_url": source_url})
            summary.nodes_created += 1
            summary.relationships_created += 1

            for course in courses:
                self.neo4j.create_relationship("Department", department, "DEPARTMENT_OFFERS_COURSE", "Course", course, {"source_url": source_url})
                summary.relationships_created += 1

            for company in companies:
                self.neo4j.create_relationship("Company", company, "COMPANY_HIRED_FROM_DEPARTMENT", "Department", department, {"source_url": source_url})
                summary.relationships_created += 1

            if "training" in lowered:
                self.neo4j.create_relationship("Training", "SKCT Training Programs", "TRAINING_FOR_DEPARTMENT", "Department", department, {"source_url": source_url})
                summary.relationships_created += 1

            if page_type == "regulations":
                self.neo4j.create_relationship("Regulation", page["title"], "REGULATION_APPLIES_TO_DEPARTMENT", "Department", department, {"source_url": source_url})
                summary.relationships_created += 1

            if page_type == "event":
                self.neo4j.create_relationship("Event", page["title"], "EVENT_CONDUCTED_BY_DEPARTMENT", "Department", department, {"source_url": source_url})
                summary.relationships_created += 1

            for person in faculty:
                self.neo4j.create_relationship("Faculty", person, "FACULTY_BELONGS_TO_DEPARTMENT", "Department", department, {"source_url": source_url})
                summary.relationships_created += 1

        for course in courses:
            self.neo4j.create_node("Course", course, {"source_url": source_url})
            summary.nodes_created += 1

        for company in companies:
            self.neo4j.create_node("Company", company, {"source_url": source_url})
            self.neo4j.create_node("Recruiter", company, {"source_url": source_url})
            summary.nodes_created += 2

        for person in faculty:
            self.neo4j.create_node("Faculty", person, {"source_url": source_url})
            for course in courses[:2]:
                self.neo4j.create_relationship("Faculty", person, "FACULTY_TEACHES_COURSE", "Course", course, {"source_url": source_url})
                summary.relationships_created += 1
            summary.nodes_created += 1

    def _map_sqlite_relationship(self, relationship: dict[str, Any]) -> dict[str, Any] | None:
        type_map = {
            ("Department", "PART_OF", "College"): "PART_OF",
            ("Placement", "PART_OF", "College"): "PART_OF",
            ("Page", "MENTIONS", "Department"): "MENTIONS",
            ("Page", "MENTIONS", "Recruiter"): "MENTIONS",
        }
        rel_type = type_map.get((relationship["source_type"], relationship["relationship_type"], relationship["target_type"]))
        if not rel_type:
            return None
        return {
            "source_label": relationship["source_type"],
            "source_name": relationship["source_name"],
            "relationship_type": rel_type,
            "target_label": relationship["target_type"],
            "target_name": relationship["target_name"],
            "properties": {"sqlite_page_id": relationship["page_id"]},
        }

    def _detect_departments(self, lowered_text: str) -> list[str]:
        return sorted({name for alias, name in DEPARTMENT_ALIASES.items() if alias in lowered_text})

    def _detect_courses(self, text: str) -> list[str]:
        courses = set()
        for pattern in COURSE_PATTERNS:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                courses.add(match.title())
        return sorted(courses)

    def _detect_companies(self, text: str) -> list[str]:
        lowered = text.lower()
        return [company for company in COMPANIES if company.lower() in lowered]

    def _detect_faculty(self, text: str) -> list[str]:
        names = re.findall(r"\b(?:Dr|Prof|Mr|Ms|Mrs)\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}", text)
        return sorted({re.sub(r"\s+", " ", name).strip() for name in names})[:30]
