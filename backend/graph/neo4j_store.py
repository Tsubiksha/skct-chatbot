from collections import Counter
from typing import Any

from neo4j import AsyncGraphDatabase


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str, database: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    async def close(self) -> None:
        await self.driver.close()

    async def health(self) -> str:
        try:
            await self.driver.verify_connectivity()
            return "ok"
        except Exception:
            return "unavailable"

    async def reset(self) -> None:
        async with self.driver.session(database=self.database) as session:
            await session.run("MATCH (n) DETACH DELETE n")

    async def apply_constraints(self) -> None:
        statements = [
            "CREATE CONSTRAINT department_name IF NOT EXISTS FOR (n:Department) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT faculty_name IF NOT EXISTS FOR (n:Faculty) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT company_name IF NOT EXISTS FOR (n:Company) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT course_name IF NOT EXISTS FOR (n:Course) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT event_name IF NOT EXISTS FOR (n:Event) REQUIRE n.name IS UNIQUE",
        ]
        async with self.driver.session(database=self.database) as session:
            for statement in statements:
                await session.run(statement)

    async def upsert_extracted_graph(self, extracted: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        await self.apply_constraints()
        counts = Counter()

        async with self.driver.session(database=self.database) as session:
            for label in ["Department", "Faculty", "Company", "Course", "Event"]:
                for node in extracted.get(label, []):
                    await session.run(
                        f"MERGE (n:{label} {{name: $name}}) "
                        "SET n.source_url = coalesce(n.source_url, $source_url)",
                        name=node["name"],
                        source_url=node.get("source_url"),
                    )
                    counts[label] += 1

            for rel in extracted.get("relationships", []):
                await session.run(
                    self._relationship_merge_query(rel["type"]),
                    source=rel["source"],
                    target=rel["target"],
                    source_url=rel.get("source_url"),
                )
                counts[rel["type"]] += 1

        return dict(counts)

    async def query_context(self, names: list[str], limit: int = 12) -> list[dict[str, Any]]:
        if not names:
            return []

        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (n)-[r]-(m)
                WHERE any(name IN $names WHERE toLower(n.name) CONTAINS toLower(name)
                   OR toLower(m.name) CONTAINS toLower(name))
                RETURN labels(n)[0] AS source_label, n.name AS source,
                       type(r) AS relationship,
                       labels(m)[0] AS target_label, m.name AS target
                LIMIT $limit
                """,
                names=names,
                limit=limit,
            )
            return [dict(record) async for record in result]

    async def stats(self) -> dict[str, int]:
        async with self.driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (n)
                WITH
                  count { MATCH (:Department) } AS departments,
                  count { MATCH (:Faculty) } AS faculty,
                  count { MATCH (:Course) } AS courses,
                  count { MATCH (:Company) } AS companies,
                  count { MATCH (:Event) } AS events,
                  count { MATCH ()-[r]->() } AS relationships
                RETURN departments, faculty, courses, companies, events, relationships
                """
            )
            record = await result.single()
            if record is None:
                return {}
            return {key: int(record[key]) for key in record.keys()}

    def _relationship_merge_query(self, rel_type: str) -> str:
        allowed = {
            "FACULTY_BELONGS_TO_DEPARTMENT",
            "FACULTY_TEACHES_COURSE",
            "COMPANY_HIRED_FROM_DEPARTMENT",
            "DEPARTMENT_OFFERS_COURSE",
            "EVENT_CONDUCTED_BY_DEPARTMENT",
        }
        if rel_type not in allowed:
            raise ValueError(f"Unsupported relationship type: {rel_type}")

        return f"""
        MATCH (a {{name: $source}})
        MATCH (b {{name: $target}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r.source_url = coalesce(r.source_url, $source_url)
        """
