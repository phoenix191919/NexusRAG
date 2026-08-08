# Environment

Copy to `.env` and fill in secrets. Never commit `.env`.

```bash
cp .env.example .env   # or: copy .env.example .env  on Windows
```

## Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio / Gemini API key |

## Models

| Variable | Default | Notes |
|----------|---------|-------|
| `GEMINI_MODEL` | `gemini-3.5-flash` | Chat / extract; client has fallbacks if unavailable |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | Dense vectors |
| `EMBEDDING_DIMS` | `768` | Must match collection |

## Infra

| Variable | Default |
|----------|---------|
| `QDRANT_URL` | `http://localhost:6333` |
| `QDRANT_COLLECTION` | `nexusrag` |
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | `nexusrag` (matches `docker-compose.yml`) |

## Paths & CORS

| Variable | Default |
|----------|---------|
| `DATA_DIR` | `./data` |
| `BUNDLE_DIR` | `./data/bundle` |
| `UPLOAD_DIR` | `./data/uploads` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
