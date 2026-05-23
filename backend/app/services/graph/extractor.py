import json
import uuid
import re
import sqlite3
import re
from typing import List, Dict, Any
import ollama
from backend.app.config import settings
from backend.app.schemas.document import DocumentChunk
from backend.app.services.graph.storage import GraphStorage

class GraphExtractor:
    def __init__(self, storage: GraphStorage):
        self.storage = storage
        self.model = settings.LLM_MODEL
        
    def _create_extraction_prompt(self, chunk: DocumentChunk) -> str:
        return f"""
You are an expert knowledge graph extractor for a college context (SKCT).
Given the following text chunk from the college website, extract all relevant entities and their relationships.
Focus on these entity types: Department, Faculty, Course, Event, Facility, Company (for placements), Notice, Club.
Focus on relationships like: TEACHES, OFFERS, HOSTS, RECRUITS, PART_OF, REQUIRED_FOR.

Text:
{chunk.content}

Return ONLY a valid JSON object in this exact format (do not include markdown block markers):
{{
    "entities": [
        {{"name": "John Doe", "type": "Faculty", "properties": {{"role": "Professor"}}}},
        {{"name": "CSE", "type": "Department", "properties": {{}}}}
    ],
    "relationships": [
        {{"source": "John Doe", "target": "CSE", "relation": "PART_OF", "properties": {{}}}}
    ]
}}
"""

    def _generate_id(self, name: str, entity_type: str) -> str:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
        return f"{entity_type.lower()}_{clean_name}"

    def extract_and_store(self, chunk: DocumentChunk):
        prompt = self._create_extraction_prompt(chunk)
        
        try:
            response = ollama.chat(model=self.model, messages=[
                {"role": "system", "content": "You are a JSON-only extraction bot."},
                {"role": "user", "content": prompt}
            ])
            
            content = response['message']['content'].strip()
            
            # Clean up markdown if LLM includes it
            if content.startswith('```json'):
                content = content[7:-3]
            elif content.startswith('```'):
                content = content[3:-3]
                
            data = json.loads(content)
            
            # Process Entities
            for entity in data.get("entities", []):
                e_name = entity.get("name")
                e_type = entity.get("type")
                e_props = entity.get("properties", {})
                
                if e_name and e_type:
                    e_id = self._generate_id(e_name, e_type)
                    self.storage.add_entity(
                        entity_id=e_id,
                        name=e_name,
                        entity_type=e_type,
                        properties=e_props,
                        chunk_id=chunk.chunk_id
                    )
            
            # Process Relationships
            for rel in data.get("relationships", []):
                source_name = rel.get("source")
                target_name = rel.get("target")
                r_type = rel.get("relation")
                r_props = rel.get("properties", {})
                
                if source_name and target_name and r_type:
                    # In a real scenario, we might need to resolve entity types again,
                    # but we can try to find them by name in the DB, or just recreate the IDs
                    # based on the assumption that they exist in the extracted entities list
                    
                    # We'll just search by name for simplicity
                    with sqlite3.connect(self.storage.db_path) as conn:
                        cursor = conn.cursor()
                        
                        cursor.execute("SELECT id FROM entities WHERE name = ?", (source_name,))
                        s_row = cursor.fetchone()
                        
                        cursor.execute("SELECT id FROM entities WHERE name = ?", (target_name,))
                        t_row = cursor.fetchone()
                        
                        if s_row and t_row:
                            self.storage.add_relationship(
                                source_id=s_row[0],
                                target_id=t_row[0],
                                relation_type=r_type,
                                properties=r_props,
                                chunk_id=chunk.chunk_id
                            )
                            
        except Exception as e:
            print(f"Extraction failed for chunk {chunk.chunk_id}: {e}")

# This import is needed at the top of the file, let me add it.
