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
import { useBackendState } from "./backend";
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

function useDataScope(): "live" | "recorded" {
  return useBackendState().mode === "recorded" ? "recorded" : "live";
}

export function useMeta() {
  const scope = useDataScope();
  return useSWR<Meta>(`${scope}:/meta`, () => getMeta(), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
}

export function useDatasets() {
  const scope = useDataScope();
  return useSWR<DatasetSummary[]>(`${scope}:/datasets`, () => getDatasets());
}

export function useDataset(id: string | null | undefined) {
  const scope = useDataScope();
  return useSWR<DatasetDetail>(id ? `${scope}:/datasets/${id}` : null, () =>
    getDataset(id as string),
  );
}

export function useRuns(options: {
  limit?: number;
  offset?: number;
  status?: RunStatus;
  datasetVersionId?: string;
} = {}) {
  const scope = useDataScope();
  const key = [
    scope,
    "runs",
    options.limit ?? 50,
    options.offset ?? 0,
    options.status ?? "all",
    options.datasetVersionId ?? "all",
  ].join(":");
  return useSWR<RunPage>(key, () => getRuns(options));
}

export function useRun(id: string | null | undefined) {
  const scope = useDataScope();
  return useSWR<RunSummary>(id ? `${scope}:/runs/${id}` : null, () => getRun(id as string), {
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
  const scope = useDataScope();
  const limit = options.limit ?? 20;
  const offset = options.offset ?? 0;
  return useSWR<QueryResultPage>(
    id ? `${scope}:/runs/${id}/results?limit=${limit}&offset=${offset}` : null,
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
  const scope = useDataScope();
  return useSWR<CompareResponse>(
    baselineId && candidateId
      ? `${scope}:compare/${baselineId}/${candidateId}`
      : null,
    () => getComparison(baselineId as string, candidateId as string),
    { revalidateOnFocus: false },
  );
}
