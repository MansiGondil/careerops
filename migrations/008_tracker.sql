-- Application tracking. Two tables rather than one status column:
-- applications holds current state for querying; outcomes is an
-- append-only event log, which is what Phase 6 trains on. A status
-- column alone loses the timing — "rejected after 3 days" and
-- "rejected after 6 weeks" mean different things.

CREATE TABLE IF NOT EXISTS applications (
    canonical_id    TEXT PRIMARY KEY REFERENCES jobs(canonical_id),

    status          TEXT NOT NULL DEFAULT 'applied',
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_change_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Provenance: which model version ranked this role, and what it
    -- scored. Needed to answer whether high scores actually convert,
    -- and miserable to reconstruct later.
    fit_score_at_apply  REAL,
    scoring_model       TEXT,
    prompt_version      TEXT,

    -- Was this a deliberate below-threshold application? Phase 6's
    -- exploration policy needs these flagged so the model is not
    -- trained purely on its own past choices.
    is_exploration  BOOLEAN NOT NULL DEFAULT FALSE,

    notes           TEXT
);

CREATE TABLE IF NOT EXISTS outcomes (
    id              BIGSERIAL PRIMARY KEY,
    canonical_id    TEXT NOT NULL REFERENCES jobs(canonical_id),

    from_status     TEXT,
    to_status       TEXT NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- How we learned: manual | email | inferred
    source          TEXT NOT NULL DEFAULT 'manual',
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_job
    ON outcomes (canonical_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_applications_status
    ON applications (status);
