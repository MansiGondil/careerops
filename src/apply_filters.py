"""
Recompute eligibility for every open posting.

Separate from ingest so filter rules can be re-applied without re-fetching
boards — the config will change far more often than the data.
"""
from sqlalchemy import text

from src.db import engine
from src.filters import evaluate


def run() -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT canonical_id, title, location_raw, description
              FROM jobs WHERE closed_at IS NULL
        """)).fetchall()

        updates = [
            {
                "canonical_id": r.canonical_id,
                "is_eligible": eligible,
                "filter_reasons": "; ".join(reasons),
            }
            for r in rows
            for eligible, reasons in [evaluate(r.title, r.location_raw, r.description)]
        ]

        conn.execute(
            text("""
                UPDATE jobs
                   SET is_eligible = :is_eligible,
                       filter_reasons = :filter_reasons
                 WHERE canonical_id = :canonical_id
            """),
            updates,
        )

    eligible = sum(u["is_eligible"] for u in updates)
    print(f"{len(updates)} evaluated, {eligible} eligible")


if __name__ == "__main__":
    run()
