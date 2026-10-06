-- Company registry. Replaces config/companies.yml as the source of truth
-- for which boards to poll, and carries manual notes that would otherwise
-- be re-derived every time a role from that employer appears.
--
-- Sponsorship is recorded by hand rather than resolved against DOL filing
-- data: automating the match across ~27k employer names costs far more
-- than it saves at this volume, and a boolean loses the context that
-- actually matters ("filed 40, none since 2024" vs "filed 3, all PhD").

CREATE TABLE IF NOT EXISTS companies (
    source              TEXT NOT NULL,
    board_token         TEXT NOT NULL,

    display_name        TEXT,
    careers_url         TEXT,

    -- Manual, filled in once per company as it comes up.
    sponsorship_status  TEXT,     -- sponsors | no | unknown | unclear
    sponsorship_note    TEXT,     -- free text: the context behind the status
    checked_at          TIMESTAMPTZ,

    -- Operational state.
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    inactive_reason     TEXT,     -- e.g. moved to Workday, no openings
    last_ingest_at      TIMESTAMPTZ,
    last_ingest_status  TEXT,     -- ok | http_404 | error
    last_job_count      INTEGER,

    added_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (source, board_token)
);

CREATE INDEX IF NOT EXISTS idx_companies_active
    ON companies (is_active) WHERE is_active;
