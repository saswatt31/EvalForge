# Core Functions

This is a guided map of the code that carries the product's important behavior. It is useful for a
code review, an interview walkthrough, or deciding where a change belongs.

## Request, validation, and write access

| Function | Location | Why it matters |
| --- | --- | --- |
| `create_app` | `backend/app/main.py:33` | Builds FastAPI, CORS, the versioned router, and lifespan-owned worker. |
| `lifespan` | `backend/app/main.py:17` | Seeds demo data when configured, starts the run worker, and closes the engine on shutdown. |
| `require_write_access` | `backend/app/api/deps.py:21` | Enforces demo read-only mode and constant-time API-token checks. |
| `Settings.blank_secret_is_none` | `backend/app/core/config.py:65` | Prevents an empty environment value from turning into a blank secret that would behave unexpectedly. |
| `RunCreate.validate_target` | `backend/app/schemas/run.py:63` | Rejects bad HTTP targets/providers before a row or background job exists. |
| `RunCreate.validate_git_sha` | `backend/app/schemas/run.py` | Keeps CI metadata canonical and lowercase. |

Thin API handlers validate with Pydantic, call a service, and serialize the result. Business logic
does not live in the routes.

## Dataset ingestion

### `parse_jsonl` - `backend/app/services/datasets.py:50`

Reads a bounded JSONL payload, validates each line through `GoldenQuery`, reports line numbers, and
returns a summary including duplicate questions and the minimum context count. Blank lines are
ignored. It fails the whole import if any line fails; there is no partially valid dataset version.

### `canonical_content_hash` - `backend/app/services/datasets.py:92`

Serializes normalized records with sorted keys and SHA-256 hashes them. This is the deduplication
and version-identity key.

### `import_dataset` - `backend/app/services/datasets.py:106`

Finds or creates the logical dataset, returns the existing version when the content hash matches,
or creates the next immutable version and ordered items. A changed file creates history; it never
mutates an old version.

Pair this with `DatasetImportRequest` in `backend/app/schemas/dataset.py:29` for limits and unknown
field rejection.

## Run creation and configuration

### `canonical_run_hash` - `backend/app/services/runs.py:44`

Hashes the reproducible, non-secret configuration: dataset version, target kind, provider/model,
pipeline, judge mode/model/repeats, evaluator settings, and warm-ups. `name`, source, and git
metadata are intentionally excluded.

### `create_run` - `backend/app/services/runs.py:67`

Validates the dataset version and baseline, rejects LLM/Groq runs without a key, snapshots the
configuration, defaults the run name, sets `queued`, and calculates total queries. The API returns
201 only after this row exists; the CLI can then poll it.

### `sanitize_target_config` - `backend/app/services/runs.py:114`

Replaces header values with header names in API responses. The stored row still contains those
headers because the worker needs them for deferred execution, so the database is sensitive.

### `run_summary` - `backend/app/services/runs.py:121`

Joins the persisted run row to freshly computed aggregates. There is no aggregate table to drift.

### `RunManager.start` and `_mark_interrupted_runs` - `backend/app/workers/manager.py`

On startup, stale `running` rows fail with an interruption message and `queued` rows are put back on
the queue. The process owns one worker task.

## Target execution

### `build_target` - `backend/app/adapters/factory.py:13`

Chooses the HTTP adapter or the reference RAG target and validates URL/config/top-k. The worker and
the API therefore agree on which target configurations are legal.

### `HttpRAGTarget.query` - `backend/app/adapters/http.py:34`

Dispatches to JSON or streaming. The streaming path parses SSE JSON events, captures contexts and
usage, times the first non-whitespace delta, and builds measured TTFT. The JSON path times the
whole request and records target-reported TTFT separately.

### `QdrantReferenceIndex.ensure_indexed` - `backend/app/reference/index.py:43`

Creates or replaces the reference collection when the document count changes, then upserts the
corpus. The collection name and embedding dimensions are part of the run environment.

### `QdrantReferenceIndex.search` - `backend/app/reference/index.py:75`

Embeds the question with the same hash embedding used for documents and returns payload-complete
retrieved passages. These are the contexts the evaluator sees; golden contexts are not substituted.

### `ReferenceRAGTarget.query` - `backend/app/reference/target.py:41`

Runs retrieval, builds an extractive answer for the mock provider, or streams a Groq/Ollama answer
from the retrieved passages. It closes the index/provider through `aclose`.

## Evaluation and caching

### `MockEvaluator.evaluate` - `backend/app/evaluators/mock.py`

Provides deterministic lexical scores for context recall, faithfulness, and answer relevance. It is
a fixture: the UI and reports expose `judge_mode=mock` so no one mistakes it for real quality.

### `RagasEvaluator.evaluate` - `backend/app/evaluators/ragas.py:14`

Wraps the three Ragas collection metrics, normalizes finite scores to `[0, 1]`, and records judge
model and prompt version. Ragas failures become evaluator errors; the executor stores a failed
metric row instead of a fake zero.

### `build_cache_key` - `backend/app/evaluators/cache.py:26`

