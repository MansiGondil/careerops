from sqlalchemy import text
from src.db import engine
from src.filters import evaluate

with engine.begin() as conn:
    rows = conn.execute(text("""
        SELECT title, location_raw, company_name
          FROM jobs WHERE closed_at IS NULL
    """)).fetchall()

kept = [r for r in rows if evaluate(r.title, r.location_raw)[0]]
dropped = [r for r in rows if not evaluate(r.title, r.location_raw)[0]]

print(f"{len(rows)} open  ->  {len(kept)} eligible ({len(kept)/len(rows):.0%})\n")

print("=== SAMPLE KEPT ===")
for r in kept[:15]:
    print(f"  {r.company_name:14} {r.title[:50]:52} {r.location_raw[:35]}")

print("\n=== SAMPLE DROPPED ===")
for r in dropped[:15]:
    _, reasons = evaluate(r.title, r.location_raw)
    why = next((x for x in reasons if "us signal" not in x and "within band" not in x), "")
    print(f"  {r.title[:48]:50} {why}")
