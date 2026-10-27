"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useDataset } from "@/lib/hooks";
import { formatDate, shortId } from "@/lib/format";
import {
  CopyButton,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  Panel,
} from "@/components/ui";
import { DatasetIcon, PlusIcon, SearchIcon } from "@/components/icons";

const INITIAL_VISIBLE = 20;

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: dataset, error, isLoading } = useDataset(params.id);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(INITIAL_VISIBLE);

  const filteredItems = useMemo(() => {
    if (!dataset) return [];
    const query = search.trim().toLowerCase();
    if (!query) return dataset.items;
    return dataset.items.filter(
      (item) =>
        item.question.toLowerCase().includes(query) ||
        item.ground_truth.toLowerCase().includes(query) ||
        item.reference_contexts.some((context) => context.toLowerCase().includes(query)),
    );
  }, [dataset, search]);

  if (isLoading) return <LoadingBlock label="Loading dataset" />;
  if (error) return <ErrorNotice error={error} title="Could not load this dataset" />;
  if (!dataset) return <ErrorNotice error={new Error("Dataset not found")} />;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={`Dataset · ${shortId(dataset.id)}`}
        title={dataset.name}
        description={dataset.description ?? "No description was recorded for this dataset."}
        actions={
          <Link className="button primary" href={`/runs/new?dataset=${dataset.id}`}>
            <PlusIcon /> Run this dataset
          </Link>
        }
      />

      <section className="dataset-facts">
        <div>
          <span>Questions</span>
          <strong>{dataset.latest_version.item_count}</strong>
        </div>
        <div>
          <span>Version</span>
          <strong>v{dataset.latest_version.version_number}</strong>
        </div>
        <div>
          <span>Versions</span>
          <strong>{dataset.version_count}</strong>
        </div>
        <div>
          <span>Imported</span>
          <strong>{formatDate(dataset.latest_version.created_at)}</strong>
        </div>
        <div className="fact-wide">
          <span>Content hash</span>
          <strong>
            <code>{dataset.latest_version.content_hash}</code>
            <CopyButton value={dataset.latest_version.content_hash} />
          </strong>
        </div>
      </section>

      <Panel
        className="dataset-items"
        title="Immutable dataset version"
        aside={
          <span className="panel-note">
            {dataset.latest_version.source_filename ?? "JSONL import"}
          </span>
        }
      >
        <div className="result-toolbar">
          <label className="search-field">
            <SearchIcon />
            <span className="sr-only">Search dataset</span>
            <input
              type="search"
              placeholder="Search questions, answers, and contexts…"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setVisible(INITIAL_VISIBLE);
              }}
            />
          </label>
          <span className="panel-note">
            {filteredItems.length} of {dataset.items.length} shown
          </span>
        </div>

        {filteredItems.length ? (
          <div className="dataset-item-list">
            {filteredItems.slice(0, visible).map((item) => (
              <details className="dataset-item" key={item.id}>
                <summary>
                  <span className="item-index">{String(item.ordinal + 1).padStart(3, "0")}</span>
                  <span>{item.question}</span>
                  <span className="item-context-count">
                    {item.reference_contexts.length} context
                    {item.reference_contexts.length === 1 ? "" : "s"}
                  </span>
                </summary>
                <div className="dataset-item-body">
                  <div>
                    <h4>Reference answer</h4>
                    <p>{item.ground_truth}</p>
                  </div>
                  <div>
                    <h4>Reference contexts</h4>
                    {item.reference_contexts.map((context, index) => (
                      <p key={`${item.id}-ref-${index}`} className="reference-context">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        {context}
                      </p>
                    ))}
                  </div>
                  {Object.keys(item.item_metadata).length ? (
                    <div>
                      <h4>Metadata</h4>
                      <pre>{JSON.stringify(item.item_metadata, null, 2)}</pre>
                    </div>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
        ) : (
          <p className="muted-copy results-empty">No items match that search.</p>
        )}

        {visible < filteredItems.length ? (
          <button
            className="button secondary wide"
            type="button"
            onClick={() => setVisible((current) => current + 25)}
          >
            Load {Math.min(25, filteredItems.length - visible)} more
          </button>
        ) : null}
      </Panel>

      <div className="dataset-cta">
        <DatasetIcon />
        <div>
          <strong>Ready to test a pipeline?</strong>
          <p>
            This dataset is pinned by version. A future import creates a new version and leaves
            existing run evidence untouched.
          </p>
        </div>
        <Link className="button primary" href={`/runs/new?dataset=${dataset.id}`}>
          Start evaluation
        </Link>
      </div>
    </div>
  );
}
