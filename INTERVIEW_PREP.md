# EvalForge Interview Preparation

## 60-second pitch

EvalForge is an end-to-end evaluation harness for RAG systems. You upload an immutable golden
dataset, point it at a reference RAG pipeline or your own HTTP endpoint, and run an evaluation that
scores context recall, faithfulness, answer relevance, and a derived hallucination rate while also
measuring p50/p95 latency and TTFT provenance. Results are stored per query with the retrieved
contexts, answers, judge reasons, cache evidence, and configuration snapshot.

The system is more than a dashboard: it has a FastAPI/SQLite backend, a single-process async worker,
Qdrant retrieval, Ragas and deterministic mock judges, a Next.js UI, a CLI with strict thresholds,
a composite GitHub Action that comments on PRs, Playwright E2E tests, and a read-only demo mode. I
was deliberate about not hiding uncertainty: missing judgments are excluded and counted, mock
scores are labelled, target-reported TTFT is not presented as measured, and the architecture notes
where the single-node design stops scaling.

## Three-minute architecture walkthrough

1. **Ingestion.** JSONL is validated line by line, canonicalized, hashed, and stored as an immutable
   dataset version. Re-uploading identical content returns the existing version.
2. **Run creation.** A configuration snapshot (target, pipeline, judge, repeats, warm-ups) is
   validated and hashed. The run references a dataset version, not "latest". The row is queued
   before the API responds.
3. **Execution.** One asyncio worker consumes the queue. For each question it calls the target,
   persists the answer/contexts/latency/TTFT, evaluates three direct metrics per repeat, consults a
   cross-run cache, and derives hallucination from faithfulness. Target failures and judge failures
   are stored differently.
4. **Aggregation.** Means are macro averages over queries with valid judgments. Coverage and failed
   samples are returned beside every mean. Latency percentiles use successful calls only.
5. **Comparison.** The API returns delta rows for quality, success, latency, TTFT, and throughput;
   the UI groups them and labels direction. It is descriptive, not a significance test.
6. **Gate.** The CLI polls to a terminal state, applies optional strict thresholds, emits JSON and
   markdown, and returns exit code 0/1/2. The GitHub Action maps inputs, uploads evidence, upserts
   one PR comment, and enforces the exit code.
7. **Operations.** Demo mode seeds read-only synthetic runs. Startup reconciliation handles
   interrupted runs. SQLite WAL and a single process keep the deployment simple and honest.

## Demo script

```powershell
# API
Set-Location backend
$env:EVALFORGE_WRITE_API_TOKEN = "local-demo-token"
alembic upgrade head
uvicorn app.main:app --reload

# Web (second terminal)
Set-Location frontend
npm run dev
```

Then:

1. Open the dashboard and click the lock control to enter the token.
2. Download the sample dataset or import `backend/data/golden_dataset.jsonl`.
3. Create two reference runs with `mock`/`mock`, top-k 2 and top-k 6.
4. Open the run detail and point to per-query contexts, answers, metrics, and cache counts.
5. Compare the runs and explain quality versus latency deltas.
6. Show the CLI markdown report and the composite action file.
7. Run `npm run test:e2e` to show the browser journey is automated.

If asked to prove missing-data behavior: explain that a judge outage produces failed metric rows,
not zero scores, and the API reports coverage. If asked to prove reproducibility: show the config
hash, pinned dataset version, judge/prompt versions, and cache key inputs.

## Key design decisions

| Decision | Reason | Cost |
| --- | --- | --- |
| SQLite + Alembic | One-file deployment, simple backup, enough for one team | Single writer, one API process |
| In-process asyncio queue | No Redis/Celery to operate; easy end-to-end reasoning | Jobs are not durable across a crash |
| Immutable dataset versions | Honest historical comparisons | More rows and explicit version selection |
| Store per-query evidence | Auditable aggregates and judge reasons | More storage and larger payloads |
| Ragas behind an evaluator interface | RAG-specific metrics without coupling the worker | Judge behavior changes with Ragas/prompt versions |
| Deterministic mock judge | Fast, reproducible tests and CI | Not evidence of real RAG quality |
| Judge cache keyed by all inputs | Avoid duplicate paid calls across identical runs | No TTL; model drift can hide |
| Derived hallucination | One fewer noisy/expensive judge | Only as meaningful as faithfulness |
| TTFT provenance | Avoid fake precision from non-streaming targets | Some runs honestly have null TTFT |
| p50/p95 only | Small sample sets make p99 misleading | Less tail detail than a production SLO tool |
| Hash embedding for reference corpus | Offline, deterministic demo | Lexical, not semantic retrieval |
| Strict thresholds | Simple gate semantics | No tolerance or statistical confidence |

