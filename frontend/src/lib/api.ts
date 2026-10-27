import type {
  CompareResponse,
  DatasetDetail,
  DatasetImportRequest,
  DatasetImportResponse,
  DatasetSummary,
  Meta,
  QueryResultPage,
  RunCreateRequest,
  RunPage,
  RunStatus,
  RunStatusResponse,
  RunSummary,
  ValidationIssue,
} from "./types";

const TOKEN_KEY = "evalforge.write-token";
const tokenListeners = new Set<() => void>();
const rawUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const normalizedUrl = rawUrl.replace(/\/+$/, "");

export const API_ROOT = normalizedUrl.endsWith("/api/v1")
  ? normalizedUrl.slice(0, -"/api/v1".length)
  : normalizedUrl;
export const API_BASE = `${API_ROOT}/api/v1`;
export const API_DOCS_URL = `${API_ROOT}/docs`;
export const SAMPLE_DATASET_URL = `${API_BASE}/datasets/sample`;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly issues: ValidationIssue[];

  constructor(status: number, message: string, detail?: unknown, issues: ValidationIssue[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.issues = issues;
  }
}

export function getWriteToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function hasWriteToken(): boolean {
  return Boolean(getWriteToken());
}

export function subscribeWriteToken(listener: () => void): () => void {
  tokenListeners.add(listener);
  return () => {
    tokenListeners.delete(listener);
  };
}

export function setWriteToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    if (token.trim()) {
      window.sessionStorage.setItem(TOKEN_KEY, token.trim());
    } else {
      window.sessionStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    return;
  }
  tokenListeners.forEach((listener) => listener());
}

function validationIssues(detail: unknown): ValidationIssue[] {
  if (!Array.isArray(detail)) return [];
  return detail.map((entry) => {
    if (!entry || typeof entry !== "object") return { message: String(entry) };
    const record = entry as Record<string, unknown>;
    const location = Array.isArray(record.loc) ? record.loc.join(".") : record.field;
    return {
      field: typeof location === "string" ? location : undefined,
      message:
        typeof record.msg === "string"
          ? record.msg
          : typeof record.message === "string"
            ? record.message
            : "Invalid value",
    };
  });
}

function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const issues = validationIssues(detail);
    return issues.length ? issues.map((issue) => issue.message).join("; ") : `Request failed (${status})`;
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (Array.isArray(record.errors)) {
      const issues = validationIssues(record.errors);
      if (issues.length) return issues.map((issue) => issue.message).join("; ");
    }
  }
  return `Request failed (${status})`;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getWriteToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("X-API-Key", token);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      `Could not reach the EvalForge API at ${API_ROOT}. Is the backend running?`,
    );
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      detail = body.detail ?? body;
    } catch {
      detail = await response.text().catch(() => "");
    }
    const record =
      detail && typeof detail === "object" ? (detail as Record<string, unknown>) : null;
    const issues = validationIssues(record?.errors ?? detail);
    throw new ApiError(response.status, errorMessage(detail, response.status), detail, issues);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function getMeta(): Promise<Meta> {
  return apiGet<Meta>("/meta");
}

export function getDatasets(): Promise<DatasetSummary[]> {
  return apiGet<DatasetSummary[]>("/datasets");
}

export function getDataset(id: string): Promise<DatasetDetail> {
  return apiGet<DatasetDetail>(`/datasets/${id}`);
}

export function importDataset(payload: DatasetImportRequest): Promise<DatasetImportResponse> {
  return apiPost<DatasetImportResponse>("/datasets", payload);
}

export function getRuns(
  options: {
    limit?: number;
    offset?: number;
    status?: RunStatus;
    datasetVersionId?: string;
  } = {},
): Promise<RunPage> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  if (options.status) params.set("status", options.status);
  if (options.datasetVersionId) params.set("dataset_version_id", options.datasetVersionId);
  return apiGet<RunPage>(`/runs?${params.toString()}`);
}

export function getRun(id: string): Promise<RunSummary> {
  return apiGet<RunSummary>(`/runs/${id}`);
}

export function getRunResults(
  id: string,
  options: { limit?: number; offset?: number } = {},
): Promise<QueryResultPage> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 20));
  params.set("offset", String(options.offset ?? 0));
  return apiGet<QueryResultPage>(`/runs/${id}/results?${params.toString()}`);
}

export function createRun(payload: RunCreateRequest): Promise<RunSummary> {
  return apiPost<RunSummary>("/runs", payload);
}

export function cancelRun(id: string): Promise<RunStatusResponse> {
  return apiPost<RunStatusResponse>(`/runs/${id}/cancel`, {});
}

export function getComparison(
  baselineId: string,
  candidateId: string,
): Promise<CompareResponse> {
  const params = new URLSearchParams({
    baseline_id: baselineId,
    candidate_id: candidateId,
  });
  return apiGet<CompareResponse>(`/runs/compare?${params.toString()}`);
}
