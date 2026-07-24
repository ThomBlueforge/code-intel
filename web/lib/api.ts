// Typed client for the Code Intelligence HTTP API (`/api/*`).
//
// In production the UI is served by FastAPI at the same origin, so the base URL
// is empty. During `next dev` (port 3000) we point at the FastAPI dev server on
// port 8000. Override explicitly with NEXT_PUBLIC_API_BASE.

function resolveBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE;
  if (explicit && explicit.length > 0) return explicit;
  if (typeof window !== "undefined" && window.location.port === "3000") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "";
}

export interface RepoEntry {
  path: string;
  name: string;
  db_path: string;
  last_indexed: string;
  indexed: boolean;
}

export interface BrowseEntry {
  name: string;
  path: string;
  indexed: boolean;
}

export interface BrowseListing {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}

export interface JobProgress {
  done: number;
  total: number | null;
  message: string;
}

export type JobStatus = "pending" | "running" | "done" | "error";

export interface JobSnapshot {
  id: string;
  kind: string;
  status: JobStatus;
  progress: JobProgress;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Health {
  status: string;
  schema?: string;
  files?: number;
  db?: string;
}

export interface DuplicateGroup {
  count: number;
  names: string[];
  paths: string[];
}

export interface Stats {
  files: number;
  symbols: number;
  languages: Record<string, number>;
  call_edges: number;
  import_edges: number;
  circular_dependencies: string[][];
  duplicate_implementations: DuplicateGroup[];
  dead_code_candidates: string[];
  orphan_modules: string[];
  entry_points: string[];
  shared_utilities: [string, number][];
  most_depended_modules: [string, number][];
}

export interface Finding {
  id: string;
  category: string;
  title: string;
  detail: string;
  origin: string;
  confidence: number;
  target: string;
}

export interface Intel {
  count: number;
  by_category: Record<string, number>;
  findings: Finding[];
  diff?: { new: number; resolved: number };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${resolveBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body && body.detail != null) detail = String(body.detail);
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const qp = (params: Record<string, string>): string =>
  new URLSearchParams(params).toString();

export const getRepos = (): Promise<{ repositories: RepoEntry[] }> =>
  request("/api/repos");

export const browse = (dir?: string): Promise<BrowseListing> =>
  request(`/api/browse${dir ? `?${qp({ dir })}` : ""}`);

export const getHealth = (path: string): Promise<Health> =>
  request(`/api/health?${qp({ path })}`);

export const getStats = (path: string): Promise<Stats> =>
  request(`/api/stats?${qp({ path })}`);

export const getIntel = (
  path: string,
  opts?: { origin?: string; diff?: boolean },
): Promise<Intel> => {
  const params: Record<string, string> = { path };
  if (opts?.origin) params.origin = opts.origin;
  if (opts?.diff) params.diff = "true";
  return request(`/api/intel?${qp(params)}`);
};

export const startIndex = (path: string): Promise<JobSnapshot> =>
  request("/api/index", { method: "POST", body: JSON.stringify({ path }) });

export const startUpdate = (path: string): Promise<JobSnapshot> =>
  request("/api/update", { method: "POST", body: JSON.stringify({ path }) });

export const getJob = (id: string): Promise<JobSnapshot> =>
  request(`/api/jobs/${encodeURIComponent(id)}`);

export const deleteRepo = (
  path: string,
): Promise<{ deleted: boolean; path: string }> =>
  request(`/api/repo?${qp({ path })}`, { method: "DELETE" });

export async function pollJob(
  id: string,
  onUpdate?: (snapshot: JobSnapshot) => void,
  intervalMs = 400,
): Promise<JobSnapshot> {
  for (;;) {
    const snapshot = await getJob(id);
    onUpdate?.(snapshot);
    if (snapshot.status === "done" || snapshot.status === "error") return snapshot;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// --- search, symbols, source (U3) ----------------------------------------

export interface FileInfo {
  path: string;
  language: string;
}

export interface KeywordMatch {
  path: string;
  line: number;
  text: string;
}

export interface SymbolHit {
  name: string;
  type: string;
  path: string;
  line: number;
  score: number;
  match: string;
}

export interface RetrieveResult {
  name: string;
  type: string;
  path: string;
  start_line: number;
  score: number;
  sources: string[];
}

export interface FileSymbol {
  id: string;
  name: string;
  type: string;
  visibility: string;
  start_line: number;
  end_line: number;
  signature: string | null;
  parent: string | null;
}

export interface FileSource {
  file: string;
  start: number;
  end: number;
  total_lines: number;
  lines: string[];
}

export const getFiles = (path: string): Promise<{ files: FileInfo[] }> =>
  request(`/api/files?${qp({ path })}`);

export const searchKeyword = (body: {
  path: string;
  keyword: string;
  regex?: boolean;
  case_sensitive?: boolean;
  limit?: number;
}): Promise<{ backend: string; matches: KeywordMatch[] }> =>
  request("/api/search", { method: "POST", body: JSON.stringify(body) });

export const searchSymbol = (
  path: string,
  query: string,
): Promise<{ results: SymbolHit[] }> =>
  request(`/api/symbol?${qp({ path, query })}`);

export const retrieve = (body: {
  path: string;
  query: string;
  limit?: number;
}): Promise<{ results: RetrieveResult[] }> =>
  request("/api/retrieve", { method: "POST", body: JSON.stringify(body) });

export const getFileSymbols = (
  path: string,
  file: string,
): Promise<{ file: string; symbols: FileSymbol[] }> =>
  request(`/api/symbols?${qp({ path, file })}`);

export const getFileSource = (
  path: string,
  file: string,
  start?: number,
  end?: number,
): Promise<FileSource> => {
  const params: Record<string, string> = { path, file };
  if (start != null) params.start = String(start);
  if (end != null) params.end = String(end);
  return request(`/api/file?${qp(params)}`);
};

// --- repo-wide symbol browser -------------------------------------------

export interface QualityMetrics {
  complexity: number;
  maintainability: number;
  readability: number;
  coupling: number;
  cohesion: number;
  testability: number;
  risk: number;
  stability: number;
  reusability: number;
  technical_debt: number;
}

export interface EnrichedInfo {
  symbol_id: string;
  summary: string;
  business_domain: string[];
  architecture_layer: string;
  responsibilities: string[];
  quality_metrics: QualityMetrics;
  risks: string[];
  technical_debt: string[];
  confidence: number;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface SymbolDetail {
  id: string;
  name: string;
  type: string;
  language: string;
  path: string;
  start_line: number;
  end_line: number;
  loc: number;
  signature: string;
  visibility: string;
  parent: string | null;
  decorators: string[];
  code: string;
  hash: string;
  created_at: string;
  updated_at: string;
  enriched: EnrichedInfo | null;
}

export type SymbolSort = "loc" | "name" | "type" | "path" | "updated";

export interface SymbolPage {
  total: number;
  returned: number;
  enriched_available: boolean;
  symbols: SymbolDetail[];
}

export const getAllSymbols = (
  path: string,
  opts: {
    q?: string;
    sort?: SymbolSort;
    order?: "asc" | "desc";
    limit?: number;
  } = {},
): Promise<SymbolPage> => {
  const params: Record<string, string> = { path };
  if (opts.q) params.q = opts.q;
  if (opts.sort) params.sort = opts.sort;
  if (opts.order) params.order = opts.order;
  if (opts.limit != null) params.limit = String(opts.limit);
  return request(`/api/symbols/all?${qp(params)}`);
};

// --- codebase comprehension (Phase 23) ----------------------------------

export interface FileUnderstanding {
  repository_id: string;
  path: string;
  summary: string;
  responsibilities: string[];
  key_exports: string[];
  collaborators: string[];
  role: string;
  source: string; // "aggregate" | "llm"
  confidence: number;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface RepoUnderstanding {
  repository_id: string;
  summary: string;
  architecture: string[];
  entry_points: string[];
  key_modules: string[];
  source: string;
  confidence: number;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface Understanding {
  available: boolean;
  repo: RepoUnderstanding | null;
  file: FileUnderstanding | null;
}

export const getUnderstanding = (
  path: string,
  file?: string,
): Promise<Understanding> => {
  const params: Record<string, string> = { path };
  if (file) params.file = file;
  return request(`/api/understanding?${qp(params)}`);
};

// --- graph (U4) -----------------------------------------------------------

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  origin: string;
}

export interface GraphData {
  focus: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const getGraph = (
  path: string,
  symbol: string,
  depth = 1,
): Promise<GraphData> =>
  request(`/api/graph?${qp({ path, symbol, depth: String(depth) })}`);

// --- understanding: ask, explain, impact (U5) ----------------------------

export interface Answer {
  answer: string;
  citations: string[];
  used_llm: boolean;
}

export const ask = (
  path: string,
  question: string,
  useLlm: boolean,
): Promise<Answer> =>
  request("/api/ask", {
    method: "POST",
    body: JSON.stringify({ path, question, use_llm: useLlm }),
  });

export interface Explanation {
  scope: string;
  target: string;
  summary: string;
  details: string[];
}

export const explain = (path: string, target: string): Promise<Explanation> =>
  request(`/api/explain?${qp({ path, target })}`);

export interface ImpactReport {
  symbol: string;
  targets: number;
  direct_callers: string[];
  indirect_callers: string[];
  affected_files: string[];
  affected_modules: string[];
  affected_tests: string[];
}

export const getImpact = (path: string, symbol: string): Promise<ImpactReport> =>
  request(`/api/impact?${qp({ path, symbol })}`);

// --- AI layers: config, enrich, embed (U6) -------------------------------

export interface LLMConfig {
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
  max_retries: number;
  batch_size: number;
  max_concurrency: number;
}

export interface Config {
  db_path: string;
  max_file_bytes: number;
  llm: LLMConfig;
}

export const getConfig = (path: string): Promise<Config> =>
  request(`/api/config?${qp({ path })}`);

export const startEnrich = (body: {
  path: string;
  limit?: number | null;
  force?: boolean;
  base_url?: string | null;
  model?: string | null;
}): Promise<JobSnapshot> =>
  request("/api/enrich", { method: "POST", body: JSON.stringify(body) });

export const startEmbed = (body: {
  path: string;
  limit?: number | null;
  force?: boolean;
}): Promise<JobSnapshot> =>
  request("/api/embed", { method: "POST", body: JSON.stringify(body) });
