import { FormEvent, useEffect, useMemo, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { FileUp, Loader2, Send, Sparkles, Video, X } from "lucide-react";
import KnowledgeGraph from "./components/KnowledgeGraph";
import {
  ask,
  getEntity,
  getGraph,
  getSources,
  getStats,
  type EntityDetail,
  type GraphData,
  type QueryResult,
  type SourceRecord,
  type Stats,
  uploadFile,
  uploadYoutube,
} from "./api";

function statusColor(status: string) {
  if (status === "COMPLETED") return "var(--ok)";
  if (status === "FAILED") return "var(--bad)";
  return "var(--warn)";
}

function collectHighlights(result: QueryResult | null, fullGraph: GraphData): Set<string> {
  const ids = new Set<string>();
  if (!result) return ids;

  for (const n of result.graph?.nodes || []) {
    if (n.type !== "Source") ids.add(n.id);
  }
  for (const c of result.citations || []) {
    if (c.concept_id) ids.add(c.concept_id);
  }

  const answer = (result.answer || "").toLowerCase();
  for (const n of fullGraph.nodes || []) {
    if (n.type === "Source") continue;
    const label = (n.label || "").trim();
    if (label.length >= 3 && answer.includes(label.toLowerCase())) {
      ids.add(n.id);
    }
  }
  return ids;
}

export default function App() {
  const [stats, setStats] = useState<Stats>({ sources: 0, chunks: 0, entities: 0, relationships: 0 });
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [graph, setGraph] = useState<GraphData>({ nodes: [], edges: [] });
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [question, setQuestion] = useState("How does BERT relate to Transformers?");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [entityLoading, setEntityLoading] = useState(false);

  const highlightedIds = useMemo(() => collectHighlights(result, graph), [result, graph]);

  async function refresh() {
    try {
      const [s, src, g] = await Promise.all([getStats(), getSources(), getGraph()]);
      setStats(s);
      setSources(src);
      setGraph(g);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backend unreachable");
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function onUpload(file?: File | null) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadFile(file);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onYoutube(e: FormEvent) {
    e.preventDefault();
    if (!youtubeUrl.trim()) return;
    setUploading(true);
    setError(null);
    try {
      await uploadYoutube(youtubeUrl.trim());
      setYoutubeUrl("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "YouTube ingest failed");
    } finally {
      setUploading(false);
    }
  }

  async function onAsk(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    setPanelOpen(true);
    try {
      const res = await ask(question.trim());
      setResult(res);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(false);
    }
  }

  async function onNodeSelect(nodeId: string) {
    setEntityLoading(true);
    try {
      const detail = await getEntity(nodeId);
      setEntity(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load entity");
    } finally {
      setEntityLoading(false);
    }
  }

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-[var(--bg)] text-[var(--ink)]">
      <div className="absolute inset-0">
        <ReactFlowProvider>
          <KnowledgeGraph
            data={graph}
            highlightedIds={highlightedIds}
            onNodeSelect={onNodeSelect}
          />
        </ReactFlowProvider>
      </div>

      {/* Top-left brand + stats */}
      <div className="pointer-events-none absolute left-4 top-4 z-20 flex max-w-xl flex-col gap-3 md:left-6 md:top-6">
        <div className="pointer-events-auto glass-panel rounded-2xl px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[var(--accent)]" />
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
              Evolving knowledge engine
            </p>
          </div>
          <h1 className="mt-1 text-3xl text-white md:text-4xl">NexusRAG</h1>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Drag to pan · scroll to zoom · click a node for its wiki page
          </p>
        </div>
        <div className="pointer-events-auto grid grid-cols-4 gap-2">
          {[
            ["Sources", stats.sources],
            ["Chunks", stats.chunks],
            ["Entities", stats.entities],
            ["Links", stats.relationships],
          ].map(([label, value]) => (
            <div key={label as string} className="glass-panel rounded-xl px-2.5 py-2 text-center">
              <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
              <div className="text-lg font-semibold tabular-nums text-white">{value}</div>
            </div>
          ))}
        </div>
        {highlightedIds.size > 0 && (
          <div className="pointer-events-auto glass-panel flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-xs">
            <span className="text-[var(--accent)]">{highlightedIds.size} nodes lit from last answer</span>
            <button
              type="button"
              className="text-[var(--muted)] hover:text-white"
              onClick={() => setResult(null)}
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Right entity detail panel */}
      {(entity || entityLoading) && (
        <aside className="absolute right-4 top-4 z-30 flex max-h-[calc(100vh-8rem)] w-[min(100%-2rem,380px)] flex-col md:right-6 md:top-6">
          <div className="glass-panel flex max-h-full flex-col overflow-hidden rounded-2xl">
            <div className="flex items-start justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--accent)]">
                  {entityLoading ? "Loading…" : entity?.type || "Entity"}
                </div>
                <h2 className="text-lg text-white">{entity?.title || "…"}</h2>
                {entity?.description && (
                  <p className="mt-1 text-xs text-[var(--muted)]">{entity.description}</p>
                )}
              </div>
              <button
                type="button"
                className="text-[var(--muted)] hover:text-white"
                onClick={() => setEntity(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="overflow-y-auto px-4 py-3 text-sm">
              {entityLoading && !entity && (
                <div className="flex items-center gap-2 text-[var(--muted)]">
                  <Loader2 size={14} className="animate-spin" /> Loading concept…
                </div>
              )}

              {!!entity?.sources?.length && (
                <div className="mb-4">
                  <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                    Sources that contributed
                  </h3>
                  <ul className="space-y-1.5">
                    {entity.sources.map((s, i) => (
                      <li
                        key={`${s.id || s.title}-${i}`}
                        className="rounded-lg border border-[var(--line)] bg-black/25 px-2.5 py-1.5 text-xs text-[#c9d4f0]"
                      >
                        {s.title || s.resource || s.id}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {!!entity?.links?.length && (
                <div className="mb-4">
                  <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                    Links
                  </h3>
                  <ul className="space-y-1 text-xs text-[var(--muted)]">
                    {entity.links.map((l, i) => (
                      <li key={`${l.target}-${i}`}>
                        <button
                          type="button"
                          className="text-left text-[var(--accent)] hover:underline"
                          onClick={() => onNodeSelect(l.target)}
                        >
                          {l.label} → {l.target}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {entity?.body && (
                <div>
                  <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                    Merged knowledge
                  </h3>
                  <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-[#d7def5]">
                    {entity.body}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </aside>
      )}

      {/* Left ingest panel */}
      <aside className="absolute bottom-4 left-4 z-20 flex w-[min(100%-2rem,340px)] flex-col gap-3 md:bottom-6 md:left-6">
        <div className="glass-panel rounded-2xl p-4">
          <h2 className="mb-3 text-sm font-semibold text-white">Ingest</h2>
          <div className="space-y-3">
            <label className="flex cursor-pointer flex-col items-center gap-1 rounded-xl border border-dashed border-[var(--accent)]/35 bg-white/5 px-3 py-4 text-center transition hover:bg-[var(--accent)]/10">
              <FileUp size={18} className="text-[var(--accent)]" />
              <span className="text-xs font-medium">PDF / DOCX / TXT</span>
              <span className="text-[10px] text-[var(--muted)]">
                {uploading ? "Uploading…" : "Click to upload"}
              </span>
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md"
                className="hidden"
                onChange={(e) => onUpload(e.target.files?.[0])}
              />
            </label>
            <form onSubmit={onYoutube} className="space-y-2">
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--muted)]">
                <Video size={14} className="text-[var(--accent-2)]" />
                YouTube URL
              </div>
              <input
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=..."
                className="w-full rounded-lg border border-[var(--line)] bg-black/30 px-3 py-2 text-sm outline-none ring-[var(--accent)] placeholder:text-[var(--muted)] focus:ring-1"
              />
              <button
                type="submit"
                disabled={uploading}
                className="w-full rounded-lg bg-[var(--accent-2)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                Ingest URL
              </button>
            </form>
          </div>
        </div>

        <div className="glass-panel max-h-40 overflow-y-auto rounded-2xl p-3">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Sources
          </h2>
          {sources.length === 0 && (
            <p className="text-xs text-[var(--muted)]">No sources yet.</p>
          )}
          <div className="space-y-2">
            {sources.slice(0, 6).map((s) => (
              <div key={s.source_id} className="rounded-lg border border-[var(--line)] bg-black/20 p-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="truncate text-xs font-medium text-white">{s.title}</div>
                  <span className="shrink-0 text-[10px] font-semibold" style={{ color: statusColor(s.status) }}>
                    {s.status}
                  </span>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-[var(--accent)] transition-all"
                    style={{ width: `${s.progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* Bottom-right ask + answer */}
      <div className="absolute bottom-4 right-4 z-20 flex w-[min(100%-2rem,420px)] flex-col gap-3 md:bottom-6 md:right-6">
        {error && (
          <div className="glass-panel rounded-xl border border-[var(--bad)]/40 px-3 py-2 text-xs text-[var(--bad)]">
            {error}
          </div>
        )}

        {result && panelOpen && (
          <div className="glass-panel max-h-[36vh] overflow-y-auto rounded-2xl p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Answer</h2>
              <button type="button" onClick={() => setPanelOpen(false)} className="text-[var(--muted)] hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-[#d7def5]">{result.answer}</div>
            {result.confidence && (
              <div className="mt-2 text-[10px] uppercase tracking-wide text-[var(--muted)]">
                Confidence · {result.confidence}
              </div>
            )}
            {!!result.conflicts?.length && (
              <div className="mt-2 rounded-lg border border-[var(--warn)]/30 bg-[var(--warn)]/10 p-2 text-xs text-[var(--warn)]">
                {result.conflicts.join(" · ")}
              </div>
            )}
            {!!result.citations?.length && (
              <ul className="mt-3 space-y-1 border-t border-[var(--line)] pt-3 text-xs text-[var(--muted)]">
                {result.citations.map((c, i) => (
                  <li key={`${c.source_id}-${i}`}>
                    {c.title}
                    {c.page != null ? ` — p.${c.page}` : ""}
                    {c.timestamp_start ? ` — ${c.timestamp_start}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <form onSubmit={onAsk} className="glass-panel flex gap-2 rounded-2xl p-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="min-w-0 flex-1 rounded-xl bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-[var(--muted)]"
            placeholder="Ask the knowledge base…"
          />
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-[#04110e] disabled:opacity-60"
          >
            {busy ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}
