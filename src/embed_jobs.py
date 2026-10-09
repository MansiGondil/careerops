"""
Generate embeddings for eligible postings.

Only eligible roles are embedded: ineligible ones are never scored, and
embedding all ~9,000 would cost roughly ten times the time for no benefit.
Rows already embedded with the current model are skipped, so this is safe
to re-run and cheap in steady state.
"""

import sys

from sqlalchemy import text

from src.db import engine
from src.embeddings import MODEL_NAME, embed

BATCH = 100

SELECT_PENDING = text(
    """
    SELECT canonical_id, title, company_name, description
      FROM jobs
     WHERE closed_at IS NULL
       AND is_eligible
       AND description IS NOT NULL
       AND (embedding IS NULL OR embedding_model IS DISTINCT FROM :model)
    """
)

STORE_VECTOR = text(
    """
    UPDATE jobs
       SET embedding = CAST(:vec AS vector),
           embedding_model = :model,
           embedded_at = now()
     WHERE canonical_id = :cid
    """
)


def run() -> None:
    with engine.begin() as conn:
        rows = conn.execute(SELECT_PENDING, {"model": MODEL_NAME}).fetchall()

    if not rows:
        print("nothing to embed")
        return

    print(f"embedding {len(rows)} postings")

    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]

        # Title and company are prepended because descriptions often open
        # with company boilerplate, and the model only reads the first few
        # hundred word pieces. The title is the single most informative
        # line about what the role actually is, so it must not be buried.
        texts = [
            f"{r.title}\n{r.company_name}\n\n{r.description}" for r in chunk
        ]
        vectors = embed(texts)

        payload = [
            {"cid": r.canonical_id, "vec": str(v), "model": MODEL_NAME}
            for r, v in zip(chunk, vectors)
        ]

        with engine.begin() as conn:
            conn.execute(STORE_VECTOR, payload)

        print(f"  {min(start + BATCH, len(rows))}/{len(rows)}")

    print("done")


if __name__ == "__main__":
    sys.exit(run())
