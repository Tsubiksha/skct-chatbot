from typing import Any

from backend.app.graph.neo4j_service import Neo4jService


class GraphQueries:
    def __init__(self, neo4j: Neo4jService | None = None):
        self.neo4j = neo4j or Neo4jService()

    def get_department_relationships(self, department: str | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE $department IS NULL OR toLower(d.name) CONTAINS toLower($department)"
        return self.neo4j.run_query(
            f"""
            MATCH (d:Department)-[r]-(n)
            {where_clause}
            RETURN d.name AS department, type(r) AS relationship,
                   labels(n)[0] AS related_type, n.name AS related_name
            LIMIT 50
            """,
            {"department": department},
        )

    def get_faculty_relationships(self, faculty: str | None = None) -> list[dict[str, Any]]:
        return self.neo4j.run_query(
            """
            MATCH (f:Faculty)-[r]-(n)
            WHERE $faculty IS NULL OR toLower(f.name) CONTAINS toLower($faculty)
            RETURN f.name AS faculty, type(r) AS relationship,
                   labels(n)[0] AS related_type, n.name AS related_name
            LIMIT 50
            """,
            {"faculty": faculty},
        )

    def get_company_relationships(self, company: str | None = None) -> list[dict[str, Any]]:
        return self.neo4j.run_query(
            """
            MATCH (c:Company)-[r]-(n)
            WHERE $company IS NULL OR toLower(c.name) CONTAINS toLower($company)
            RETURN c.name AS company, type(r) AS relationship,
                   labels(n)[0] AS related_type, n.name AS related_name
            LIMIT 50
            """,
            {"company": company},
        )

    def get_related_entities(self, name: str, depth: int = 1) -> list[dict[str, Any]]:
        depth = max(1, min(depth, 3))
        return self.neo4j.run_query(
            f"""
            MATCH path = (n)-[*1..{depth}]-(m)
            WHERE toLower(n.name) CONTAINS toLower($name)
            RETURN labels(n)[0] AS source_type, n.name AS source,
                   [rel IN relationships(path) | type(rel)] AS relationships,
                   labels(m)[0] AS target_type, m.name AS target,
                   length(path) AS hops
            LIMIT 50
            """,
            {"name": name},
        )

    def multi_hop_search(self, question: str) -> list[dict[str, Any]]:
        lowered = question.lower()
        if "compan" in lowered or "recruit" in lowered or "hired" in lowered:
            return self.neo4j.run_query(
                """
                MATCH (company:Company)-[:COMPANY_HIRED_FROM_DEPARTMENT]->(department:Department)
                OPTIONAL MATCH (department)-[:DEPARTMENT_OFFERS_COURSE]->(course:Course)
                RETURN company.name AS company,
                       department.name AS department,
                       collect(DISTINCT course.name) AS courses
                LIMIT 50
                """
            )

        if "faculty" in lowered:
            return self.neo4j.run_query(
                """
                MATCH (faculty:Faculty)-[:FACULTY_BELONGS_TO_DEPARTMENT]->(department:Department)
                OPTIONAL MATCH (faculty)-[:FACULTY_TEACHES_COURSE]->(course:Course)
                RETURN faculty.name AS faculty,
                       department.name AS department,
                       collect(DISTINCT course.name) AS courses
                LIMIT 50
                """
            )

        if "training" in lowered:
            return self.neo4j.run_query(
                """
                MATCH (training:Training)-[:TRAINING_FOR_DEPARTMENT]->(department:Department)
                RETURN training.name AS training, department.name AS department
                LIMIT 50
                """
            )

        return self.neo4j.run_query(
            """
            MATCH (n)-[r]-(m)
            RETURN labels(n)[0] AS source_type, n.name AS source,
                   type(r) AS relationship,
                   labels(m)[0] AS target_type, m.name AS target
            LIMIT 50
            """
        )

    def stats(self) -> dict[str, int]:
        rows = self.neo4j.run_query(
            """
            RETURN
              count { MATCH (:College) } AS colleges,
              count { MATCH (:Department) } AS departments,
              count { MATCH (:Faculty) } AS faculty,
              count { MATCH (:Course) } AS courses,
              count { MATCH (:Company) } AS companies,
              count { MATCH (:Placement) } AS placements,
              count { MATCH (:Event) } AS events,
              count { MATCH (:Recruiter) } AS recruiters,
              count { MATCH (:Training) } AS training,
              count { MATCH (:Regulation) } AS regulations,
              count { MATCH ()-[r]->() } AS relationships
            """
        )
        return rows[0] if rows else {}
