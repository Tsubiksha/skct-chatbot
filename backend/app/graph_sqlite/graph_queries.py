"""
graph_queries.py — SQL query functions for the Graph RAG knowledge graph.

Only contains functions that work with the new website-only schema:
  entities, relationships tables (built from scraped SKCT website pages).

Student/results queries have been removed — those tables no longer exist
in the new website-only backend schema.
"""

import logging
from backend.app.graph_sqlite.db import fetchall, fetchone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph / entity queries (website-only schema)
# ---------------------------------------------------------------------------

def get_related_entities(entity_name: str, limit: int = 20) -> dict:
    """All relationships where entity_name appears as source or target."""
    rows = fetchall(
        """SELECT e_src.name AS source_name, e_src.entity_type AS source_type,
                  rel.relation_type,
                  e_tgt.name AS target_name, e_tgt.entity_type AS target_type,
                  rel.properties_json
           FROM relationships rel
           JOIN entities e_src ON e_src.id = rel.source_entity_id
           JOIN entities e_tgt ON e_tgt.id = rel.target_entity_id
           WHERE LOWER(e_src.name) LIKE LOWER(?)
              OR LOWER(e_tgt.name) LIKE LOWER(?)
           LIMIT ?""",
        (f"%{entity_name}%", f"%{entity_name}%", limit)
    )
    return {"entity_name": entity_name,
            "relationships": [dict(r) for r in rows]}


def get_all_entities(limit: int = 100) -> dict:
    """Return all distinct entities in the knowledge graph."""
    rows = fetchall(
        """SELECT name, entity_type, source_type, metadata_json
           FROM entities
           ORDER BY entity_type, name
           LIMIT ?""",
        (limit,)
    )
    return {"entities": [dict(r) for r in rows]}


def get_entity_details(entity_name: str) -> dict:
    """Full entity record and all its relationships."""
    entity = fetchone(
        "SELECT * FROM entities WHERE LOWER(name) = LOWER(?)",
        (entity_name,)
    )
    if not entity:
        return {"found": False, "entity_name": entity_name}

    rels = fetchall(
        """SELECT e_src.name AS source_name, rel.relation_type,
                  e_tgt.name AS target_name, rel.properties_json
           FROM relationships rel
           JOIN entities e_src ON e_src.id = rel.source_entity_id
           JOIN entities e_tgt ON e_tgt.id = rel.target_entity_id
           WHERE rel.source_entity_id = ? OR rel.target_entity_id = ?""",
        (entity["id"], entity["id"])
    )
    return {
        "found": True,
        "entity": dict(entity),
        "relationships": [dict(r) for r in rels],
    }