Hashes every input that can change a judgment: evaluator/version, prompt, judge model, metric,
repeat index, question, answer, contexts, and ground truth. Run IDs and timestamps are excluded.

### `evaluate_with_cache` - `backend/app/evaluators/cache.py:50`

Returns a cached sample when available, otherwise evaluates and writes the cache entry. It handles
the race where another writer inserts the same key by rolling back, reading, and recording a hit.

### `RunExecutor.execute` - `backend/app/workers/executor.py:46`

Marks a queued run running, builds the target/evaluator, executes items, and closes both in all
paths. Initialization failures become terminal `failed` runs with a useful message.

### `RunExecutor._run_items` - `backend/app/workers/executor.py:111`

Issues warm-ups, iterates items sequentially, checks cancellation between items, and chooses the
terminal status. Target failures produce partial/failed; judge failures reduce metric coverage.

### `RunExecutor._execute_item` - `backend/app/workers/executor.py:157`

Persists a target result, evaluates three direct metrics for every repeat, derives hallucination
from successful faithfulness samples, and commits the item. This is the transaction boundary that
makes progress durable.

### `RunExecutor._judge_metric` - `backend/app/workers/executor.py:224`

Calls the cache and stores either a successful score or an explicit failed judgment. A judge
outage does not erase the query result.

## Metrics and comparison

### `_metric_aggregate` - `backend/app/services/metrics.py:35`

Groups samples by query, averages repeats per query, then macro-averages across valid queries.
Coverage and failed samples are returned with the mean.

### `aggregate_run_metrics` - `backend/app/services/metrics.py:54`

Builds all aggregates for a run: direct metrics, derived hallucination, p50/p95 latency, TTFT
counts by provenance, token throughput, success rate, and cache hits/misses. Failed queries and
missing TTFT are excluded from the relevant denominators.

### `percentile` - `backend/app/services/metrics.py:20`

Implements linear interpolation over sorted measurements. It is deterministic and testable; it is
not a p99 implementation and does not claim significance.

### `compare_runs` - `backend/app/services/runs.py:299`

Computes candidate-minus-baseline rows and relative deltas for quality, success, latency, TTFT, and
throughput. It is descriptive: mismatched dataset/judge comparisons are not currently blocked.

## CLI and CI gate

### `_check_thresholds` - `backend/app/cli.py:248`

Checks each configured bound against the aggregate. A missing metric fails the gate. There is no
tolerance in v1; strictness is explicit.

### `_markdown` - `backend/app/cli.py:271`

Produces the PR report: run identity, status, judged coverage, failed samples, latency, success,
cache evidence, and status. It refuses to hide null metrics behind zeroes.

### `_run_command` - `backend/app/cli.py:349`

Imports the dataset, creates the run, streams progress to stderr, prints JSON or human output,
writes markdown, and converts status/threshold problems into exit code 1.

### `action.yml` - `action/action.yml`

Sets up Python and `httpx`, maps action inputs to CLI flags, runs the CLI with `--source ci`, writes
outputs and a fallback report, uploads artifacts, upserts the PR comment, and enforces the recorded
exit code.

## API client and frontend

### `apiRequest` - `frontend/src/lib/api.ts:112`

Single fetch boundary: normalizes errors, injects the write token, and parses API error shapes. This
keeps token handling and error presentation out of page components.

### `metricScoreTone` - `frontend/src/lib/format.ts:111`

Applies direction-aware coloring for per-query metrics; hallucination is inverted so a lower value
is good. This is a readability aid, not a statistical judgment.

### `useRun` / `useRuns` - `frontend/src/lib/hooks.ts`

SWR data hooks with refresh intervals for active runs. Polling is intentionally simpler than
WebSockets and matches the persisted progress model.

### `QueryResults` - `frontend/src/components/QueryResults.tsx:92`

Renders per-query evidence with pagination: answer, contexts, latency provenance, and metric
details. Missing scores remain `n/a`, and failed judgments are visible.

### `CompareView` - `frontend/src/components/CompareView.tsx:186`

Selects a baseline/candidate, computes zero-safe mean quality, groups quality versus latency
metrics, and labels deltas without claiming significance.

### `NewRunForm` - `frontend/src/components/NewRunForm.tsx:28`

Collects target/provider/judge/version settings, surfaces capability metadata, and explains
write-token state. The API remains the validation authority.

### `AppShell` - `frontend/src/components/AppShell.tsx:117`

Responsive navigation, API health indicator, write-token control, and demo state. It is the shell
that keeps the dashboard usable on desktop and mobile.

## Tests worth reading first

- `backend/tests/integration/test_run_execution.py` - reference run, cache hit/miss behavior, and
  target failure.
- `backend/tests/integration/test_executor_errors.py` - judge outage, initialization failure, and
  cancellation.
- `backend/tests/unit/test_cli.py` - CLI waits, thresholds, markdown, compare, and API errors.
- `backend/tests/integration/test_dataset_api.py` - validation, versions, and deduplication.
- `frontend/src/components/RunMetrics.test.tsx` - metric direction and coverage presentation.
- `frontend/e2e/evaluation.spec.ts` - the complete browser journey and mobile navigation.
