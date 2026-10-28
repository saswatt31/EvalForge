# EvalForge deployment: free tier

This is the click-by-click guide for putting EvalForge online at zero monthly cost:

| Layer | Service | Free-tier shape |
| --- | --- | --- |
| Dashboard | Vercel Hobby | Next.js static/SSR app, global CDN |
| API + worker | Render free web service | One Docker container, 512 MB RAM, sleeps when idle |
| Metadata | Neon free Postgres (or Supabase free) | Serverless Postgres with a connection limit |
| Vector store | Qdrant Cloud free cluster | ~1 GB, one collection |
| Recorded data | Repository | Committed JSON export of the synthetic demo |

Nothing in the repository contains credentials. All secrets are entered in the Render, Vercel,
Neon/Supabase, or Qdrant dashboards. **Never paste an API key, password, or connection string into
a chat, issue, or commit.** This guide never asks for one.

What is live and what is recorded:

- **Live:** the API, the mini-suite evaluator, dataset import, runs, comparisons, and the recorded
  export's provenance. A live run is labelled `dashboard`, runs at most 10 queries, and keeps
  whatever latency it actually measures.
- **Recorded:** the committed `frontend/src/lib/recorded-demo.json`. It is generated from the
  synthetic reference corpus with the deterministic mock judge, and every screen that shows it says
  `Recorded` plus "Nothing on this screen is a live run or a live measurement." It is served only
  when the live API is unreachable, asleep past the wake budget, or has paused live runs.

## 0. Prerequisites

You need accounts on:

