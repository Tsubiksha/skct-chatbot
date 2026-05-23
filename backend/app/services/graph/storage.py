import sqlite3
import json
from typing import List, Dict, Any, Tuple
from backend.app.config import settings

class GraphStorage:
    def __init__(self):
        self.db_path = settings.GRAPH_DB_PATH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Nodes table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT,
                source_chunk_id TEXT
            )
            """)
            
            # Edges table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                target_id TEXT,
                relation_type TEXT NOT NULL,
                properties TEXT,
                source_chunk_id TEXT,
                FOREIGN KEY(source_id) REFERENCES entities(id),
                FOREIGN KEY(target_id) REFERENCES entities(id),
                UNIQUE(source_id, target_id, relation_type)
            )
            """)
            
            # Full Text Search for fast entity lookup
            cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                name,
                type,
                properties,
                content='entities',
                content_rowid='rowid'
            )
            """)
            
            # Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relation_source ON relationships(source_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relation_target ON relationships(target_id)")
            conn.commit()

    def add_entity(self, entity_id: str, name: str, entity_type: str, properties: Dict[str, Any], chunk_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            props_json = json.dumps(properties)
            
            # Upsert entity
            cursor.execute("""
            INSERT INTO entities (id, name, type, properties, source_chunk_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                properties = ?,
                source_chunk_id = ?
            """, (entity_id, name, entity_type, props_json, chunk_id, props_json, chunk_id))
            
            # Update FTS
            cursor.execute("INSERT OR REPLACE INTO entities_fts (rowid, name, type, properties) VALUES (last_insert_rowid(), ?, ?, ?)", 
                           (name, entity_type, props_json))
            conn.commit()

    def add_relationship(self, source_id: str, target_id: str, relation_type: str, properties: Dict[str, Any], chunk_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            props_json = json.dumps(properties)
            
            cursor.execute("""
            INSERT OR IGNORE INTO relationships (source_id, target_id, relation_type, properties, source_chunk_id)
            VALUES (?, ?, ?, ?, ?)
            """, (source_id, target_id, relation_type, props_json, chunk_id))
            conn.commit()

    def get_entity_neighbors(self, entity_id: str, max_hops: int = 1) -> List[Dict[str, Any]]:
        # For simplicity, implementing 1-hop here. Multi-hop can be done via recursive CTEs
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT e.id, e.name, e.type, r.relation_type, 'outgoing' as direction
            FROM relationships r
            JOIN entities e ON r.target_id = e.id
            WHERE r.source_id = ?
            UNION ALL
            SELECT e.id, e.name, e.type, r.relation_type, 'incoming' as direction
            FROM relationships r
            JOIN entities e ON r.source_id = e.id
            WHERE r.target_id = ?
            """, (entity_id, entity_id))
            
            return [dict(row) for row in cursor.fetchall()]

    def search_entities(self, query: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Basic BM25 like search using FTS5
            cursor.execute("""
            SELECT e.id, e.name, e.type, e.properties 
            FROM entities e
            JOIN entities_fts f ON e.rowid = f.rowid
            WHERE entities_fts MATCH ?
            ORDER BY rank
            LIMIT 10
            """, (query,))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            stats = {}
            
            cursor.execute("SELECT count(*) FROM entities")
            stats['total_entities'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT type, count(*) FROM entities GROUP BY type")
            for row in cursor.fetchall():
                stats[f'entity_{row[0]}'] = row[1]
                
            cursor.execute("SELECT count(*) FROM relationships")
            stats['total_relationships'] = cursor.fetchone()[0]
            
            return stats
