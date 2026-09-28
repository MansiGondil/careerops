# CareerOps

Operational discipline applied to job search.

A continuously running multi-agent pipeline that discovers, screens, scores, and tailors job applications — where the fit-ranking model retrains on real application outcomes and must pass an automated evaluation gate before it reaches production.

## Why

Most job-search tooling is a one-shot assistant: paste a job description, get a tailored resume back. Nothing measures whether the output worked, and nothing improves as a result.

CareerOps treats the fit model as a production ML asset — versioned, evaluated, monitored, and retrained on observed outcomes — and treats the surrounding pipeline as infrastructure rather than a script.

## Status

**Phase 1 of 7** — discovery skeleton. See [`docs/charter.md`](docs/charter.md) for the full plan.

| Phase | Scope | State |
|---|---|---|
| 1 | Discovery skeleton — ATS ingestion, dedup, employer screening | In progress |
| 2 | Scoring v0 and outcome tracking | Not started |
| 3 | Evidence bank and tailoring | Not started |
| 4 | Multi-agent orchestration | Not started |
| 5 | Outreach | Not started |
| 6 | MLOps layer — training, CI gate, monitoring | Not started |
| 7 | Publish | Not started |

## Architecture

    ORCHESTRATION (LangGraph)
      discover -> screen -> score -> tailor -> outreach -> [APPROVAL] -> track
                                      |
    MCP TOOL LAYER  <-----------------+
      jobs | profile | scoring | docs | contacts | tracker
                                      |
    DATA + ML  <----------------------+
      Postgres + pgvector | model registry | artifact store
                                      |
    MLOPS  <--------------------------+
      training | CI-gated eval | drift monitoring | tracing

## Design notes

**Source adapters.** Every job source normalizes to one `JobPosting` shape. Adding a provider is one new class implementing `SourceAdapter`; nothing downstream changes.

**Canonical ID.** `{source}:{board_token}:{source_job_id}`. Greenhouse's `internal_job_id` groups job *families* — one requisition can back several distinct postings on different teams — so it is stored as a hint, never as identity. This was tested against a 705-posting board before the schema was fixed.

**Defensive parsing.** Real boards contain broken records: null locations, postings whose location field literally reads `LOCATION`, unparseable dates. None of these may fail an ingest.

**Location is free text.** `Seattle, San Francisco, New York City`, `Remote from the US`, `SF, NYC, SEA, CHI` all appear on one board. Raw values are preserved and normalization is a separate, re-runnable stage.

**Evidence-grounded generation.** Tailoring selects and rephrases verified career evidence. It never generates new claims.

## Layout

    src/
      models.py           JobPosting — the normalized record
      adapters/
        __init__.py       SourceAdapter contract
        greenhouse.py     Greenhouse public board API
    docs/
      charter.md          Problem statement, scope, metrics, phase plan
    data/                 Local data (gitignored)
    profile/              Resume and evidence bank (gitignored)
    artifacts/            Generated documents (gitignored)

## Running locally

    python -m venv .venv
    source .venv/Scripts/activate    # Windows; use .venv/bin/activate elsewhere
    pip install -r requirements.txt

## Stack

Python · LangGraph · MCP · Postgres + pgvector · Ollama · sentence-transformers · scikit-learn · MLflow · Prefect · GitHub Actions · Streamlit · Langfuse

Runs locally. No paid APIs.

## Data sources

Public, keyless job board APIs published by ATS vendors for exactly this purpose — the same endpoints that fill employers' own careers pages. No scraping, no logins, no proxies. Requests are rate-limited and sent with a descriptive User-Agent.
