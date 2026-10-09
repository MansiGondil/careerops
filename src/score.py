"""
Fit scoring: cosine similarity between a posting and each profile section.

The score is max-over-sections rather than an average. A job that matches
your skills strongly but your stated preferences weakly is still a good
match; averaging would penalise it for a mismatch that does not matter.
Per-section scores are kept so the explanation can say which part matched.
"""

import json

from sqlalchemy import text

from src.db import engine
from src.embeddings import MODEL_NAME, embed
from src.profile import load_sections

STORE_SCORE = text(
    """
    UPDATE jobs
       SET fit_score = :score,
           fit_breakdown = CAST(:breakdown AS jsonb),
           scored_at = now(),
           scoring_model = :model
     WHERE canonical_id = :cid
    """
)

SELECT_EMBEDDED = text(
    """
    SELECT canonical_id, embedding
      FROM jobs
     WHERE closed_at IS NULL
       AND is_eligible
       AND embedding IS NOT NULL
    """
)


def _cosine(a: list[float], b: list[float]) -> float:
    """Both vectors are normalized at embed time, so this is a dot product."""
    return sum(x * y for x, y in zip(a, b))


def _parse_vector(raw) -> list[float]:
    """pgvector comes back as a string like '[0.1,0.2,...]' through pg8000."""
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)


def run() -> None:
    sections = load_sections()
    names = list(sections)
    section_vectors = dict(zip(names, embed([sections[n] for n in names])))
    print(f"profile sections: {', '.join(names)}")

    with engine.begin() as conn:
        rows = conn.execute(SELECT_EMBEDDED).fetchall()

    print(f"scoring {len(rows)} postings")

    payload = []
    for row in rows:
        job_vec = _parse_vector(row.embedding)
        breakdown = {
            name: round(_cosine(job_vec, vec), 4)
            for name, vec in section_vectors.items()
        }
        payload.append(
            {
                "cid": row.canonical_id,
                "score": round(max(breakdown.values()), 4),
                "breakdown": json.dumps(breakdown),
                "model": MODEL_NAME,
            }
        )

    with engine.begin() as conn:
        conn.execute(STORE_SCORE, payload)

    print("done")


if __name__ == "__main__":
    run()