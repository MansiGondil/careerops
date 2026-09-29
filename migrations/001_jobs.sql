-- Jobs discovered from ATS source adapters.
-- One row per posting, keyed on canonical_id = {source}:{board_token}:{source_job_id}.

CREATE TABLE IF NOT EXISTS jobs (
    canonical_id    TEXT PRIMARY KEY,

    -- Identity
    source          TEXT NOT NULL,
    board_token     TEXT NOT NULL,
    source_job_id   TEXT NOT NULL,

    -- Content
    company_name    TEXT NOT NULL,
    title           TEXT NOT NULL,
    location_raw    TEXT NOT NULL DEFAULT '',
    apply_url       TEXT NOT NULL,
    description     TEXT,

    -- Timing
    posted_at       TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ,

    -- Grouping hint from the source; NOT an identity or dedup key.
    -- Greenhouse's internal_job_id backs several distinct postings
    -- across different teams, so it groups job families only.
    job_family_id   TEXT,

    -- Full original payload, kept so new fields can be extracted
    -- without re-fetching every board.
    raw             JSONB
);

-- Ingest reads by source+board to reconcile what is still live.
CREATE INDEX IF NOT EXISTS idx_jobs_source_board
    ON jobs (source, board_token);

-- Discovery-latency queries and freshness filters sort on posting age.
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at
    ON jobs (posted_at DESC NULLS LAST);

-- Open roles are the common read path; closed_at IS NULL is the filter.
CREATE INDEX IF NOT EXISTS idx_jobs_open
    ON jobs (closed_at)
    WHERE closed_at IS NULL;
