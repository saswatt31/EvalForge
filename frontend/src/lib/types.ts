export type RunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial"
  | "failed"
  | "cancelled";

export type RunSource = "dashboard" | "cli" | "ci" | "demo";
export type TargetKind = "reference" | "http";
export type JudgeMode = "mock" | "llm";
export type QueryStatus = "succeeded" | "failed";
export type JudgmentStatus = "succeeded" | "failed";
export type TTFTSource = "measured" | "target_reported" | "demo";

export interface MetricAggregate {
  mean: number | null;
  judged_queries: number;
  total_samples: number;
  failed_samples: number;
}

export interface LatencyAggregate {
  p50_ms: number | null;
  p95_ms: number | null;
  mean_ms: number | null;
  ttft_p50_ms: number | null;
  ttft_p95_ms: number | null;
  measured_ttft_count: number;
  target_reported_ttft_count: number;
  demo_ttft_count: number;
  mean_tokens_per_second: number | null;
}

export interface RunMetrics {
  context_recall: MetricAggregate;
  faithfulness: MetricAggregate;
  answer_relevance: MetricAggregate;
  hallucination_rate: MetricAggregate;
  latency: LatencyAggregate;
  success_rate: number | null;
  cache_hits: number;
  cache_misses: number;
}

export interface RunSummary {
  id: string;
  name: string;
  status: RunStatus;
  source: RunSource;
  target_kind: TargetKind;
  provider_name: string;
  model_name: string | null;
  target_config: Record<string, unknown>;
  pipeline_config: Record<string, unknown>;
  judge_mode: JudgeMode;
  judge_model: string;
  judge_repeats: number;
  warmup_count: number;
  config_hash: string;
  dataset_version_id: string;
  baseline_run_id: string | null;
  total_queries: number;
  completed_queries: number;
  failed_queries: number;
  error_message: string | null;
  git_sha: string | null;
  git_branch: string | null;
  pull_request_number: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  metrics: RunMetrics;
}

export interface RunPage {
  items: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetricScore {
  id: string;
  metric_name: string;
  sample_index: number;
  status: JudgmentStatus;
  score: number | null;
  reason: string | null;
  evaluator: string;
  judge_model: string;
  prompt_version: string;
  judge_cached: boolean;
  error_message: string | null;
  details: Record<string, unknown>;
}

export interface QueryResult {
  id: string;
  status: QueryStatus;
  question: string;
  ground_truth: string;
  answer: string | null;
  contexts: string[];
  ttft_ms: number | null;
  ttft_source: TTFTSource | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  tokens_per_second: number | null;
  error_message: string | null;
  metrics: MetricScore[];
}

export interface QueryResultPage {
  items: QueryResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface RunStatusResponse {
  id: string;
  status: RunStatus;
  completed_queries: number;
  failed_queries: number;
  total_queries: number;
}

export interface DatasetVersion {
  id: string;
  version_number: number;
  content_hash: string;
  source_filename: string | null;
  item_count: number;
  validation_summary: Record<string, unknown>;
  created_at: string;
}

export interface DatasetSummary {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  latest_version: DatasetVersion;
  version_count: number;
}

export interface DatasetItem {
  id: string;
  ordinal: number;
  question: string;
  ground_truth: string;
  reference_contexts: string[];
  item_metadata: Record<string, unknown>;
}

export interface DatasetDetail extends DatasetSummary {
  version: DatasetVersion;
  items: DatasetItem[];
}

export interface DatasetImportResponse {
  dataset: DatasetSummary;
  version: DatasetVersion;
  created_version: boolean;
}

export interface CompareRow {
  metric: string;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
  relative_delta: number | null;
}

export interface CompareResponse {
  baseline: RunSummary;
  candidate: RunSummary;
  rows: CompareRow[];
}

export interface MetaProvider {
  id: string;
  label: string;
  available: boolean;
  requires_key: boolean;
  base_url?: string;
}

export interface Meta {
  demo_mode: boolean;
  write_protected: boolean;
  database_ready: boolean;
  target_kinds: string[];
  providers: MetaProvider[];
  judge_modes: string[];
  max_dataset_bytes: number;
  max_dataset_items: number;
  max_result_page_size: number;
  sample_dataset_available: boolean;
}

export interface DatasetImportRequest {
  name: string;
  description?: string | null;
  filename?: string | null;
  jsonl: string;
}

export interface RunCreateRequest {
  name?: string;
  dataset_version_id: string;
  target_kind: TargetKind;
  provider_name: string;
  model_name?: string | null;
  target_config: Record<string, unknown>;
  pipeline_config: { top_k: number; prompt_version: string };
  judge_mode: JudgeMode;
  judge_model: string;
  judge_repeats: number;
  evaluator_config: { judge_provider: "groq" | "ollama" };
  warmup_count: number;
  baseline_run_id?: string | null;
}

export interface ValidationIssue {
  line?: number;
  field?: string;
  message: string;
}
