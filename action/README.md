# EvalForge GitHub Action

Run an EvalForge evaluation from a pull request, enforce quality/latency thresholds, upload the
evidence, and keep one updated comment on the pull request.

The action is a thin wrapper around the repository's standalone `backend/app/cli.py`. It installs
Python and `httpx`, calls an EvalForge API that you host, and exits non-zero when the gate fails.

## Requirements

- An EvalForge API reachable from the GitHub runner.
- A dataset JSONL file in the checked-out repository.
- A write token when the API has `EVALFORGE_WRITE_API_TOKEN` configured.
- `actions/checkout` before this action, so the dataset exists in the workspace.
- Workflow permission `pull-requests: write` only if you want comments.

The action does **not** start an EvalForge API, Qdrant, or a RAG target. Those must already be
running. For a self-contained PR check, start the API as a previous job/service in the same
workflow or point `api-url` at a staging deployment.

## Example workflow

```yaml
name: RAG quality

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  evalforge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Evaluate RAG quality
        uses: OWNER/REPO/action@main
        with:
          api-url: https://evalforge.example.com/api/v1
          api-token: ${{ secrets.EVALFORGE_API_TOKEN }}
          dataset: evals/golden-dataset.jsonl
          name: PR ${{ github.event.pull_request.number }}
          target: http
          url: https://rag-staging.example.com/query
          streaming: "true"
          judge: llm
          judge-provider: groq
          judge-model: llama-3.3-70b-versatile
          min-context-recall: "0.75"
          min-faithfulness: "0.85"
          max-hallucination-rate: "0.15"
          max-p95-latency-ms: "2500"
          baseline: ${{ vars.EVALFORGE_BASELINE_RUN }}
```

Replace `OWNER/REPO` with the repository that contains this action. For a third-party dependency,
pin the action to a commit SHA instead of a moving branch.

For a reference-target smoke check, omit `url` and use:

```yaml
with:
  api-url: ${{ secrets.EVALFORGE_API_URL }}
  api-token: ${{ secrets.EVALFORGE_API_TOKEN }}
  dataset: evals/golden-dataset.jsonl
  target: reference
  provider: mock
  judge: mock
  min-faithfulness: "0.50"
```

Mock judgments are fixtures, not evidence of real RAG quality. Use `judge: llm` with a configured
Groq key or Ollama endpoint for a real quality gate.

## Inputs

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `api-url` | no | `http://localhost:8000/api/v1` | EvalForge API base including `/api/v1` |
| `api-token` | no | empty | Sent as `X-API-Key`; required when the API is write-protected |
| `dataset` | yes | - | Path to JSONL in the workspace |
| `name` | no | CLI default | Human-readable run name |
| `target` | no | `reference` | `reference` or `http` |
| `url` | no | empty | HTTP target URL; required when `target=http` |
| `streaming` | no | `false` | `true` requests SSE from an HTTP target |
| `provider` | no | `mock` | Reference answer provider: `mock`, `groq`, or `ollama` |
| `model` | no | empty | Reference model override |
| `top-k` | no | `5` | Reference retrieval depth, 1-20 |
| `judge` | no | `mock` | `mock` or `llm` |
| `judge-provider` | no | `groq` | `groq` or `ollama` for LLM judging |
| `judge-model` | no | empty | Judge model override |
| `repeats` | no | `1` | Judge samples per query/metric, 1-5 |
| `warmup` | no | `0` | Discarded warm-up requests per run |
| `baseline` | no | empty | Completed run ID stored on the candidate |
| `min-context-recall` | no | empty | Strict lower bound, expected 0-1 |
| `min-faithfulness` | no | empty | Strict lower bound, expected 0-1 |
| `min-answer-relevance` | no | empty | Strict lower bound, expected 0-1 |
| `max-hallucination-rate` | no | empty | Strict upper bound, expected 0-1 |
| `max-p95-latency-ms` | no | empty | Strict upper bound in milliseconds |
| `timeout` | no | `1800` | Maximum seconds to wait for a terminal run |
| `poll-interval` | no | `2` | Polling interval in seconds |
| `comment` | no | `true` | Upsert a PR comment on `pull_request` events |
| `github-token` | no | `github.token` in the step | Token used for the comment |
| `python-version` | no | `3.11` | Python used for the CLI |
| `artifact-name` | no | `evalforge-results` | Artifact name for JSON, markdown, and log |

Thresholds are strict. The v1 CLI has no tolerance, confidence interval, or minimum-coverage
threshold. A partial run always fails even if the configured metric means pass. If no thresholds
are supplied, the gate only verifies that the run completed without failed target queries.

## Outputs

| Output | Meaning |
| --- | --- |
| `run-id` | EvalForge run UUID |
| `status` | Terminal status reported by the API |
| `exit-code` | `0` pass, `1` gate failure, `2` API/CLI failure |

The exit code is also used by the final gate step. The evaluation step uses
`continue-on-error: true` so the report and comment are still produced before the gate fails the
job.

## Artifacts

The action uploads:

```text
evalforge-comment.md   PR-ready markdown
evalforge-run.json     final run summary
evalforge-run.log      CLI progress and errors
```

Artifacts are retained for 14 days and are uploaded even when the gate fails. The same markdown is
written to the job summary.

## Comment behavior

On a `pull_request` event with comments enabled, the action finds a comment containing
`<!-- evalforge-evaluation -->` and updates it, or creates one if absent. It does not create a new
comment on every push.

The workflow needs:

```yaml
permissions:
  contents: read
  pull-requests: write
```

PRs from forks may receive a read-only token under the default GitHub security model. In that case
the comment step can fail while the evaluation and gate still have meaningful results. Do not
grant broad write permissions to untrusted workflows.

## Security notes

- Use a secret for `api-token`; never commit it or echo it in logs.
- The action sends questions, answers, and contexts to the configured EvalForge API and judge.
- The target URL and API URL must be reachable by the runner. EvalForge does not currently block
  private/loopback target URLs, so do not let untrusted users choose arbitrary URLs.
- The CLI and action code are taken from the action's pinned repository ref. Pin to a SHA for
  supply-chain safety.
- The action expects the API to enforce its own write token. An unprotected API can spend provider
  credits and create runs.

## Troubleshooting

- **401 from the API:** set `api-token` to the API's `EVALFORGE_WRITE_API_TOKEN`.
- **CLI cannot find dataset:** call `actions/checkout` first and pass a workspace-relative path.
- **Run stuck queued:** the API worker is not running, or the API is scaled to multiple processes.
- **LLM judge initialization fails:** configure `EVALFORGE_GROQ_API_KEY` on the API, or use Ollama
  and a reachable model.
- **No PR comment:** verify the event is `pull_request` and grant `pull-requests: write`. Check the
  workflow log for the comment step.
- **Gate fails with `unavailable`:** the run did not reach a usable result, or a requested metric
  had no successful judgments. Inspect the uploaded log and JSON evidence.
