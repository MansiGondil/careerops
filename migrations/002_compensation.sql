-- Some sources (Ashby) publish a salary range on the public feed.
-- Stored as the source's own summary string; parsing is deferred.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS compensation_raw TEXT;
