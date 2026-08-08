# Architecture

NexusRAG is a small full-stack system that treats knowledge as a **persistent graph of concepts**, not a throwaway chat session.

## Goals

1. **Accumulate** — each new source should enrich shared entities, not replace prior context.
2. **Retrieve hybrid** — dense similarity alone misses multi-hop relations; the graph fills that gap.
3. **Cite** — answers must point back to source + page (or transcript offset) when available.
4. **Stay inspectable** — the OKF bundle is human-readable markdown on disk.

## Data flow

### Ingest

1. Parse PDF / DOCX / TXT / YouTube transcript into text with provenance metadata.
2. Chunk the document.
3. **Embed every chunk** into Qdrant (full semantic coverage for retrieval).
4. **Sample a budgeted subset** of chunks (`ingestion/sampler.py`) for Gemini entity/relation extraction — keeps ingest cost predictable.
5. Resolve entities against the existing OKF bundle (title / alias match; optional Gemini hint when needed).
6. Write / merge OKF concept files under `data/bundle/entities/` and source records under `data/bundle/sources/`.
7. Sync links into Neo4j for neighborhood queries.

### Query

1. Embed the user question; retrieve diverse top-k chunks from Qdrant.
2. Expand via Neo4j neighbors of entities mentioned in those hits (and title-matched concepts).
3. For list-style questions, run a light second pass to fill gaps.
4. Build a grounded prompt with excerpts + provenance; Gemini answers with citation hygiene rules.
5. Return answer, citations, and optional graph highlights to the UI.

## Module map

| Path | Responsibility |
|------|----------------|
| `backend/app/ingestion/` | Parsers, chunking, pipeline orchestration, smart sampling |
| `backend/app/okf/` | OKF v0.2 bundle read/write and merge |
| `backend/app/graph/` | LLM extraction schema + Neo4j client |
| `backend/app/rag/` | Gemini client, embeddings, hybrid retriever / answerer |
| `backend/app/api/` | HTTP surface for upload, query, graph, stats |
| `frontend/src/` | Knowledge map (React Flow) + glass ingest/chat overlays |

## Design tradeoffs

| Choice | Why |
|--------|-----|
| File-backed OKF + Neo4j sync | Disk is the source of truth and demos well; Neo4j speeds neighborhood walks |
| Sampled extraction, full embed | Extraction is the expensive LLM step; vectors must cover the whole doc |
| Gemini-only LLM stack | One key, strong multimodal/text models, simple ops for a portfolio MVP |
| No auth in MVP | Local demo / resume project; add auth before any shared deployment |

## Future extensions (interview talking points)

- Cross-encoder re-ranking and stricter citation verification  
- Stronger entity linking (embeddings over aliases, human confirm UI)  
- Streaming answers and async ingest jobs with progress events  
- Auth + multi-tenant bundles for a production deployment  
