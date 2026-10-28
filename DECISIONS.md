# EvalForge decision log

This file records the decisions behind the free-tier deployment so the trade-offs survive after the
implementation details. Each entry states the context, the decision, and what it costs.

## D1. Deploy the API and the worker as one Render container

**Context.** EvalForge runs evaluations in an in-process asyncio worker. A separate worker
deployment would need a shared queue, a second image, and a second set of limits on a free plan.

**Decision.** Keep one Docker image and one process on Render. `render.yaml` declares a single
`web` service; the container runs Alembic and then Uvicorn.

**Consequences.** The free plan's 512 MB and single instance are sufficient for a demo. A process
restart interrupts in-flight work, and horizontal scaling is still out of scope. The queue remains
in-memory by design; run rows are the durable record.

## D2. Use Postgres in production, keep SQLite locally

**Context.** Render's free plan has no persistent disk, while the local workflow already relies on
SQLite.

**Decision.** `EVALFORGE_DATABASE_URL` accepts both. The settings layer normalizes `sqlite://`,
`postgres://`, and `postgresql://` into async SQLAlchemy URLs. Hosted Postgres gets pool settings
and TLS through `EVALFORGE_DATABASE_SSL`; libpq-only query parameters (`sslmode`,
`channel_binding`, pooler hints) are stripped before asyncpg sees the URL. Alembic remains the only
schema path.

**Consequences.** The same code runs on a laptop and on managed Postgres. Supabase's transaction
pooler is not recommended because prepared statements are not disabled; use direct or session
connections. CI applies the migration to both SQLite and a real Postgres service.

## D3. Count live-run usage in the database, not in memory

**Context.** A free public demo needs a per-network limit and a global daily cap. In-memory counters
reset on every deploy and are wrong across processes.

**Decision.** Add a nullable `client_ip_hash` to `runs`, with indexes on
`(client_ip_hash, created_at)` and `created_at`. The API resolves the caller from
`X-Forwarded-For` (Render's proxy) or the socket peer, salts and hashes it, and counts guarded runs
before creating a new row. A process-local `asyncio.Lock` makes the check-then-create sequence
atomic for the single instance.

**Consequences.** Usage survives restarts and deploys, and raw IPs are never stored. The salt is a
secret; rotating it resets continuity for the current window. A multi-instance deployment would
need a distributed lock or a database constraint.

## D4. Cap each live run at a 10-query mini-suite

**Context.** The bundled dataset has 112 queries. A full run with three judged metrics and repeats
can consume real judge tokens and wall time, which is unacceptable for an unauthenticated demo.

**Decision.** When `EVALFORGE_LIVE_RUN_PROTECTION=true`, `create_run` records the full dataset size
but limits `total_queries` to `EVALFORGE_LIVE_RUN_MAX_QUERIES` (default 10). The executor slices the
dataset items to that count. `/meta` exposes the policy, and the new-run form shows
"10 of 112".

**Consequences.** Visitors get a real, measured evaluation rather than a slideshow, without
unbounded cost. Aggregate scores are computed over 10 queries and are less stable than a full run;
the UI and API still report the query count so the sample size is visible. Locally, protection is
off and full runs remain available.

## D5. Return an explicit paused response instead of hiding the limit

**Context.** A rate-limited visitor must not be told a run failed for an unrelated reason.

**Decision.** When a limit is hit, `POST /runs` returns HTTP 429 with
`detail.code = "live_runs_paused"`, a reason (`per_ip` or `daily`), a human-readable message, and a
`Retry-After` header. The dashboard recognizes this shape and opens the recorded demo.

**Consequences.** Limits are observable and testable. The frontend must keep the response contract
in sync; tests cover the 429 path at the API and the fallback path in the browser.

## D6. Fall back to a committed recorded export, never to fabricated live data

**Context.** Render free services sleep. A portfolio visitor should see the product, not a blank
error page, but must not mistake synthetic data for a live measurement.

**Decision.** `backend/scripts/export_recorded_demo.py` generates
`frontend/src/lib/recorded-demo.json` from the actual deterministic demo seed, the actual metadata
builder, and the actual run service. The file is committed and imported lazily only after the wake
timeout, an unreachable API, or a 429 pause. Every recorded screen carries a permanent **Recorded**
banner stating that nothing is a live run or measurement.

**Consequences.** The fallback cannot drift into invented numbers, but the JSON must be regenerated
whenever the seed or response shape changes. The export is about 0.9 MB and stays out of the initial
live bundle because it is a dynamic import. A recorded demo is a product tour, not evidence about a
real RAG system.

## D7. Lock CORS to the Vercel origin

**Context.** The browser calls the Render API directly, and the frontend URL is not known until
Vercel deploys.

**Decision.** CORS origins come from `EVALFORGE_CORS_ORIGINS` as a JSON array. Production rejects
`*` at settings validation. The deploy order is Vercel first, then update the Render variable with
the exact origin.

**Consequences.** No wildcard CORS in production. A missing or stale origin is a visible browser
error, documented in `DEPLOYMENT.md`; preview deployments need to be added explicitly.

## D8. Index the reference corpus on startup only when empty

**Context.** Qdrant Cloud must contain the reference collection before a reference run, but
re-indexing 28 documents on every boot is wasted work and a failure risk.

**Decision.** `ensure_reference_index` builds the collection name, client, and embedding exactly as
the target does, then calls the existing idempotent `ensure_indexed`. A count match is a no-op.
Failure is logged and the API still starts; reference runs retry on demand.

**Consequences.** The first boot after cluster creation writes 28 points. Later boots cost one count
query. A corpus change with an unchanged document count still requires deleting the collection
(count-based invalidation is a pre-existing limitation).

## D9. Keep secrets in dashboards and examples in the repository

**Context.** The deployment needs a write token, a database password, a Qdrant key, and optionally a
Groq key.

**Decision.** `render.yaml` uses `generateValue` for the write token and IP salt, `sync: false` for
provider values, and commits no secret. `.env.example`, `backend/.env.example`, and
`frontend/.env.example` contain placeholders only. Documentation tells the operator where to click,
never what value to paste.

**Consequences.** The repository can be public. Setup requires manual dashboard work, which
`DEPLOYMENT.md` lists explicitly. A full-history secret scan runs in CI.

## D10. Verify the deployment contract in CI

**Context.** Docker and hosted services are not available in the authoring environment.

**Decision.** CI keeps the existing lint, type, test, build, and E2E jobs, and adds:
a Postgres service job that applies Alembic and checks the new column through asyncpg; a
backend-off Playwright job that asserts the waking state and the recorded fallback; and a
full-history gitleaks job.

**Consequences.** The migration path, fallback, and secret hygiene are checked on every push.
Render cold starts, Qdrant Cloud, Neon/Supabase, and Vercel remain deployment-time checks and are
covered by the manual verification list in `DEPLOYMENT.md`.
