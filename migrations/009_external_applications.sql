-- Applications made outside the pipeline.
--
-- The FK to jobs assumed every application came from CareerOps. In practice
-- roles get applied to wherever they are found, and excluding those makes
-- every funnel number wrong — response rate computed over a subset of
-- applications is not a response rate.
--
-- External rows carry no fit_score, so they are excluded from Phase 6
-- training (nothing to learn from) but included in funnel reporting.

ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_canonical_id_fkey;
ALTER TABLE outcomes     DROP CONSTRAINT IF EXISTS outcomes_canonical_id_fkey;

-- Denormalised because there is no jobs row to join to.
ALTER TABLE applications ADD COLUMN IF NOT EXISTS company_name TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS apply_url TEXT;

-- 'careerops' = surfaced and scored by the pipeline
-- 'external'  = found elsewhere; no score, counts for funnel only
ALTER TABLE applications ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'careerops';

CREATE INDEX IF NOT EXISTS idx_applications_origin ON applications (origin);
