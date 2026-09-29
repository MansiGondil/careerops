import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text

from src.models import JobPosting

load_dotenv()

# Driver is pg8000 (pure Python): Windows Smart App Control blocks the
# unsigned libpq DLL that psycopg's binary wheel ships. SQLAlchemy keeps
# the driver swappable — switching back is a connection-string change.
engine = create_engine(os.environ["DATABASE_URL"], future=True)


UPSERT = text("""
INSERT INTO jobs (
    canonical_id, source, board_token, source_job_id,
    company_name, title, location_raw, apply_url, description,
    posted_at, updated_at, first_seen_at, last_seen_at,
    job_family_id, raw
) VALUES (
    :canonical_id, :source, :board_token, :source_job_id,
    :company_name, :title, :location_raw, :apply_url, :description,
    :posted_at, :updated_at, :first_seen_at, :first_seen_at,
    :job_family_id, :raw
)
ON CONFLICT (canonical_id) DO UPDATE SET
    title         = EXCLUDED.title,
    location_raw  = EXCLUDED.location_raw,
    apply_url     = EXCLUDED.apply_url,
    description   = COALESCE(EXCLUDED.description, jobs.description),
    updated_at    = EXCLUDED.updated_at,
    raw           = EXCLUDED.raw,

    -- Seen again, so it is live: refresh and un-close.
    last_seen_at  = EXCLUDED.last_seen_at,
    closed_at     = NULL

    -- first_seen_at is deliberately NOT updated. It is our own discovery
    -- timestamp; overwriting it would destroy the discovery-latency metric.
""")


def upsert_postings(postings: list[JobPosting]) -> int:
    if not postings:
        return 0

    rows = [
        {
            "canonical_id": p.canonical_id,
            "source": p.source,
            "board_token": p.board_token,
            "source_job_id": p.source_job_id,
            "company_name": p.company_name,
            "title": p.title,
            "location_raw": p.location_raw,
            "apply_url": p.apply_url,
            "description": p.description,
            "posted_at": p.posted_at,
            "updated_at": p.updated_at,
            "first_seen_at": p.first_seen_at,
            "job_family_id": p.job_family_id,
            "raw": json.dumps(p.raw) if p.raw else None,
        }
        for p in postings
    ]

    with engine.begin() as conn:
        conn.execute(UPSERT, rows)

    return len(rows)


def close_missing(source: str, board_token: str, live_ids: list[str]) -> int:
    """
    Mark postings closed when they no longer appear in their board's feed.
    A posting that stops being listed has been filled or withdrawn — record
    that rather than letting it silently vanish.
    """
    stmt = text("""
        UPDATE jobs
           SET closed_at = :now
         WHERE source = :source
           AND board_token = :board_token
           AND closed_at IS NULL
           AND canonical_id NOT IN :live_ids
    """).bindparams(bindparam("live_ids", expanding=True))

    with engine.begin() as conn:
        result = conn.execute(
            stmt,
            {
                "now": datetime.now(timezone.utc),
                "source": source,
                "board_token": board_token,
                "live_ids": live_ids or [""],
            },
        )
        return result.rowcount
