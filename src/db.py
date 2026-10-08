import hashlib
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


# Description text lives in its own column. Keeping a second copy inside
# the raw payload doubled write volume once descriptions were captured,
# and raw exists to recover fields we did not anticipate — not to
# duplicate ones we already extract.
RAW_EXCLUDE = {
    "content",
    "description",
    "descriptionPlain",
    "descriptionHtml",
    "descriptionBody",
    "descriptionBodyPlain",
    "lists",
    "additional",
    "additionalPlain",
}


def _slim_raw(raw: dict | None) -> dict | None:
    if not raw:
        return None
    return {k: v for k, v in raw.items() if k not in RAW_EXCLUDE}


def _content_hash(p: JobPosting) -> str:
    """
    Fingerprint of the fields an employer can edit on a live posting.

    Most postings are unchanged between runs, so hashing lets the ingest
    skip the expensive write for them and only touch last_seen_at. Without
    this, every run rewrote all ~9k rows including full descriptions.
    """
    parts = [
        p.title or "",
        p.location_raw or "",
        p.apply_url or "",
        p.description or "",
        p.compensation_raw or "",
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


UPSERT = text("""
INSERT INTO jobs (
    canonical_id, source, board_token, source_job_id,
    company_name, title, location_raw, apply_url, description, compensation_raw,
    posted_at, updated_at, first_seen_at, last_seen_at,
    job_family_id, raw, content_hash
) VALUES (
    :canonical_id, :source, :board_token, :source_job_id,
    :company_name, :title, :location_raw, :apply_url, :description, :compensation_raw,
    :posted_at, :updated_at, :first_seen_at, :first_seen_at,
    :job_family_id, :raw, :content_hash
)
ON CONFLICT (canonical_id) DO UPDATE SET
    title            = EXCLUDED.title,
    location_raw     = EXCLUDED.location_raw,
    apply_url        = EXCLUDED.apply_url,
    description      = COALESCE(EXCLUDED.description, jobs.description),
    compensation_raw = EXCLUDED.compensation_raw,
    updated_at       = EXCLUDED.updated_at,
    raw              = EXCLUDED.raw,
    content_hash     = EXCLUDED.content_hash,

    -- Seen again, so it is live: refresh and un-close.
    last_seen_at     = EXCLUDED.last_seen_at,
    closed_at        = NULL

    -- first_seen_at is deliberately NOT updated. It is our own discovery
    -- timestamp; overwriting it would destroy the discovery-latency metric.
""")


TOUCH_SEEN = text("""
    UPDATE jobs
       SET last_seen_at = :now,
           closed_at = NULL
     WHERE canonical_id IN :ids
""").bindparams(bindparam("ids", expanding=True))


def _existing_hashes(conn, source: str, board_token: str) -> dict[str, str]:
    rows = conn.execute(
        text("""
            SELECT canonical_id, content_hash
              FROM jobs
             WHERE source = :source AND board_token = :board_token
        """),
        {"source": source, "board_token": board_token},
    ).fetchall()
    return {r.canonical_id: r.content_hash for r in rows}


def upsert_postings(postings: list[JobPosting]) -> tuple[int, int]:
    """
    Write postings, skipping rows whose content has not changed.

    Returns (written, unchanged). A steady-state run usually has very few
    writes: employers rarely edit live postings, so most rows only need
    their last_seen_at refreshed, which one bulk statement handles.
    """
    if not postings:
        return 0, 0

    source = postings[0].source
    board_token = postings[0].board_token
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        existing = _existing_hashes(conn, source, board_token)

        changed: list[dict] = []
        unchanged_ids: list[str] = []

        for p in postings:
            digest = _content_hash(p)
            if existing.get(p.canonical_id) == digest:
                unchanged_ids.append(p.canonical_id)
                continue

            changed.append(
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
                    "compensation_raw": p.compensation_raw,
                    "posted_at": p.posted_at,
                    "updated_at": p.updated_at,
                    "first_seen_at": p.first_seen_at,
                    "job_family_id": p.job_family_id,
                    "raw": json.dumps(_slim_raw(p.raw)) if p.raw else None,
                    "content_hash": digest,
                }
            )

        if changed:
            conn.execute(UPSERT, changed)

        # Unchanged rows still need proof of life, in chunks because the
        # IN list is expanded into bind parameters.
        CHUNK = 500
        for i in range(0, len(unchanged_ids), CHUNK):
            conn.execute(
                TOUCH_SEEN,
                {"now": now, "ids": unchanged_ids[i : i + CHUNK]},
            )

    return len(changed), len(unchanged_ids)


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
