const API = "";

export type SourceRecord = {
  source_id: string;
  title: string;
  source_type: string;
  status: string;
  progress: number;
  progress_message: string;
  chunk_count: number;
  entity_count: number;
  error?: string | null;
  url?: string | null;
};

export type Stats = {
  sources: number;
  chunks: number;
  entities: number;
  relationships: number;
};

export type Citation = {
  source_id: string;
  title: string;
  page?: number | null;
  timestamp_start?: string | null;
  timestamp_end?: string | null;
  chunk_id?: string | null;
  concept_id?: string | null;
};

export type GraphData = {
  nodes: { id: string; label: string; type?: string; description?: string }[];
  edges: { source: string; target: string; label?: string }[];
};

export type QueryResult = {
  answer: string;
  citations: Citation[];
  graph: GraphData;
  conflicts: string[];
  confidence?: string | null;
};

export async function getStats(): Promise<Stats> {
  const r = await fetch(`${API}/api/stats`);
  if (!r.ok) throw new Error("Failed to load stats");
  return r.json();
}

export async function getSources(): Promise<SourceRecord[]> {
  const r = await fetch(`${API}/api/sources`);
  if (!r.ok) throw new Error("Failed to load sources");
  return r.json();
}

export async function getGraph(): Promise<GraphData> {
  const r = await fetch(`${API}/api/graph`);
  if (!r.ok) throw new Error("Failed to load graph");
  return r.json();
}

export async function uploadFile(file: File): Promise<SourceRecord> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/api/sources/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function uploadYoutube(url: string): Promise<SourceRecord> {
  const r = await fetch(`${API}/api/sources/youtube`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function ask(question: string): Promise<QueryResult> {
  const r = await fetch(`${API}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type EntityDetail = {
  id: string;
  type: string;
  title: string;
  description?: string | null;
  body?: string;
  tags?: string[];
  status?: string;
  sources?: { id?: string; resource?: string; title?: string }[];
  links?: { label: string; target: string }[];
  meta?: Record<string, unknown>;
};

export async function getEntity(entityId: string): Promise<EntityDetail> {
  const r = await fetch(`${API}/api/graph/entity/${encodeURIComponent(entityId)}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
