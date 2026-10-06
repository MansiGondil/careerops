"""
Probe candidate board tokens before adding them to the registry.

Board tokens are guesses until proven — companies move between ATS
providers and slugs rarely match the company name exactly. This checks
a candidate list against all three providers and reports what is live.

Usage:
    python -m src.check_boards figma airbnb cloudflare
    python -m src.check_boards --file candidates.txt
"""
import sys
import time

import requests

HEADERS = {"User-Agent": "careerops/0.1 (personal project)"}
DELAY = 0.3

PROBES = {
    "greenhouse": lambda t: (
        f"https://boards-api.greenhouse.io/v1/boards/{t}/jobs", {}, "jobs"),
    "lever": lambda t: (
        f"https://api.lever.co/v0/postings/{t}", {"mode": "json"}, None),
    "ashby": lambda t: (
        f"https://api.ashbyhq.com/posting-api/job-board/{t}", {}, "jobs"),
}


def probe(source: str, token: str) -> int | None:
    """Returns job count if the board is live, else None."""
    url, params, key = PROBES[source](token)
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        jobs = data.get(key, []) if key else data
        return len(jobs) if isinstance(jobs, list) else None
    except (requests.RequestException, ValueError):
        return None


def check(token: str) -> None:
    for source in PROBES:
        count = probe(source, token)
        time.sleep(DELAY)
        if count is not None:
            flag = "" if count else "   (board live but empty)"
            print(f"  FOUND  {source:11} {token:22} {count:5} jobs{flag}")
            return
    print(f"  --     {token:22} not found on any provider")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--file":
        tokens = [
            line.strip() for line in open(args[1])
            if line.strip() and not line.startswith("#")
        ]
    else:
        tokens = args

    if not tokens:
        print(__doc__)
        return

    print(f"Probing {len(tokens)} candidates\n")
    for token in tokens:
        check(token)


if __name__ == "__main__":
    main()
