import type {
  CompareResponse,
  DatasetDetail,
  DatasetSummary,
  Meta,
  QueryResultPage,
  RunPage,
  RunStatus,
  RunStatusResponse,
  RunSummary,
} from "./types";

export interface RecordedDemo {
  schema_version: number;
  generated_at: string;
  source: string;
  meta: Meta;
  datasets: DatasetSummary[];
  dataset_details: Record<string, DatasetDetail>;
  runs: RunSummary[];
  run_results: Record<string, QueryResultPage>;
  comparisons: Record<string, CompareResponse>;
}

let demoPromise: Promise<RecordedDemo> | null = null;

/**
 * Load the committed recorded export on demand.
 *
 * The JSON is dynamically imported so a live dashboard never pays for it in its initial bundle.
 * It is only requested after the backend probe times out or returns the live-run pause response.
 */
export function loadRecordedDemo(): Promise<RecordedDemo> {
  if (!demoPromise) {
    demoPromise = import("./recorded-demo.json").then(
      (module) => module.default as unknown as RecordedDemo,
    );
  }
  return demoPromise;
}

function parseQuery(path: string): { pathname: string; search: URLSearchParams } {
  const url = new URL(path, "https://recorded.evalforge.local");
  return { pathname: url.pathname, search: url.searchParams };
}

function numberParam(search: URLSearchParams, key: string, fallback: number): number {
  const raw = search.get(key);
  if (raw === null || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function resolveRunList(demo: RecordedDemo, search: URLSearchParams): RunPage {
  const limit = Math.min(100, Math.max(1, numberParam(search, "limit", 20)));
  const offset = Math.max(0, numberParam(search, "offset", 0));
  const status = search.get("status") as RunStatus | null;
  const versionId = search.get("dataset_version_id");
  const filtered = demo.runs.filter((run) => {
    if (status && run.status !== status) return false;
    if (versionId && run.dataset_version_id !== versionId) return false;
    return true;
  });
  return {
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    limit,
    offset,
  };
}

function resolveComparison(
  demo: RecordedDemo,
  search: URLSearchParams,
): CompareResponse | undefined {
  const baseline = search.get("baseline_id");
  const candidate = search.get("candidate_id");
  if (!baseline || !candidate) return undefined;
  return demo.comparisons[`${baseline}:${candidate}`];
}

/**
 * Resolve a read-only API path from the committed recorded export. Returns undefined when the
 * recorded demo has no matching record; callers turn that into an explicit 404-style error.
 */
export async function resolveRecorded<T>(path: string): Promise<T | undefined> {
  const demo = await loadRecordedDemo();
  const { pathname, search } = parseQuery(path);

  if (pathname === "/meta") {
    return {
      ...demo.meta,
      demo_mode: true,
      write_protected: true,
      database_ready: true,
      sample_dataset_available: false,
      live_runs: {
        ...demo.meta.live_runs,
        enabled: false,
        daily_run_cap: null,
        per_ip_runs_per_window: null,
        window_seconds: null,
      },
    } as T;
  }

  if (pathname === "/datasets") {
    return demo.datasets as T;
  }

  if (pathname.startsWith("/datasets/")) {
    const datasetId = pathname.slice("/datasets/".length);
    return demo.dataset_details[datasetId] as T | undefined;
  }

  if (pathname === "/runs/compare") {
    return resolveComparison(demo, search) as T | undefined;
  }

  if (pathname === "/runs") {
    return resolveRunList(demo, search) as T;
  }

  if (pathname.startsWith("/runs/")) {
    const parts = pathname.slice("/runs/".length).split("/");
    const runId = parts[0];
    const run = demo.runs.find((item) => item.id === runId);
    if (!run) return undefined;

    if (parts.length === 1) {
      return run as T;
    }
    if (parts.length === 2 && parts[1] === "status") {
      const status: RunStatusResponse = {
        id: run.id,
        status: run.status,
        completed_queries: run.completed_queries,
        failed_queries: run.failed_queries,
        total_queries: run.total_queries,
      };
      return status as T;
    }
    if (parts.length === 2 && parts[1] === "results") {
      const page = demo.run_results[runId];
      if (!page) return undefined;
      const limit = Math.min(200, Math.max(1, numberParam(search, "limit", 20)));
      const offset = Math.max(0, numberParam(search, "offset", 0));
      const results: QueryResultPage = {
        items: page.items.slice(offset, offset + limit),
        total: page.total,
        limit,
        offset,
      };
      return results as T;
    }
  }

  return undefined;
}
