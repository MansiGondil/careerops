-- Eligibility verdict from config/filters.yml, recomputed on every ingest.
-- Stored rather than computed at read time so the shortlist is queryable
-- and so verdict changes over time are visible.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_eligible BOOLEAN;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS filter_reasons TEXT;

CREATE INDEX IF NOT EXISTS idx_jobs_eligible
    ON jobs (is_eligible)
    WHERE closed_at IS NULL AND is_eligible IS TRUE;
