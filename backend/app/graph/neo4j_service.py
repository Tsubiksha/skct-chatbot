import logging
import os
from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

logger = logging.getLogger(__name__)


class Neo4jService:
    """Small synchronous Neo4j helper used only by the additive GraphRAG module."""

    _instance: "Neo4jService | None" = None

    def __new__(cls) -> "Neo4jService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._driver = None
        return cls._instance

    def connect(self) -> None:
        if self._driver is not None:
            return

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", uri)

    @contextmanager
    def session(self):
        self.connect()
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    def run_query(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            with self.session() as session:
                result = session.run(cypher, parameters or {})
                return [dict(record) for record in result]
        except (Neo4jError, ServiceUnavailable, OSError) as exc:
            logger.warning("Neo4j query failed: %s", exc)
            raise RuntimeError(f"Neo4j query failed: {exc}") from exc

    def create_node(self, label: str, name: str, properties: dict[str, Any] | None = None) -> None:
        safe_label = self._safe_label(label)
        properties = properties or {}
        self.run_query(
            f"""
            MERGE (n:{safe_label} {{name: $name}})
            SET n += $properties
            """,
            {"name": name, "properties": properties},
        )

    def create_relationship(
        self,
        source_label: str,
        source_name: str,
        relationship_type: str,
        target_label: str,
        target_name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        safe_source = self._safe_label(source_label)
        safe_target = self._safe_label(target_label)
        safe_relationship = self._safe_label(relationship_type)
        properties = properties or {}
        self.run_query(
            f"""
            MERGE (source:{safe_source} {{name: $source_name}})
            MERGE (target:{safe_target} {{name: $target_name}})
            MERGE (source)-[rel:{safe_relationship}]->(target)
            SET rel += $properties
            """,
            {
                "source_name": source_name,
                "target_name": target_name,
                "properties": properties,
            },
        )

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _safe_label(self, value: str) -> str:
        cleaned = "".join(character for character in value if character.isalnum() or character == "_")
        if not cleaned:
            raise ValueError("Neo4j labels and relationship types cannot be empty")
        return cleaned
