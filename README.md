# NexusRAG

Evolving knowledge-graph RAG: ingest PDFs and transcripts into a persistent [OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) knowledge map, then answer with hybrid **vector + graph** retrieval and page/timestamp citations.

**Repo:** [phoenix191919/NexusRAG](https://github.com/phoenix191919/NexusRAG)

## Why not plain RAG?

Traditional RAG stacks isolated chunks. NexusRAG also extracts entities/relationships, merges the same concept across documents, and keeps provenance — so each upload extends a shared knowledge base you can inspect as markdown.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React, Vite, Tailwind, React Flow |
| Backend | FastAPI |
| Vectors | Qdrant + `gemini-embedding-2` |
| Graph | Neo4j (synced from OKF links) |
| LLM | Gemini (`gemini-3.5-flash` + fallbacks) |
| Knowledge | OKF v0.2 bundle on disk |

## Prerequisites

- Python 3.10+
- Node 20+
- Docker Desktop
- A [Gemini API key](https://aistudio.google.com/apikey)

## Setup

```powershell
git clone https://github.com/phoenix191919/NexusRAG.git
cd NexusRAG

copy .env.example .env
# Set GEMINI_API_KEY in .env

docker compose up -d

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

cd frontend
npm install
cd ..
```

## Run

**API** (terminal 1):

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "backend"
uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

**UI** (terminal 2):

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/sources/upload` | PDF / DOCX / TXT |
| POST | `/api/sources/youtube` | `{ "url": "..." }` |
| GET | `/api/sources` | Status list |
| POST | `/api/query` | `{ "question": "..." }` |
| GET | `/api/graph` | Full link graph |
| GET | `/api/graph/entity/{id}` | OKF concept detail |
| GET | `/api/stats` | Counts |
| GET | `/api/health` | Health check |

## Data layout (local, gitignored)

- `data/uploads/` — raw files  
- `data/bundle/` — OKF concepts (`entities/`, `sources/`)  
- `data/sources.json` — ingestion status  

## License

Add a license of your choice (MIT recommended for open source).
