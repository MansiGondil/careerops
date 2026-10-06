# CareerOps — Project Charter

**Owner:** Mansi Gondil
**Started:** September 2026
**Type:** Portfolio project — multi-agent systems, MCP, MLOps
**Status:** Phase 1 complete; Phase 2 next

---

## 1. Problem Statement

Job search is manual, reactive, and slow in exactly the places where speed and consistency matter most.

Three specific failures:

**Discovery is late and lexically blind.** Postings attract most of their applicants within the first 48 hours, so late discovery costs most of a candidate's edge. Worse, keyword search over job *titles* misses emerging role categories that don't map to established titles — Forward Deployed Engineer, AI Solutions Engineer, Applied AI Engineer — precisely the roles where competition is thinnest and the opportunity is largest.

**Tailoring is high-effort and doesn't scale.** Each application needs a resume and cover letter shaped to a specific job description, passing both automated ATS parsing and human screening. Done properly this takes 30–60 minutes per role, which caps throughput at a handful of quality applications per week. Done with a generic LLM, it invents experience the candidate cannot defend in an interview.

**There is no feedback loop.** Applications go out, most produce silence, and nothing about that outcome data is captured or used. The candidate cannot answer which sources, role types, or messaging actually convert — so the same low-yield behaviour repeats indefinitely.

### What this project builds

An end-to-end, continuously running system that:

1. **Discovers** relevant openings across ATS providers within hours of posting, matching semantically over job descriptions rather than lexically over titles, and hard-filtering on eligibility (visa sponsorship, location, seniority)
2. **Screens employers** against public government data — sponsorship history, debarment status, standing — so effort is never spent on roles that were never viable
3. **Scores and ranks** each posting for fit, with a per-requirement explanation that surfaces honest gaps alongside matches, rather than an opaque number
4. **Tailors** a resume and cover letter from a verified evidence bank, optimised for ATS parsing and human readability, with no fabricated experience
5. **Identifies recruiters** and drafts short cold outreach for high-fit roles
6. **Tracks** every application through its funnel stages, ingesting status changes automatically from email
7. **Learns** from accumulated outcomes — the fit model retrains on real results and must pass an automated evaluation gate before replacing the incumbent

### Why the learning loop is the point

Several published projects cover items 1–6. Almost none cover item 7. A static scorer — embedding similarity plus a skill taxonomy — never improves, and its rankings are never validated against whether high-scored roles actually convert.

Treating the fit model as a production ML asset with training, versioning, CI-gated promotion, and drift monitoring is what makes this an MLOps project rather than an automation script. It is also the harder engineering problem, and the one worth talking about in an interview.

---

## 2. Scope

### In scope
- Greenhouse, Lever, Ashby public job board APIs (free, keyless, no scraping), behind a single normalised adapter interface so a fourth provider is one new class
- Public government employer data: sponsorship filings, debarment list, employer standing
- Local-first deployment; runs on a laptop
- Human approval gate before anything is sent
- Evidence-grounded generation only
- Full MLOps lifecycle around the fit-scoring model

### Explicitly out of scope
- Auto-submitting applications (deliberate — accuracy and ToS risk outweigh the time saved)
- Bulk cold email (reputation risk; outreach stays low-volume and reviewed)
- LinkedIn/Indeed scraping (ToS violation; ATS APIs are the legitimate route)
- Multi-user / SaaS deployment
- Paid contact-enrichment APIs (Phase 5 accepts a manual lookup step)
- Automated employer screening against DOL filing data. Resolving ~27k government employer records against ATS board tokens costs roughly a day of entity-resolution work to save ~15 minutes a month at this application volume, and a boolean verdict discards the context that actually matters — "filed 40, none since 2024" and "filed 3, all PhD research roles" classify identically and mean very different things. Sponsorship is checked by hand once per company and cached in the `companies` table.

### Non-negotiable constraints
| Constraint | Reason |
|---|---|
| No fabricated experience in any generated artifact | Interview credibility; this is the core trust guarantee |
| Human reviews every outbound artifact | Safety, and the quality bar is subjective |
| Resume/PII never sent to free-tier hosted LLMs | Free tiers may train on inputs; tailoring runs locally on Ollama |
| Idempotent processing | Never re-apply or double-contact |
| Every artifact carries model + prompt version | Provenance is miserable to retrofit |
| Fit output shows gaps, not just matches | Tells you what to learn; keeps you truthful in interviews |

