from src.adapters.greenhouse import GreenhouseAdapter

adapter = GreenhouseAdapter()
jobs = adapter.fetch("stripe")

print(f"{len(jobs)} postings normalized\n")
for j in jobs[:3]:
    print(j.canonical_id)
    print(f"  {j.title}")
    print(f"  {j.location_raw}")
    print(f"  posted {j.posted_at}")
    print()