1. [GitHub](https://github.com) with the EvalForge repository pushed.
2. [Render](https://render.com).
3. [Qdrant Cloud](https://cloud.qdrant.io).
4. [Neon](https://neon.tech) **or** [Supabase](https://supabase.com).
5. [Vercel](https://vercel.com).

No local Docker and no paid plan is required. Render builds the backend image from
`backend/Dockerfile`.

## 1. Qdrant Cloud

1. Sign in at <https://cloud.qdrant.io>.
2. Click **Clusters -> Create cluster**.
3. Choose the **Free** tier, a region near the Render region (the blueprint uses `oregon`; a US
   West region keeps latency low), and a name such as `evalforge`.
4. Click **Create**. Wait until the cluster status is **Healthy**.
5. Open the cluster and copy the **REST endpoint**. It looks like
   `https://<cluster-id>.<region>.cloud.qdrant.io:6333`.
6. Open **Data access control** (or **API keys**), create a key named `evalforge-render`, and copy it
   once into a password manager. Qdrant shows it only at creation time.
7. Do not create a collection by hand. The API creates `evalforge_reference_v1` and indexes the 28
   bundled documents on first boot, then only counts points on later boots.

Keep both values out of the repository. Render will prompt for them in step 4.

## 2. Postgres: Neon (recommended) or Supabase

### Option A: Neon

1. Sign in at <https://console.neon.tech>.
2. Click **New project**, choose a name such as `evalforge`, and a region near Render (`us-west-2`
   is a good match for `oregon`).
3. Choose the free plan and create the project.
4. On the project dashboard, click **Connect**.
5. Select the **connection string** tab. Copy the string that starts with `postgresql://` and
   includes the role, password, host, and database name.
6. Prefer the **direct** or **session** connection (not a transaction pooler) for this
   single-instance deployment. If you must use a pooler, use the session-mode port, not the
   transaction-mode port.
7. Keep `sslmode=require` or `channel_binding=require` if Neon includes it. EvalForge strips those
   libpq-only parameters and enables TLS from `EVALFORGE_DATABASE_SSL=true`.

### Option B: Supabase

1. Sign in at <https://supabase.com/dashboard>.
2. Click **New project**, choose a name and region, and set a database password you save in a
   password manager.
3. Wait for the project to finish provisioning.
4. Click **Project Settings -> Database**.
5. Under **Connection string**, choose **URI** and copy the direct or session connection string.
6. Use the direct/session connection. The transaction pooler (port 6543) can break prepared
   statements; this deployment does not disable them, so avoid it.
7. As with Neon, leave `sslmode=require` in place if present.

The schema is created by `alembic upgrade head`, which the container runs before Uvicorn starts.
No SQL needs to be pasted into a dashboard.

## 3. Deploy the API on Render

The repository contains a Render Blueprint at `render.yaml`.

1. Sign in at <https://dashboard.render.com>.
2. Click **New -> Blueprint**.
3. Connect GitHub if prompted and select the EvalForge repository and the `main` branch.
4. Render reads `render.yaml` and shows the `evalforge-api` service. Confirm:
   - **Environment:** Docker
   - **Plan:** Free
   - **Region:** Oregon (or the region you chose for Qdrant/Postgres)
   - **Health check path:** `/health`
5. Click **Apply** or **Create service**.
6. Render prompts for every `sync: false` variable. Fill them in:

   | Variable | Value |
   | --- | --- |
   | `EVALFORGE_DATABASE_URL` | The Neon/Supabase Postgres string from step 2 |
   | `EVALFORGE_CORS_ORIGINS` | `["https://placeholder.vercel.app"]` for now; replace after step 5 |
   | `EVALFORGE_QDRANT_URL` | The Qdrant REST endpoint from step 1 |
   | `EVALFORGE_QDRANT_API_KEY` | The Qdrant API key from step 1 |
   | `EVALFORGE_GROQ_API_KEY` | Optional. Leave blank for the deterministic mock judge |

   `EVALFORGE_WRITE_API_TOKEN` and `EVALFORGE_LIVE_RUN_IP_HASH_SALT` use `generateValue: true`; Render
   creates them. Open the service's **Environment** tab after the first deploy and copy the write
   token into a password manager if you want to start runs from the CLI or the dashboard.
7. Click **Deploy**. The first build installs Python dependencies in Docker and can take several
   minutes.
8. Watch **Logs**. A healthy boot ends with lines similar to:

   ```text
   Running upgrade ... -> 8f3c1a2d4e56, add live-run client IP hash and date indexes
   Reference index ready: collection=evalforge_reference_v1 documents=28
   Application startup complete.
   ```

9. Copy the service URL, for example `https://evalforge-api.onrender.com`.

If the build fails, read the first error in the build log. The usual causes are a typo in
`EVALFORGE_DATABASE_URL` (it must start with `postgres://` or `postgresql://`; EvalForge rewrites it
to `postgresql+asyncpg://`) or a missing Qdrant key. The API still boots when Qdrant indexing fails,
so `/health` alone is not proof that reference runs will work.

## 4. Deploy the dashboard on Vercel

1. Sign in at <https://vercel.com/new>.
2. Import the same GitHub repository.
3. Configure the project:
   - **Framework preset:** Next.js
   - **Root directory:** `frontend`
   - **Build command:** `npm run build`
   - **Install command:** `npm ci --legacy-peer-deps`
   - **Output directory:** leave the framework default
4. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL` = the Render service URL from step 3, without `/api/v1`
     (for example `https://evalforge-api.onrender.com`)
   - `NEXT_PUBLIC_BACKEND_WAKE_TIMEOUT_MS` = `20000` (the cold-start budget; 20000 is the default)
5. Click **Deploy** and wait for the build.
6. Copy the production URL, for example `https://evalforge.vercel.app`.

`NEXT_PUBLIC_*` variables are compiled into the browser bundle. Changing them requires a redeploy;
they are public by design and must never contain secrets.

## 5. Lock CORS to the Vercel origin

The API rejects `*` in production, so this ordering matters: deploy Vercel first, then set the exact
origin in Render.

1. In Render, open `evalforge-api -> Environment`.
2. Edit `EVALFORGE_CORS_ORIGINS` to a JSON array with the Vercel production URL:

   ```json
   ["https://evalforge.vercel.app"]
   ```

   Add preview domains only if you need them, for example
   `["https://evalforge.vercel.app", "https://evalforge-git-main-yourteam.vercel.app"]`.
3. Save. Render redeploys the service automatically.
4. If the dashboard still reports a CORS error, confirm the origin is `https`, has no trailing
   slash, and exactly matches the browser origin.

## 6. Post-deploy verification

Run these checks in order. They use only public URLs.

### 6.1 Liveness

```powershell
Invoke-RestMethod https://evalforge-api.onrender.com/health
```

Expect `status = ok`, `environment = production`, and a version. This endpoint is unauthenticated
and is what Render polls. A sleeping free service may take 30-60 seconds to answer the first time.

### 6.2 Readiness and metadata

```powershell
Invoke-RestMethod https://evalforge-api.onrender.com/api/v1/health/ready
Invoke-RestMethod https://evalforge-api.onrender.com/api/v1/meta
```

Expect a database-ready response and a `meta.live_runs` block with `enabled: true`,
`max_queries_per_run: 10`, `daily_run_cap: 20`, `per_ip_runs_per_window: 3`, and
`window_seconds: 3600`.

### 6.3 Interaction in the dashboard

1. Open the Vercel URL. The sidebar should read **API connected**, and the permanent banner should
   be absent.
2. Go to **Datasets**, click **Use sample dataset**, and import it. This is a write, so use the lock
   control in the sidebar and paste the Render `EVALFORGE_WRITE_API_TOKEN` value. The token stays in
   session storage.
3. Go to **New evaluation**. The form should state the free-tier cap and show **Queries: 10 of 112**
   (or the dataset size). Start the run with the reference target and the mock judge.
4. Open the run. It should complete with 10 query results and real measured latency. There is no
   demo/synthetic label on this run.
5. Start a second run and compare the two. The comparison should use the live run rows.
6. Trigger the per-network limit by creating the fourth run inside the hour. The API returns
   HTTP 429 with `detail.code = "live_runs_paused"` and a `Retry-After` header. The dashboard shows
   the recorded demo instead of a broken screen.

### 6.4 Verify the recorded fallback

1. In Vercel, temporarily set `NEXT_PUBLIC_API_URL` to an address that refuses connections, such as
   `http://127.0.0.1:9`, and redeploy.
2. Open the dashboard. It shows the waking screen, then after the timeout opens the recorded demo
   with a permanent blue **Recorded** banner.
3. Confirm that "Nothing on this screen is a live run or a live measurement." is visible on the
   overview, runs, run detail, compare, and new-run screens.
4. Restore the real `NEXT_PUBLIC_API_URL` and redeploy.

The browser E2E suite covers the same path with the backend off:
`npm run test:e2e:recorded` in `frontend/`.

### 6.5 Verify persistence

1. Wait for the Render service to sleep (free services sleep after inactivity).
2. Open the dashboard again. The waking screen appears, then either the live API catches up or the
   recorded demo opens.
3. After a live run, refresh the run list. Runs are stored in Postgres, not in the container, so
   they survive restarts and deploys.

## 7. Operating the free deployment

### Live-run guardrails

Configured by `render.yaml` and enforced by the API:

| Control | Default | Behavior |
| --- | --- | --- |
| Mini-suite | 10 queries | Executor evaluates only the first 10 dataset items and records the full dataset size |
| Per-network limit | 3 runs / 60 min | Salted IP hash counted from `X-Forwarded-For`; HTTP 429 with `Retry-After` |
| Daily cap | 20 runs / UTC day | Global across all visitors; HTTP 429 until 00:00 UTC |
| Judge cache | On | Repeated judge work is reused from `judge_cache` |
| Write token | Generated | Every write endpoint requires `X-API-Key` or a bearer token |

When any limit is hit, the API returns:

```json
{
  "detail": {
    "code": "live_runs_paused",
    "reason": "daily",
    "message": "The free-tier daily live-run budget is exhausted. ...",
    "retry_after_seconds": 3600
  }
}
```

The dashboard treats this as a hint to open the recorded demo. It does not silently show recorded
data as if it were live.

To pause live runs entirely without taking the API down, set
`EVALFORGE_LIVE_RUN_PROTECTION=true` and either lower `EVALFORGE_LIVE_RUN_DAILY_CAP` or set
`EVALFORGE_DEMO_MODE=true` (which also blocks writes and seeds the demo). To restore full local-like
behavior for a trusted demo, set `EVALFORGE_LIVE_RUN_PROTECTION=false` and raise the caps.

### Cold starts

Render free web services sleep after inactivity. The next request can take 30-60 seconds while the
container starts, migrations run, and the Qdrant count check completes.

- `/health` remains the platform health check.
- The dashboard probes the API; after `NEXT_PUBLIC_BACKEND_WAKE_TIMEOUT_MS` it opens the committed
  recorded demo and keeps a **Recorded** banner until the user retries or reloads.
- The **Retry live backend** button in the banner re-probes without a page reload.
- A sleeping backend does not lose data: runs and datasets are in Postgres.

### Free-tier limits

Approximate provider limits at the time of writing; confirm them on each provider's pricing page
before relying on them:

| Provider | Limit that matters here |
| --- | --- |
| Render free web | 512 MB RAM, shared CPU, sleeps when idle, no persistent disk |
| Neon free | Small storage and compute allowance, limited simultaneous connections |
| Supabase free | 500 MB database, pauses after a week of inactivity on some plans |
| Qdrant Cloud free | ~1 GB cluster; one small collection is enough for 28 documents |
| Vercel Hobby | Personal, non-commercial use; generous bandwidth for a portfolio demo |

The backend is stateless apart from Postgres and Qdrant, so Render's ephemeral disk is acceptable.
SQLite is not used in this deployment.

### Rotating secrets

1. Render `EVALFORGE_WRITE_API_TOKEN`: edit the value in the Render dashboard and redeploy. Existing
   dashboard sessions must paste the new token.
2. Qdrant API key: create a new key in Qdrant Cloud, update `EVALFORGE_QDRANT_API_KEY` in Render, then
   delete the old key.
3. Postgres password: rotate it in Neon/Supabase, update `EVALFORGE_DATABASE_URL` in Render, and
   redeploy.
4. `EVALFORGE_LIVE_RUN_IP_HASH_SALT`: changing it resets per-network continuity for the current rate
   window; historical hashes stay in the database but no longer match new ones.

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Render build fails at `pip install` | Dependency resolution on the pinned Python 3.11 image | Read the first error; do not pin a new package without updating `pyproject.toml` |
| `/health` is OK but `/api/v1/health/ready` is 503 | Wrong database URL or TLS setting | Check the URL, keep `EVALFORGE_DATABASE_SSL=true`, and confirm the database is awake |
| Startup log says Qdrant indexing failed | Wrong endpoint/key or the free cluster is paused | Fix the Qdrant variables; the API still serves reads |
| Dashboard says API unreachable | Wrong `NEXT_PUBLIC_API_URL`, or CORS not set | The URL is the Render origin without `/api/v1`; CORS must contain the exact Vercel origin |
| Browser console shows a CORS error | `EVALFORGE_CORS_ORIGINS` is missing the Vercel origin | Update it in Render and let the service redeploy |
| Run creation returns 429 | Per-network or daily cap reached | Wait for `Retry-After`, or use the recorded demo |
| Run creation returns 403 | Write token missing or wrong | Paste the Render token through the dashboard lock control |
| Recorded demo never appears | `NEXT_PUBLIC_BACKEND_WAKE_TIMEOUT_MS` is very high, or the API answers slowly | Lower the timeout, or use **Use recorded demo now** on the waking screen |
| Recorded data is stale | The seed or meta shape changed | Regenerate with `python -m scripts.export_recorded_demo` from `backend/` and commit the JSON |

## 9. What remains manual

These steps need your accounts and cannot be performed from the repository:

- creating the Qdrant Cloud cluster and key;
- creating the Neon or Supabase project and copying its connection string;
- creating the Render Blueprint and entering `sync: false` values;
- creating the Vercel project and setting `NEXT_PUBLIC_API_URL`;
- copying the Vercel URL back into `EVALFORGE_CORS_ORIGINS`;
- optionally adding `EVALFORGE_GROQ_API_KEY` for a real judge.

Once those are done, everything else in this document is verification, not setup.