---

## 3. Success Criteria

Metrics are defined tightly on purpose — loosely defined funnel numbers are the most common way these projects oversell themselves.

### System metrics
| Metric | Definition | Target |
|---|---|---|
| Discovery latency | Median hours from `posted_at` to `first_seen_at` | < 12h |
| Dedup precision | Distinct roles / total ingested rows | > 0.95 |
| Coverage | Tracked companies with a working ATS feed | > 150 |
| Sponsorship check coverage | Companies with eligible roles that carry a recorded sponsorship note | 100% |
| Pipeline uptime | Scheduled runs completing without manual intervention | > 95% |
| Cost per posting processed | Total spend / postings scored | $0.00 |

### Outcome metrics
Denominators stated explicitly. "Response rate" means replies divided by **applications submitted**, not by pipeline size.

| Metric | Definition |
|---|---|
| Response rate | (screens + rejections with a human reply) / applications submitted |
| Screen rate | screens / applications submitted |
| Interview rate | interviews / applications submitted |
| Time per application | Median minutes of human effort, end to end |

### Model metric — the one that matters
**Score–outcome correlation:** do postings in the top score quartile convert to responses at a materially higher rate than the bottom quartile? If not, the model adds nothing and the honest move is to report that.

### Project-level definition of done
- System runs unattended on a daily schedule
- Time per quality application drops below 10 minutes of human effort
- At least 50 logged outcomes, enough to train and evaluate a first model
- Public repo with README, architecture diagram, and an honest results write-up

---

## 4. Architecture Summary

```
ORCHESTRATION (LangGraph)
  discover -> score -> tailor -> outreach -> [HUMAN APPROVAL GATE] -> send -> track
                                  |
MCP SERVER LAYER  <---------------+
  jobs | profile/evidence | scoring | docs | contacts | tracker
                                  |
DATA + ML  <----------------------+
  Postgres + pgvector | model registry | artifact store
                                  |
MLOPS  <--------------------------+
  training | CI-gated eval | drift monitoring | scheduling | tracing
```

### Agents
| Agent | Responsibility | Guardrail |
|---|---|---|
| Discovery | Poll ATS feeds, normalise, dedup, eligibility filter | Canonical job ID |
| Scoring | Fit score + per-requirement match explanation | Must emit rationale |
| Tailoring | Resume bullet selection, cover letter draft | Evidence bank only |
| Outreach | Recruiter identification, 2-line message | No double-contact, rate limited |
| Tracker | State transitions, email ingestion, auto-ghosting | Idempotent writes |
| Orchestrator | Sequencing, daily budget, approval routing | Cost + volume ceiling |

### MCP server boundaries
Agents never import a vendor SDK. They call tools.

- `jobs-server` — `search(query, since)`, `fetch(job_id)`
- `profile-server` — `get_evidence(tags)`, `get_resume_base()`
- `scoring-server` — `score(job_id)` — hides whether the scorer is a heuristic or a trained model
- `docs-server` — `render_resume(selection)`, `render_cover_letter()`
- `contacts-server` — `find_recruiters(company, role)`
- `tracker-server` — `upsert_application()`, `transition()`, `get_funnel()`

The `scoring-server` boundary is what lets Phase 2's heuristic be swapped for Phase 6's trained model without touching agent code.

### Data model
`jobs` · `evidence` · `applications` (carries `model_version`, `prompt_version`) · `outreach` · `outcomes`

### Stack
Python · LangGraph · MCP Python SDK · Postgres + pgvector · Ollama (local LLM) · sentence-transformers · scikit-learn · MLflow · Prefect · GitHub Actions · Streamlit · Langfuse · Docker Compose

All components free and self-hosted. Total running cost: $0.

---

## 5. Execution Plan

Assumes roughly 8–10 hours per week alongside coursework, TA duties, and the co-op. Each phase ends in something that runs.

