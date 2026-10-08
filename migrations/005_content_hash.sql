-- Fingerprint of employer-editable fields. Lets ingest skip the write
-- for unchanged postings — without it every run rewrote all ~9k rows
-- including full descriptions, taking 32 minutes.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;