## Metrics: answers to have ready

### Why macro-average?

The dataset is a set of equally important questions. A long answer should not dominate because it
contains more claims. Every query contributes one value; repeats are averaged inside the query
first, then queries are averaged.

### What happens when a judge fails?

A `metric_scores` row is written with `status=failed`, `score=null`, and an error/context. The query
result remains. The aggregate ignores that sample and reports `failed_samples` and lower
`judged_queries`. It is never converted to zero. The CLI threshold check treats a missing aggregate
as a failure.

### What is hallucination rate?

For each query, `1 - mean(successful faithfulness samples)`, then the macro average across queries
with valid faithfulness. It is a proxy for unsupported claims, not a calibrated probability that
the answer is false. It also does not reward completeness.

### Why not compare answer relevance alone?

Answer relevance can score a fluent, on-topic answer that is wrong. Pair it with faithfulness
(grounded in contexts) and context recall (did retrieval contain the evidence) plus inspection of
ground truth.

### Why are context recall and golden contexts separate?

The target must retrieve its own contexts. If EvalForge substituted the dataset's curated
`reference_contexts`, retrieval quality would be inflated. Golden contexts are stored for review,
not injected into the target call.

### What does TTFT mean here?

For streaming targets, it is measured from just before the request to the first non-whitespace
answer delta. For JSON targets, it is either null or a labelled `target_reported` value. EvalForge
does not infer TTFT from total latency.

### Why p50/p95 rather than average?

Means hide tail behavior. p50 describes the typical request and p95 gives a coarse tail signal. p99
is intentionally omitted because 112 queries cannot support a stable extreme-tail estimate.

### What do cache hits mean?

The cache stores successful judgments for the three direct metrics. Hits mean identical evaluator,
prompt, model, metric, repeat, question, answer, contexts, and ground truth. The API reports cache
hits/misses separately; derived hallucination rows are not counted as cacheable judge calls.

## Failure and edge-case stories

### Missing evidence is not zero

A target can fail, a judge can fail, and a metric can be undefined. These are three different
states. The schema stores failed query results and failed metric samples explicitly; aggregates
exclude them and report coverage. This prevents a judge outage from looking like a quality
collapse, and it prevents an empty metric from looking like a perfect score.

### Judge cache correctness

The cache key includes `sample_index` so repeated judge samples do not collapse into one result.
It also includes the evaluator and prompt versions, judge model, and all evidence. Cache insertion
handles a concurrent duplicate by rolling back and reading the winner.

### Cancellation and restart

Cancellation is cooperative: the endpoint marks the run, and the worker stops before the next item,
preserving completed evidence. On startup, runs stuck in `running` are marked failed with an
interruption message, while queued runs are re-enqueued.

### Source consistency

The backend models `dashboard`, `cli`, `ci`, and `demo` sources. The UI originally used different
names, which would have produced misleading badges and filtering. The types and badge now share the
backend enum, and tests cover the mapping.

### Compare zero vs missing

An aggregate of 0 is real evidence; a missing aggregate is not a zero. The comparison mean helper
was fixed to preserve zero as zero, while missing values still render `n/a`.

## Testing strategy

- **Unit:** JSONL validation, hash/canonicalization, metric math, percentile interpolation, cache
  keys, mock/Ragas normalization with fakes, provider parsing, CLI behavior.
- **Integration:** dataset versions/deduplication, run creation, reference execution with Qdrant,
  cache hits, target failure, judge outage, cancellation, manager reconciliation, demo seeding.
- **API:** write access, errors, run results pagination, compare, readiness.
- **Frontend:** API client/write-token behavior, format/direction helpers, metric panels, status and
  source badges.
- **E2E:** import a dataset, run an evaluation, inspect results, compare, and navigate on mobile.

The deterministic mock makes the boundary behavior testable without a paid provider. Real
Groq/Ollama paths are represented by contract-level fakes; they were not live-tested here.

## Security and operations answers

- Write access is a shared token with constant-time comparison, not user identity.
- Demo mode blocks all writes.
- CORS is restricted but not authentication.
- Provider keys are environment-only. Target headers are persisted for deferred execution and
  masked from API responses; the DB itself is sensitive.
