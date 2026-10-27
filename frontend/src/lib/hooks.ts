"use client";

import useSWR from "swr";

import {
  getComparison,
  getDataset,
  getDatasets,
  getMeta,
  getRun,
  getRunResults,
  getRuns,
} from "./api";
import type {
  CompareResponse,
  DatasetDetail,
  DatasetSummary,
  Meta,
  QueryResultPage,
  RunPage,
  RunStatus,
  RunSummary,
} from "./types";

const LIVE_INTERVAL = 1500;

export function useMeta() {
  return useSWR<Meta>("/meta", () => getMeta(), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
}

export function useDatasets() {
  return useSWR<DatasetSummary[]>("/datasets", () => getDatasets());
}

export function useDataset(id: string | null | undefined) {
  return useSWR<DatasetDetail>(id ? `/datasets/${id}` : null, () => getDataset(id as string));
}

export function useRuns(options: {
  limit?: number;
  offset?: number;
  status?: RunStatus;
  datasetVersionId?: string;
} = {}) {
  const key = [
    "runs",
    options.limit ?? 50,
    options.offset ?? 0,
    options.status ?? "all",
    options.datasetVersionId ?? "all",
  ].join(":");
  return useSWR<RunPage>(key, () => getRuns(options));
}

export function useRun(id: string | null | undefined) {
  return useSWR<RunSummary>(id ? `/runs/${id}` : null, () => getRun(id as string), {
    refreshInterval: (latest) =>
      latest && (latest.status === "queued" || latest.status === "running")
        ? LIVE_INTERVAL
        : 0,
  });
}

export function useRunResults(
  id: string | null | undefined,
  options: { limit?: number; offset?: number; active?: boolean } = {},
) {
  const limit = options.limit ?? 20;
  const offset = options.offset ?? 0;
  return useSWR<QueryResultPage>(
    id ? `/runs/${id}/results?limit=${limit}&offset=${offset}` : null,
    () => getRunResults(id as string, { limit, offset }),
    {
      refreshInterval: options.active ? LIVE_INTERVAL : 0,
    },
  );
}

export function useComparison(
  baselineId: string | null | undefined,
  candidateId: string | null | undefined,
) {
  return useSWR<CompareResponse>(
    baselineId && candidateId ? `/compare/${baselineId}/${candidateId}` : null,
    () => getComparison(baselineId as string, candidateId as string),
    { revalidateOnFocus: false },
  );
}