### Phase 1 — Discovery skeleton (Weeks 1–2)
Get real job data into a real database. Nothing intelligent yet.

- Postgres + pgvector via Docker Compose
- `jobs` table and schema
- Greenhouse public API ingestion for ~20 target companies, written behind a `SourceAdapter` interface from the first line — every provider yields an identical normalised record
- Canonical job ID and dedup logic
- Eligibility hard filters: location, seniority, apply-window open
- **Company registry** (`companies` table) as the source of truth for active boards, carrying per-board ingest status and a manually recorded sponsorship note per employer, cached so the lookup is never repeated
- Daily scheduled run

**Exit criteria:** `SELECT count(*) FROM jobs` returns a few hundred deduplicated, filtered, current postings, refreshed daily without intervention. Adding a second ATS provider requires no changes outside a new adapter class.

**Status — met.** Three providers (Greenhouse, Lever, Ashby), 15 boards, 3,076 postings ingested, 209 eligible. Scheduled daily via Windows Task Scheduler and verified running unattended in ~49s.

**Risk:** low. Public APIs, no auth. The main surprises were in filtering, not ingestion: substring matching silently dropped every "Account Executive" on `iv`, an include-only function filter let "AI Sales" through on the AI keyword, and Canadian province codes (`NS`, `ON`, `BC`) collide with US state codes. All three were invisible until the drop list was read by hand.

**Note on the adapter interface:** this is the highest-leverage decision in the project and it must be made before the first ingestion script, not after. Retrofitting normalisation across three providers is far more work than designing for it once.

---

### Phase 2 — Scoring v0 and the tracker (Weeks 3–4)
Deliberately ahead of tailoring. Outcome data is the fuel for everything in Phase 6, and it only accumulates in wall-clock time — so start collecting immediately.

- Extend ingestion to Lever and Ashby
- Embedding-based fit score (sentence-transformers, local, no training)
- Requirement extraction from JD, matched against profile → explanation, not just a score
- **Honest-gaps output:** every fit result lists matched requirements *and* unmet ones explicitly. Gaps are a first-class output, not a hidden penalty term — they drive what to learn next and keep interview claims defensible.
- `applications` and `outcomes` tables with `model_version` / `prompt_version` columns
- Email ingestion to auto-populate status transitions
- Auto-ghosting after N days of silence
- Streamlit board: ranked queue, funnel view, kanban

**Exit criteria:** daily ranked shortlist with visible reasoning; applications tracked with minimal manual logging.

**Risk:** email parsing is messy. Mitigation — start with rule-based matching on known ATS sender domains, expand later.

---

### Phase 3 — Evidence bank and tailoring (Weeks 5–7)
The trust-critical phase.

- Structure career history into tagged, verified evidence units (bullets, projects, metrics)
- Expose via `profile-server` MCP server
- Retrieval over evidence given a JD
- Tailoring agent using Ollama locally — **selects and rephrases evidence, never generates new claims**
- Automated check: flag any generated claim not traceable to an evidence unit
- ATS-safe rendering: single column, no tables, no text boxes, no graphics
- Cover letter generation
- Artifact versioning tied to job ID

**Exit criteria:** tailored resume + cover letter in under 5 minutes, every claim traceable to source evidence, parses cleanly in an ATS checker.

**Risk:** highest in the project. Hallucinated experience is a credibility failure, not a bug. The traceability check is the mitigation and should be built before the generation is trusted.

---

### Phase 4 — Multi-agent orchestration (Weeks 8–9)
Turn a set of scripts into a system.

- LangGraph state machine wiring the agents
- Orchestrator with daily application budget and cost ceiling
- Human approval gate
- Langfuse tracing: per-run latency, token spend, failure rate
- Retry, backoff, source-health alerting

**Exit criteria:** one scheduled command runs the full pipeline end to end and queues artifacts for review.

**Where the effort goes:** MCP tool signatures, not prompt text. Agents given vague, broadly scoped tools flail; agents given sharp, narrowly scoped, well-described tools work. Budget review time for tool design and expect to iterate on it after watching agents fail.

---

### Phase 5 — Outreach (Week 10)
Deliberately small, deliberately semi-manual.