- The hosted deployment would need SSRF filtering for user-supplied target URLs, provider budgets,
  retention, and stronger auth.
- The API must run one Uvicorn worker with the in-process queue and SQLite. Scaling starts with a
  durable queue and PostgreSQL, not more workers.

## Likely interview questions

**Why build this instead of using an existing eval platform?**

The goal was to demonstrate the full data path: immutable datasets, target adapters, judge
normalization, latency provenance, persistence, a UI, CI integration, and deployment tradeoffs. A
managed platform would hide the parts worth discussing. EvalForge also gives a deterministic
offline path, which most demos lack.

**How do you know the scores are trustworthy?**

You do not get certainty from one judge. EvalForge makes uncertainty visible: pinned judge/prompt
versions, repeat samples, coverage counts, cache evidence, per-query reasons, and clear conversion
of judge failures to missing data. It separates quality from latency and avoids fake precision.
Trust comes from inspecting evidence and tracking configurations, not from a single aggregate.

**Why not use Celery?**

The workload is I/O-bound and single-instance. An in-process queue removes a service and makes the
worker easy to reason about. The tradeoff is that a crash interrupts jobs and the API cannot scale
horizontally. At that boundary, the service/worker split makes a durable queue a transport change,
not a metric rewrite.

**How do you compare two runs fairly?**

Hold the dataset version and judge configuration constant, use the same target environment and
warm-up policy, and inspect per-query evidence plus coverage. The API currently reports deltas but
does not block mismatched configurations; that is a deliberate descriptive choice and a known next
guardrail. Latency comparisons also require comparable network/deployment conditions.

**What would you change first in production?**

Add a durable queue and Postgres, then SSRF protection, authentication, budget limits, and a
compatibility guard on comparisons. I would also add a judge-cache TTL/invalidation policy and a
minimum-coverage gate input. The current system is intentionally a strong single-team harness, not
a multi-tenant service.

**How did you test the CI gate?**

The CLI tests cover threshold failure and markdown generation. A local action-shell smoke run called
the live API, produced a successful run/report, and returned exit code 0. The action metadata and
workflow are included in the repository. Live PR comments require GitHub permissions and were not
available in the authoring environment.

**What was the hardest bug?**

The category of "missing is not zero" was the most important: judge failures, empty metric sets,
zero-valued aggregates, and absent TTFT all need different treatment. A generic display helper that
turned zero into missing hid a real comparison signal. The fix was to preserve zero for aggregates,
keep null for missing evidence, and make direction-aware formatting explicit.

**Why a hash embedding?**

It makes the reference path fully offline and deterministic, which is valuable for tests and a
public demo. It is lexical rather than semantic, so the docs call that out and the pipeline records
the embedding name. A real deployment can swap in a semantic embedding behind the same index
boundary, but scores across embeddings are not directly comparable.

**What would you monitor?**

Run success/partial/failed rates, query failure reasons, judge failure/coverage rates, p50/p95
latency and TTFT by target, cache hit rate, queue wait, and database lock/error rates. Also monitor
provider cost and rate-limit errors. A dashboard of aggregate means without coverage would be
misleading.

**How would you handle a flaky judge threshold?**

Repeat samples and use the cache to stabilize identical inputs. Add an explicit tolerance or paired
comparison only with a documented policy. Do not silently round missing data or change the metric
until the gate flakes. The current v1 keeps thresholds strict and exposes coverage, which is easier
to explain than a hidden tolerance.

**Why keep the reference corpus small?**

The project is a demonstrable harness, not a public RAG benchmark. 28 documents and 112 questions
exercise retrieval, scoring, pagination, and regression flows quickly. A larger corpus would add
licensing, embedding cost, and dataset-governance questions without improving the architecture
story. The interface supports larger datasets; the limits are explicit.

**What is the most important invariant?**

The run references an immutable dataset version and stores its configuration snapshot and raw
evidence. Without that, a comparison is not reproducible and every aggregate is a claim without a
paper trail.

## Numbers to remember

- 28 synthetic documents, 112 golden questions.
- 85 backend tests, 86.83% coverage, 80% floor.
- 22 frontend tests, 2 Playwright tests.
- Three direct judge metrics; hallucination is derived.
- p50 and p95 only; TTFT has three provenance values.
- 0 pass / 1 gate failure / 2 API or CLI failure.
- One API process and one worker in v1.
