# AI-Powered College Knowledge Assistant

Production-style GraphRAG chatbot for Sri Krishna College of Technology website data. It combines website scraping, PDF text extraction, ChromaDB semantic search, Neo4j relationship traversal, and Ollama models.

## Architecture

```text
React + Tailwind UI
    -> FastAPI async REST API
    -> GraphRAG engine
    -> ChromaDB semantic search + Neo4j graph traversal
    -> Ollama llama3:8b answer generation
```

## Features

- Scrapes relevant SKCT pages from `https://skct.edu.in/`
- Cleans and chunks text with a default chunk size of 500 words
- Embeds chunks using `nomic-embed-text` through Ollama
- Stores vectors in local persistent ChromaDB
- Extracts departments, faculty, courses, companies, events, and relationships
- Stores graph entities in Neo4j
- Answers with vector context plus graph relationship context
- Displays retrieved sources and graph context in a responsive chatbot UI

## Backend Setup

1. Create and activate a virtual environment.

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install Python dependencies.

```bash
pip install -r requirements.txt
```

3. Copy environment settings.

```bash
copy .env.example .env
```

4. Start the backend.

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

FastAPI docs will be available at `http://localhost:8000/docs`.

## Ollama Setup

Install Ollama, then pull the required models:

```bash
ollama pull llama3:8b
ollama pull nomic-embed-text
ollama serve
```

The backend expects Ollama at `http://localhost:11434`.

## Neo4j Setup

Use Neo4j Desktop or Docker.

```bash
docker run --name college-neo4j ^
  -p 7474:7474 -p 7687:7687 ^
  -e NEO4J_AUTH=neo4j/password ^
  neo4j:5
```

Then keep these values in `.env`:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
```

The code creates constraints for:

- `Department`
- `Faculty`
- `Company`
- `Course`
- `Event`

Relationships:

- `FACULTY_BELONGS_TO_DEPARTMENT`
- `FACULTY_TEACHES_COURSE`
- `COMPANY_HIRED_FROM_DEPARTMENT`
- `DEPARTMENT_OFFERS_COURSE`
- `EVENT_CONDUCTED_BY_DEPARTMENT`

## Frontend Setup

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open `http://localhost:5173`.

## API Documentation

### `GET /health`

Checks Ollama, Neo4j, and ChromaDB.

### `POST /scrape`

Scrapes pages and keeps the result in memory for optional ingestion.

```json
{
  "base_url": "https://skct.edu.in/",
  "max_pages": 20,
  "keywords": ["department", "faculty", "placement", "course", "event", "research"]
}
```

### `POST /ingest`

Scrapes, chunks, embeds, stores vectors, extracts entities, and builds the graph.

```json
{
  "scrape_first": true,
  "reset": true,
  "max_pages": 12
}
```

### `POST /query`

Runs GraphRAG retrieval and generates a grounded answer.

```json
{
  "question": "Which departments are connected to placements?",
  "top_k": 3
}
```

## Additive SQLite GraphRAG Module

This project also includes a separate SQLite-based GraphRAG module that does not modify the existing chatbot database or routes.

Backend module:

```text
backend/app/graph_rag/
```

SQLite database:

```text
backend/data/graph_rag.db
```

Routes:

```text
GET  /api/graph-rag/health
POST /api/graph-rag/scrape-website
GET  /api/graph-rag/website-search?query=placement
GET  /api/graph-rag/stats
GET  /api/graph-rag/scraped-pages
POST /api/graph-rag/query
POST /api/graph-rag/build-graph
GET  /api/graph-rag/graph-stats
POST /api/graph-rag/graph-query
```

Scrape request:

```json
{
  "force_reindex": false,
  "max_pages": 30,
  "max_depth": 2
}
```

Query request:

```json
{
  "question": "What does SKCT say about placements?"
}
```

Query response includes the grounded answer, citations, Neo4j relationships, retrieved SQLite chunks, and the route name:

```json
{
  "answer": "...",
  "sources": [],
  "graph_context": [],
  "retrieved_chunks": [],
  "route_used": "graph_rag"
}
```

Neo4j graph build flow:

1. Confirm `.env` matches the running Neo4j password:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j123
```

2. Scrape the website:

```bash
curl -X POST http://127.0.0.1:8000/api/graph-rag/scrape-website ^
  -H "Content-Type: application/json" ^
  -d "{\"force_reindex\":false,\"max_pages\":30,\"max_depth\":2}"
```

3. Build Neo4j graph:

```bash
curl -X POST http://127.0.0.1:8000/api/graph-rag/build-graph
```

4. Query graph:

```bash
curl -X POST http://127.0.0.1:8000/api/graph-rag/graph-query ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"Which companies hired from departments teaching AI?\"}"
```

5. Ask the final GraphRAG answer endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/graph-rag/query ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"What departments are available?\"}"
```

Useful test questions:

```text
What departments are available?
What does SKCT say about placements?
Which recruiters are mentioned?
Who is the principal?
What events are listed?
What courses are offered by CSE?
Which companies hired from AI department?
What training information exists?
```

Example Cypher:

```cypher
MERGE (d:Department {name: "CSE"});
MERGE (c:Course {name: "Artificial Intelligence"});
MATCH (d:Department {name:"CSE"})
MATCH (c:Course {name:"Artificial Intelligence"})
MERGE (d)-[:DEPARTMENT_OFFERS_COURSE]->(c);
```

Frontend page:

```text
frontend/src/pages/GraphRagChat.jsx
```

To use it in your existing React routing, import the page and mount it wherever you want:

```jsx
import GraphRagChat from "./pages/GraphRagChat.jsx";
```

## Sample Questions

- Which departments are connected to placements?
- Tell me about Computer Science and Engineering.
- What courses are offered by the college?
- Which companies hired from departments?
- Summarize events and the departments involved.
- What research-related information is available?

## Notes for 16GB RAM Laptops

- Keep `MAX_SCRAPE_PAGES` between `10` and `25` while experimenting.
- Keep `RETRIEVAL_TOP_K=3`.
- Use `nomic-embed-text` for lightweight local embeddings.
- Ingesting is intentionally sequential to avoid memory spikes.
- Increase page limits only after confirming Ollama and Neo4j are stable.

## Project Structure

```text
backend/
  app.py
  config.py
  models.py
  scraper/
  rag/
  graph/
  embeddings/
  utils/
frontend/
  src/
  src/components/
  src/lib/
requirements.txt
README.md
```