- Recruiter/hiring-manager identification per role
- Two-line cold message drafted from role + evidence
- Contact registry preventing duplicate contact
- Follow-up cadence tracking
- Manual LinkedIn lookup step — keeps the project free and keeps a human on the highest-judgment step

**Exit criteria:** outreach drafted and logged, no duplicates, rate limited.

---

### Phase 6 — MLOps layer (Weeks 11–14)
Only reachable once Phase 2 has been running long enough to accumulate outcomes. This is the differentiating work.

- Feature pipeline from `outcomes`: embedding features + explicit requirement-match features
- Train fit model (scikit-learn; logistic regression or gradient boosting — interpretability over raw accuracy)
- MLflow registry with versioned metrics
- **CI gate:** GitHub Actions runs held-out evaluation on PR; a new version must beat the incumbent to be promotable
- Swap `scoring-server` from heuristic to model — no agent code changes
- **Exploration policy:** reserve 10–15% of applications for lower-scored roles, to keep collecting counterfactual signal instead of training the model on its own past choices
- Monitoring: score distribution drift, response rate by score bucket, source health, profile drift
- Retraining trigger on new outcome volume

**Exit criteria:** a model version promoted through the CI gate, with monitoring showing whether score actually predicts response.

**Risk:** label scarcity is real. With ~50 outcomes, the honest framing is "a working MLOps pipeline demonstrated on a small, growing dataset," not "a high-accuracy model." State that plainly in the write-up — a well-engineered pipeline on thin data is credible; overstated accuracy is not.

---

### Phase 7 — Publish (Week 15)
- README with architecture diagram and design rationale
- Honest results write-up: real funnel numbers, explicit denominators, what did not work
- Public repo

---

## 6. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Fabricated experience in generated artifacts | Critical — interview credibility | Evidence bank + automated traceability check before generation is trusted |
| Insufficient labels for the model | High — Phase 6 has no fuel | Start outcome collection in Phase 2; frame honestly as small-n |
| Selection bias in the feedback loop | Medium — model reinforces its own choices | Exploration policy, 10–15% below-threshold applications |
| Scope creep into a SaaS product | High — project never ships | Non-goals list above is binding |
| Project displaces actual applying | Critical — defeats the purpose | System must be usable from Phase 2; if it isn't helping by week 4, apply manually and rescope |
| ATS API changes or deprecation | Medium | Source-health alerting; multiple providers |
| Time pressure from coursework / co-op | High | Phases are independently shippable; stopping after Phase 4 still yields a coherent project |
| Benchmarking against senior-candidate results | Medium — false sense of failure | Published funnel numbers from 20-year-experience candidates are not a new-grad baseline. Measure against your own trend, not someone else's post. |
| Prior art becoming public | Medium — reduces novelty | Comparable systems exist and are being open-sourced. Differentiation is the outcome-trained model and CI gate, not the pipeline itself. Read their ingestion code rather than rediscovering it. |
| Over-filtering hides good roles | High — silent, and the shortlist still looks plausible | Filter verdicts stored with reasons; drop list reviewed by hand after every rule change. Three real bugs were found this way. |

---

## 7. What Makes This Defensible in an Interview

The honest positioning, in one line:

> A continuously running multi-agent pipeline that discovers, scores, and tailors job applications, where the scoring model retrains on real application outcomes and must pass an automated evaluation gate before it reaches production.

### Known prior art
Comparable systems exist — ATS ingestion, RAG over career history, an MCP server, a funnel dashboard — and at least one is being open-sourced. Assume the pipeline itself is not novel and do not build the pitch around it.

What those systems do **not** have, and where the differentiation actually lives:

1. A closed feedback loop from application outcome back into the ranking model
2. CI-gated model promotion, with versioned provenance on every generated artifact
3. An explicit treatment of selection bias in a self-reinforcing recommendation system
4. A designed multi-agent system with an orchestrator, rather than a single agent pointed at a set of tools

Worth borrowing from prior art rather than reinventing: the source-adapter pattern, honest-gap reporting, and email-mined tracking. Reference implementations save weeks.

And the thing that makes any of it credible: **real numbers from real use, with honest denominators.**
