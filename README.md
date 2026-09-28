# CareerOps

Operational discipline applied to job search.

A continuously running multi-agent pipeline that discovers, screens, scores, and
tailors job applications — where the fit-ranking model retrains on real
application outcomes and must pass an automated evaluation gate before it
reaches production.

## Why

Most job-search tooling is a one-shot assistant: paste a job description, get a
tailored resume. Nothing measures whether the output worked, and nothing
improves as a result.

CareerOps treats the fit model as a production ML asset — versioned, evaluated,
monitored, and retrained on observed outcomes — and treats the surrounding
pipeline as infrastructure rather than a script.

## Status

Phase 1 of 7 — discovery skeleton. See `docs/charter.md`.

## Architecture

ORCHESTRATION (LangGraph)
discover -> screen -> score -> tailor -> outreach -> [APPROVAL] -> track
|
MCP TOOL LAYER <-----------------+
jobs | profile | scoring | docs | contacts | tracker
|
DATA + ML <----------------------+
Postgres + pgvector | model registry | artifact store
|
MLOPS <--------------------------+
training | CI-gated eval | drift monitoring | tracing


## Design notes

- **Source adapters** — every job source normalizes to one `JobPosting` shape.
  Adding a provider is one new class; nothing downstream changes.
- **Canonical ID** — `{source}:{board_token}:{source_job_id}`. Greenhouse's
  `internal_job_id` groups job *families*, not duplicates, and is stored as a
  hint only.
- **Defensive parsing** — real boards contain broken records. A null location or
  unparseable date must not fail a 700-row ingest.
- **Evidence-grounded generation** — tailoring selects and rephrases verified
  career evidence. It never generates new claims.

## Stack

Python · LangGraph · MCP · Postgres + pgvector · Ollama · scikit-learn ·
MLflow · Prefect · GitHub Actions · Streamlit · Langfuse

Runs locally. No paid APIs.
