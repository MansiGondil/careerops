import requests, json

BOARD = "ramp"
URL = f"https://api.ashbyhq.com/posting-api/job-board/{BOARD}"
HEADERS = {"User-Agent": "careerops/0.1 (personal project)"}

data = requests.get(URL, params={"includeCompensation": "true"},
                    headers=HEADERS, timeout=30).json()

jobs = data["jobs"]
print(f"{len(jobs)} postings at {BOARD}\n")

print("FIELDS:")
for k, v in jobs[0].items():
    print(f"  {k:22} {type(v).__name__}")

first = {k: v for k, v in jobs[0].items()
         if k not in {"descriptionPlain", "descriptionHtml", "description"}}
print("\nFIRST RECORD:")
print(json.dumps(first, indent=2)[:1600])

print("\n--- isListed check ---")
print({j.get("isListed") for j in jobs})
