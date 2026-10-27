"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { ApiError, importDataset, SAMPLE_DATASET_URL } from "@/lib/api";
import { useDatasets, useMeta } from "@/lib/hooks";
import { formatBytes, formatDate, shortId } from "@/lib/format";
import type { ValidationIssue } from "@/lib/types";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
} from "@/components/ui";
import { ArrowIcon, DownloadIcon, PlusIcon, RunsIcon } from "@/components/icons";

export default function DatasetsPage() {
  const router = useRouter();
  const { data: datasets, error, isLoading, mutate } = useDatasets();
  const { data: meta } = useMeta();
  const fileInput = useRef<HTMLInputElement>(null);

  const [showImport, setShowImport] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [jsonl, setJsonl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<unknown>(null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [loadingSample, setLoadingSample] = useState(false);

  const readOnly = Boolean(meta?.demo_mode);

  function openImport() {
    setShowImport(true);
    window.setTimeout(() => fileInput.current?.focus(), 50);
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setIssues([]);
    if (meta && file.size > meta.max_dataset_bytes) {
      setImportError(
        new Error(
          `${file.name} is ${formatBytes(file.size)}; the limit is ${formatBytes(meta.max_dataset_bytes)}.`,
        ),
      );
      return;
    }
    try {
      const text = await file.text();
      setJsonl(text);
      setFilename(file.name);
      if (!name.trim()) setName(file.name.replace(/\.(jsonl|ndjson|json|txt)$/i, ""));
      setImportError(null);
    } catch {
      setImportError(new Error("Could not read that file."));
    }
  }

  async function loadSample() {
    setLoadingSample(true);
    setImportError(null);
    try {
      const response = await fetch(SAMPLE_DATASET_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(`Sample download failed (${response.status}).`);
      const text = await response.text();
      setJsonl(text);
      setFilename("golden_dataset.jsonl");
      if (!name.trim()) setName("Reference technical QA · sample");
      setShowImport(true);
    } catch (errorValue) {
      setImportError(errorValue);
    } finally {
      setLoadingSample(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setImportError(null);
    setIssues([]);
    if (!jsonl.trim()) {
      setImportError(new Error("Choose a JSONL file or paste dataset content."));
      return;
    }
    setImporting(true);
    try {
      const result = await importDataset({
        name: name.trim(),
        description: description.trim() || null,
        filename,
        jsonl,
      });
      await mutate();
      router.push(
        `/datasets/${result.dataset.id}${result.created_version ? "" : "?existing=1"}`,
      );
    } catch (errorValue) {
      setImportError(errorValue);
      if (errorValue instanceof ApiError) {
        const detail = errorValue.detail;
        if (detail && typeof detail === "object" && Array.isArray((detail as Record<string, unknown>).errors)) {
          setIssues(errorValue.issues);
        }
      }
      setImporting(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Golden datasets"
        title="The questions you refuse to guess about."
        description="Every import creates an immutable version. Runs pin a version ID, so editing a file can never rewrite historical results."
        actions={
          <>
            {meta?.sample_dataset_available ? (
              <button className="button secondary" type="button" onClick={() => void loadSample()} disabled={loadingSample}>
                <DownloadIcon /> {loadingSample ? "Loading sample…" : "Use sample dataset"}
              </button>
            ) : null}
            <button className="button primary" type="button" onClick={openImport} disabled={readOnly}>
              <PlusIcon /> Import dataset
            </button>
          </>
        }
      />

      {error ? <ErrorNotice error={error} title="Could not load datasets" /> : null}
      {isLoading ? <LoadingBlock label="Loading datasets" /> : null}

      <div className="datasets-layout">
        <div className="dataset-catalogue">
          {datasets?.length ? (
            datasets.map((dataset) => (
              <Link className="dataset-card" key={dataset.id} href={`/datasets/${dataset.id}`}>
                <div className="dataset-card-top">
                  <span className="dataset-icon">
                    <RunsIcon />
                  </span>
                  <span className="dataset-version">
                    v{dataset.latest_version.version_number}
                  </span>
                </div>
                <h2>{dataset.name}</h2>
                <p>{dataset.description ?? "No description."}</p>
                <div className="dataset-stats">
                  <span>
                    <b>{dataset.latest_version.item_count}</b> queries
                  </span>
                  <span>
                    <b>{dataset.version_count}</b> version{dataset.version_count === 1 ? "" : "s"}
                  </span>
                  <span>{formatDate(dataset.latest_version.created_at)}</span>
                </div>
                <div className="dataset-card-footer">
                  <code>{shortId(dataset.latest_version.content_hash, 12)}</code>
                  <span>
                    Inspect <ArrowIcon />
                  </span>
                </div>
              </Link>
            ))
          ) : !isLoading && !error ? (
            <Panel>
              <EmptyState
                title="No datasets yet"
                description="Use the bundled 112-query sample or upload your own JSONL. A dataset needs one question, one reference answer, and at least one reference context per line."
                action={
                  <button className="button primary" type="button" onClick={() => void loadSample()}>
                    Load the sample
                  </button>
                }
                secondaryAction={
                  <button className="button secondary" type="button" onClick={openImport}>
                    Upload JSONL
                  </button>
                }
              />
            </Panel>
          ) : null}
        </div>

        <aside className="dataset-import">
          {showImport || readOnly ? (
            <Panel title="Import a version" className="import-panel">
              {readOnly ? (
                <div className="notice compact">
                  <strong>Read-only demo.</strong> Dataset imports are disabled.
                </div>
              ) : (
                <form onSubmit={submit}>
                  <div className="dropzone">
                    <input
                      ref={fileInput}
                      id="dataset-file"
                      type="file"
                      accept=".jsonl,.ndjson,.json,.txt,text/plain"
                      onChange={(event) => void chooseFile(event)}
                    />
                    <label htmlFor="dataset-file">
                      <DownloadIcon />
                      <strong>{filename ? filename : "Choose a JSONL file"}</strong>
                      <span>
                        {jsonl
                          ? `${jsonl.split("\n").filter(Boolean).length} non-empty lines loaded`
                          : "or paste JSONL below"}
                      </span>
                    </label>
                  </div>

                  <label className="field">
                    <span>Dataset name</span>
                    <input
                      type="text"
                      required
                      maxLength={200}
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      placeholder="Support QA · v2"
                    />
                  </label>
                  <label className="field">
                    <span>
                      Description <em>optional</em>
                    </span>
                    <input
                      type="text"
                      maxLength={2000}
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      placeholder="What changed in this version?"
                    />
                  </label>
                  <label className="field">
                    <span>JSONL content</span>
                    <textarea
                      rows={8}
                      value={jsonl}
                      onChange={(event) => {
                        setJsonl(event.target.value);
                        setFilename(null);
                      }}
                      placeholder='{"question": "...", "ground_truth": "...", "reference_contexts": ["..."]}'
                    />
                    <small>
                      One object per line. Fields: question, ground_truth, reference_contexts,
                      optional metadata.
                    </small>
                  </label>
                  {importError ? <ErrorNotice error={importError} title="Import failed" /> : null}
                  {issues.length ? (
                    <ul className="issue-list">
                      {issues.map((issue, index) => (
                        <li key={`${issue.line ?? index}-${issue.message}`}>
                          {issue.line ? `Line ${issue.line}: ` : ""}
                          {issue.message}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <button className="button primary wide" type="submit" disabled={importing}>
                    {importing ? "Validating…" : "Import immutable version"}
                  </button>
                  {meta ? (
                    <p className="field-note">
                      Limit {formatBytes(meta.max_dataset_bytes)} · {meta.max_dataset_items}{" "}
                      queries per import
                    </p>
                  ) : null}
                </form>
              )}
            </Panel>
          ) : (
            <Panel title="Import JSONL" className="import-guide">
              <p>
                Bring a versioned golden set. The API validates every line, stores the content
                hash, and rejects malformed records with line numbers.
              </p>
              <button className="button primary" type="button" onClick={openImport}>
                Import a dataset
              </button>
              <div className="format-example">
                <span>Expected line</span>
                <pre>{`{
  "question": "What does TTFT measure?",
  "ground_truth": "...",
  "reference_contexts": ["..."],
  "metadata": {"topic": "latency"}
}`}</pre>
              </div>
            </Panel>
          )}
        </aside>
      </div>
    </div>
  );
}
