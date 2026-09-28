from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.lever import LeverAdapter

for adapter, token in [(GreenhouseAdapter(), "stripe"), (LeverAdapter(), "spotify")]:
    jobs = adapter.fetch(token)
    print(f"\n=== {adapter.name}:{token} — {len(jobs)} postings ===")
    for j in jobs[:2]:
        print(f"  {j.canonical_id}")
        print(f"    {j.title}")
        print(f"    {j.location_raw}")
        print(f"    posted {j.posted_at}")
