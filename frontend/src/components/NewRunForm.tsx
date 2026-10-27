"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { createRun } from "@/lib/api";
import { useDatasets, useMeta, useRuns } from "@/lib/hooks";
import { shortId } from "@/lib/format";
import type { RunCreateRequest, TargetKind } from "@/lib/types";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
} from "./ui";
import { ArrowIcon, DatasetIcon } from "./icons";

const MOCK_MODEL = "mock-extractive-v1";

function defaultModel(provider: string): string {
  if (provider === "groq") return "llama-3.3-70b-versatile";
  if (provider === "ollama") return "llama3.1";
  return MOCK_MODEL;
}

export function NewRunForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: meta, error: metaError } = useMeta();
  const { data: datasets, error: datasetsError } = useDatasets();
  const { data: recentRuns } = useRuns({ limit: 100 });

  const [datasetId, setDatasetId] = useState(searchParams.get("dataset") ?? "");
  const [name, setName] = useState("");
  const [targetKind, setTargetKind] = useState<TargetKind>("reference");
  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState(MOCK_MODEL);
  const [url, setUrl] = useState("");
  const [streaming, setStreaming] = useState(true);
  const [headerName, setHeaderName] = useState("");
  const [headerValue, setHeaderValue] = useState("");
  const [topK, setTopK] = useState(5);
  const [warmup, setWarmup] = useState(0);
  const [judgeMode, setJudgeMode] = useState<"mock" | "llm">("mock");
  const [judgeProvider, setJudgeProvider] = useState<"groq" | "ollama">("groq");
  const [judgeModel, setJudgeModel] = useState("llama-3.3-70b-versatile");
  const [judgeRepeats, setJudgeRepeats] = useState(1);
  const [baselineId, setBaselineId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);

  const resolvedDatasetId =
    datasetId && datasets?.some((dataset) => dataset.id === datasetId)
      ? datasetId
      : (datasets?.[0]?.id ?? "");
  const selectedDataset = datasets?.find((dataset) => dataset.id === resolvedDatasetId);
  const baselineOptions = useMemo(
    () =>
      recentRuns?.items.filter(
        (run) => run.status === "succeeded" || run.status === "partial",
      ) ?? [],
    [recentRuns],
  );
  const readOnly = Boolean(meta?.demo_mode);

  function chooseProvider(next: string) {
    setProvider(next);
    setModel(defaultModel(next));
  }

  function chooseJudgeMode(next: "mock" | "llm") {
    setJudgeMode(next);
    if (next === "mock") {
      setJudgeModel(MOCK_MODEL);
    } else {
      setJudgeModel(judgeProvider === "ollama" ? "llama3.1" : "llama-3.3-70b-versatile");
    }
  }

  function chooseJudgeProvider(next: "groq" | "ollama") {
    setJudgeProvider(next);
    setJudgeModel(next === "ollama" ? "llama3.1" : "llama-3.3-70b-versatile");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    if (!selectedDataset) {
      setSubmitError(new Error("Choose a dataset version before starting the run."));
      return;
    }
    if (targetKind === "http" && !url.trim()) {
      setSubmitError(new Error("An HTTP target needs a URL."));
      return;
    }

    const headers =
      headerName.trim() && headerValue.trim()
        ? { [headerName.trim()]: headerValue.trim() }
        : {};

    const payload: RunCreateRequest = {
      dataset_version_id: selectedDataset.latest_version.id,
      target_kind: targetKind,
      provider_name: targetKind === "reference" ? provider : "custom",
      model_name: targetKind === "reference" ? model || defaultModel(provider) : model || null,
      target_config:
        targetKind === "http"
          ? { url: url.trim(), streaming, headers }
          : {},
      pipeline_config: { top_k: topK, prompt_version: "reference-rag-v1" },
      judge_mode: judgeMode,
      judge_model: judgeMode === "mock" ? MOCK_MODEL : judgeModel.trim(),
      judge_repeats: judgeRepeats,
      evaluator_config: { judge_provider: judgeProvider },
      warmup_count: warmup,
      baseline_run_id: baselineId || null,
    };
    if (name.trim()) payload.name = name.trim();

    setSubmitting(true);
    try {
      const run = await createRun(payload);
      router.push(`/runs/${run.id}`);
    } catch (error) {
      setSubmitError(error);
      setSubmitting(false);
    }
  }

  if (datasetsError) {
    return <ErrorNotice error={datasetsError} title="Could not load datasets" />;
  }
  if (!datasets) return <LoadingBlock label="Loading datasets" />;

  if (!datasets.length) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="New evaluation"
          title="Start with a golden dataset."
          description="A run needs immutable questions, reference answers, and the evidence a correct answer should rely on."
        />
        <Panel>
          <EmptyState
            title="No datasets imported"
            description="Import the bundled sample or upload your own JSONL. The sample is the fastest way to exercise the complete offline flow."
            action={
              <Link className="button primary" href="/datasets">
                <DatasetIcon /> Import a dataset
              </Link>
            }
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="New evaluation"
        title="Run the evidence."
        description={
          selectedDataset
            ? `${selectedDataset.name} · version ${selectedDataset.latest_version.version_number} · ${selectedDataset.latest_version.item_count} queries`
            : "Choose an immutable dataset version below."
        }
        actions={
          <Link className="button ghost" href="/runs">
            Back to runs
          </Link>
        }
      />

      {metaError ? <ErrorNotice error={metaError} title="Could not load workspace settings" /> : null}
      {readOnly ? (
        <div className="notice">
          <strong>This workspace is read-only.</strong> The public demo cannot queue new provider
          calls or write benchmark data.
        </div>
      ) : null}

      <form className="run-form" onSubmit={submit}>
        <div className="form-main">
          <Panel title="01 · Dataset" className="form-section">
            <label className="field">
              <span>Dataset version</span>
              <select
                value={resolvedDatasetId}
                onChange={(event) => setDatasetId(event.target.value)}
              >
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} · v{dataset.latest_version.version_number} ·{" "}
                    {dataset.latest_version.item_count} queries
                  </option>
                ))}
              </select>
            </label>
            {selectedDataset ? (
              <div className="field-note">
                Version hash <code>{shortId(selectedDataset.latest_version.content_hash, 12)}</code>
                {" · "}
                <Link href={`/datasets/${selectedDataset.id}`}>inspect dataset</Link>
              </div>
            ) : null}
            <label className="field">
              <span>
                Run name <em>optional</em>
              </span>
              <input
                type="text"
                placeholder="e.g. Hybrid retriever, k=6"
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
          </Panel>

          <Panel title="02 · Target" className="form-section">
            <div className="choice-grid target-choice">
              <button
                type="button"
                className={`choice ${targetKind === "reference" ? "selected" : ""}`}
                onClick={() => setTargetKind("reference")}
              >
                <strong>Reference RAG</strong>
                <span>Bundled corpus, Qdrant retrieval, extractive or LLM answers.</span>
              </button>
              <button
                type="button"
                className={`choice ${targetKind === "http" ? "selected" : ""}`}
                onClick={() => setTargetKind("http")}
              >
                <strong>HTTP endpoint</strong>
                <span>Your pipeline, supporting JSON or server-sent event responses.</span>
              </button>
            </div>

            {targetKind === "reference" ? (
              <>
                <label className="field">
                  <span>Answer provider</span>
                  <select value={provider} onChange={(event) => chooseProvider(event.target.value)}>
                    <option value="mock">Mock extractive · offline</option>
                    <option value="groq" disabled={meta ? !meta.providers.find((item) => item.id === "groq")?.available : false}>
                      Groq{meta && !meta.providers.find((item) => item.id === "groq")?.available ? " · key required" : ""}
                    </option>
                    <option value="ollama">Ollama · local</option>
                  </select>
                </label>
                <label className="field">
                  <span>Model</span>
                  <input
                    type="text"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder={defaultModel(provider)}
                  />
                </label>
              </>
            ) : (
              <>
                <label className="field">
                  <span>Query endpoint</span>
                  <input
                    type="url"
                    required
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="https://api.example.com/v1/answer"
                  />
                  <small>
                    POST JSON with <code>question</code>. Return <code>answer</code>,{" "}
                    <code>contexts</code>, and optional timing or token fields.
                  </small>
                </label>
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={streaming}
                    onChange={(event) => setStreaming(event.target.checked)}
                  />
                  <span>
                    Stream server-sent events
                    <small>Enables independently measured TTFT on the first answer token.</small>
                  </span>
                </label>
                <div className="field-pair">
                  <label className="field">
                    <span>
                      Auth header <em>optional</em>
                    </span>
                    <input
                      type="text"
                      value={headerName}
                      onChange={(event) => setHeaderName(event.target.value)}
                      placeholder="Authorization"
                    />
                  </label>
                  <label className="field">
                    <span>Header value</span>
                    <input
                      type="password"
                      value={headerValue}
                      onChange={(event) => setHeaderValue(event.target.value)}
                      placeholder="Bearer …"
                      autoComplete="off"
                    />
                  </label>
                </div>
                <p className="field-note">
                  Header names are stored; values are redacted from all API responses.
                </p>
              </>
            )}
          </Panel>

          <Panel title="03 · Retrieval & judge" className="form-section">
            <label className="field range-field">
              <span>
                Top-k retrieval <b>{topK}</b>
              </span>
              <input
                type="range"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
              <small>Number of reference passages supplied to the answer pipeline.</small>
            </label>

            <div className="field">
              <span>Judge</span>
              <div className="choice-grid judge-choice">
                <button
                  type="button"
                  className={`choice compact ${judgeMode === "mock" ? "selected" : ""}`}
                  onClick={() => chooseJudgeMode("mock")}
                >
                  <strong>Mock lexical</strong>
                  <span>Deterministic, offline, not evidence of real quality.</span>
                </button>
                <button
                  type="button"
                  className={`choice compact ${judgeMode === "llm" ? "selected" : ""}`}
                  onClick={() => chooseJudgeMode("llm")}
                >
                  <strong>Ragas + LLM</strong>
                  <span>Real judge calls. Requires a provider key or local Ollama.</span>
                </button>
              </div>
            </div>

            {judgeMode === "llm" ? (
              <div className="field-pair">
                <label className="field">
                  <span>Judge provider</span>
                  <select
                    value={judgeProvider}
                    onChange={(event) =>
                      chooseJudgeProvider(event.target.value as "groq" | "ollama")
                    }
                  >
                    <option value="groq">Groq</option>
                    <option value="ollama">Ollama</option>
                  </select>
                </label>
                <label className="field">
                  <span>Judge model</span>
                  <input
                    type="text"
                    value={judgeModel}
                    onChange={(event) => setJudgeModel(event.target.value)}
                    required
                  />
                </label>
              </div>
            ) : (
              <p className="field-note">
                Mock judgments are stored with the evaluator name and prompt version so they cannot
                be mistaken for Ragas scores.
              </p>
            )}

            <div className="field-pair">
              <label className="field">
                <span>Judge samples</span>
                <select
                  value={judgeRepeats}
                  onChange={(event) => setJudgeRepeats(Number(event.target.value))}
                >
                  {[1, 2, 3, 4, 5].map((value) => (
                    <option key={value} value={value}>
                      {value} {value === 1 ? "sample" : "samples"}
                    </option>
                  ))}
                </select>
                <small>Repeated samples reduce judge noise but multiply cost.</small>
              </label>
              <label className="field">
                <span>Warmup queries</span>
                <select
                  value={warmup}
                  onChange={(event) => setWarmup(Number(event.target.value))}
                >
                  {[0, 1, 2, 3].map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <small>Excluded from quality and latency aggregation.</small>
              </label>
            </div>
          </Panel>

          <Panel title="04 · Baseline" className="form-section">
            <label className="field">
              <span>
                Compare against <em>optional</em>
              </span>
              <select value={baselineId} onChange={(event) => setBaselineId(event.target.value)}>
                <option value="">No baseline</option>
                {baselineOptions.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.name} · {run.status}
                  </option>
                ))}
              </select>
              <small>
                Stores the relationship. Open Compare after both runs finish to inspect metric and
                latency deltas.
              </small>
            </label>
          </Panel>
        </div>

        <aside className="form-side">
          <div className="form-summary panel">
            <h2>Run summary</h2>
            <dl>
              <div>
                <dt>Dataset</dt>
                <dd>{selectedDataset?.name ?? "—"}</dd>
              </div>
              <div>
                <dt>Queries</dt>
                <dd>{selectedDataset?.latest_version.item_count ?? "—"}</dd>
              </div>
              <div>
                <dt>Target</dt>
                <dd>
                  {targetKind === "http"
                    ? "Custom HTTP"
                    : `${provider} · ${model || defaultModel(provider)}`}
                </dd>
              </div>
              <div>
                <dt>Retrieval</dt>
                <dd>top-{topK}</dd>
              </div>
              <div>
                <dt>Judge</dt>
                <dd>{judgeMode === "mock" ? "Mock lexical" : judgeModel}</dd>
              </div>
              <div>
                <dt>Est. judge calls</dt>
                <dd>
                  {(selectedDataset?.latest_version.item_count ?? 0) * 3 * judgeRepeats}
                </dd>
              </div>
            </dl>
            {targetKind === "reference" && provider !== "mock" && judgeMode === "mock" ? (
              <p className="summary-note">
                Target answers use a live provider; quality scores are still mock judgments. The
                run will say so explicitly.
              </p>
            ) : null}
            {judgeMode === "llm" ? (
              <p className="summary-note warning">
                Live judging is enabled. Review provider limits and cost before running.
              </p>
            ) : null}
            {submitError ? <ErrorNotice error={submitError} title="Could not start the run" /> : null}
            <button
              className="button primary wide"
              type="submit"
              disabled={submitting || readOnly}
            >
              {submitting ? "Queueing run…" : "Start evaluation"}
              {!submitting ? <ArrowIcon /> : null}
            </button>
            {readOnly ? <p className="summary-note">Unavailable in the read-only demo.</p> : null}
          </div>
        </aside>
      </form>
    </div>
  );
}
