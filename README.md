# SKCT Graph RAG Chatbot

An AI-powered website-based Graph RAG chatbot built for Sri Krishna College of Technology (SKCT).  
The system retrieves information from website content and generates grounded answers using Graph RAG, SQLite FTS5, web scraping, and Ollama.

## 🚀 Project Overview

This project started as a traditional RAG chatbot and was later upgraded into a Graph RAG system to improve contextual understanding and relationship-based retrieval.

The chatbot can answer questions related to:

- Departments
- Placements
- Events
- Announcements
- Research
- Facilities
- Contact information
- Institutional details
- Website-based actions and updates

## 🧠 What is Graph RAG?

Graph RAG combines Retrieval-Augmented Generation with knowledge graph relationships.

Instead of only retrieving text chunks, Graph RAG also connects entities such as departments, events, pages, contacts, and institutional information.

This improves:

- Context understanding
- Relationship-based answers
- Source-grounded responses
- Retrieval accuracy

## 🛠️ Tech Stack

### Backend
- Python
- FastAPI
- SQLite
- SQLite FTS5
- BeautifulSoup
- Requests
- Ollama

### Frontend
- React
- Responsive dashboard UI
- Chatbot interface
- Source display
- Admin controls

## ✨ Features

- Website-based chatbot
- Same-domain website crawling
- Sitemap discovery
- Website content cleaning
- Chunk-based retrieval
- SQLite FTS5 search
- LIKE fallback search
- Knowledge graph entity extraction
- Graph relationship generation
- Ollama-based response generation
- Source-based answers
- Chat session handling
- Responsive chatbot dashboard

## 📌 Main Modules

### Web Scraper
Scrapes website pages, extracts useful content, removes noise, and stores cleaned data.

### Chunker
Splits website content into overlapping chunks for better retrieval.

### FTS Search
Uses SQLite FTS5 to retrieve relevant website chunks.

### Graph Builder
Builds relationships between website entities and pages.

### Answer Service
Routes user questions, retrieves relevant context, calls Ollama, and returns grounded answers.

### Frontend Chatbot
Provides a clean UI for users to ask questions and view source-based answers.

## 📂 Project Structure

```txt
backend/
│
├── app/
│   ├── graph_sqlite/
│   │   ├── answer_service.py
│   │   ├── chunker.py
│   │   ├── db.py
│   │   ├── entity_extractor.py
│   │   ├── fts_search.py
│   │   ├── graph_builder.py
│   │   ├── graph_queries.py
│   │   ├── graph_router.py
│   │   ├── prompts.py
│   │   ├── router.py
│   │   ├── text_cleaner.py
│   │   ├── web_scraper.py
│   │   └── website_entity_extractor.py
│
frontend/
│
├── src/
│   ├── pages/
│   ├── components/
│   ├── api/
│   └── assets/
🔗 API Endpoints
Method	Endpoint	Description
POST	/api/graph-rag/init	Initialize Graph RAG database
POST	/api/graph-rag/scrape-website	Scrape website content
POST	/api/graph-rag/build-graph	Build graph relationships
POST	/api/graph-rag/reindex	Run full reindexing pipeline
POST	/api/graph-rag/chat	Ask chatbot questions
GET	/api/graph-rag/stats	Get Graph RAG statistics
💬 Chat Request Example
{
  "message": "What are the departments available in SKCT?",
  "session_id": 1
}
💬 Chat Response Example
{
  "answer": "SKCT offers departments such as...",
  "route": "website_fts",
  "route_label": "Website Search",
  "session_id": 1,
  "sources": [],
  "graph_facts": {},
  "elapsed_seconds": 2.4
}
⚙️ Setup Instructions
1. Clone the Repository
git clone <your-repository-url>
cd <project-folder>
2. Backend Setup
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
3. Configure Environment

Create a .env file:

COLLEGE_URL=https://skct.edu.in/
GRAPH_RAG_DB_PATH=data/graph_rag.db
OLLAMA_BASE_URL=http://localhost:11434
GRAPH_RAG_MODEL=llama3
4. Start Ollama
ollama serve

Pull model if needed:

ollama pull llama3
5. Run Backend
uvicorn app.main:app --reload
6. Frontend Setup
cd frontend
npm install
npm run dev
🔄 Graph RAG Pipeline
Initialize database
Scrape website
Clean website content
Split content into chunks
Store chunks in SQLite
Index chunks using FTS5
Extract website entities
Build graph relationships
Retrieve context for user query
Generate grounded answer using Ollama
📊 Dashboard Features
Chatbot interface
Graph RAG statistics
Website scraping controls
Build graph button
Full reindex option
Source-based answer display
Route badge
Response time display
🎯 Learning Outcomes

This project helped me learn:

Traditional RAG architecture
Graph RAG concepts
Web scraping pipelines
Text chunking strategies
SQLite FTS5 retrieval
Knowledge graph relationships
FastAPI backend development
Ollama LLM integration
Source-grounded AI responses
Responsive chatbot UI design
🚀 Future Improvements
Improve graph traversal ranking
Add better entity extraction
Add semantic vector search
Add admin analytics dashboard
Add multilingual chatbot support
Improve source citation formatting
Add scheduled website reindexing
👩‍💻 Author

Subiksha Thangavel
AI & DS Student
Sri Krishna College of Technology

🏷️ Tags

Graph RAG RAG FastAPI Python SQLite FTS5 Ollama Chatbot Knowledge Graph Web Scraping
