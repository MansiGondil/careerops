import sys
import time
from pathlib import Path

import requests
import yaml

from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.lever import LeverAdapter
from src.adapters.ashby import AshbyAdapter
from src.db import upsert_postings, close_missing

ADAPTERS = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
}

CONFIG = Path(__file__).resolve().parent.parent / "config" / "companies.yml"

# Public APIs, but still someone else's server. Stay polite.
REQUEST_DELAY_SECONDS = 0.5


def load_boards() -> list[tuple[str, str]]:
    data = yaml.safe_load(CONFIG.read_text())
    return [
        (source, token)
        for source, tokens in data.items()
        for token in (tokens or [])
    ]


def run() -> int:
    boards = load_boards()
    print(f"Ingesting {len(boards)} boards\n")

    total_upserted = total_closed = failures = 0

    for source, board_token in boards:
        adapter = ADAPTERS.get(source)
        if adapter is None:
            print(f"  SKIP  {source}:{board_token} — no adapter for '{source}'")
            failures += 1
            continue

        try:
            postings = adapter.fetch(board_token)
        except requests.HTTPError as exc:
            # A dead board must not kill the whole run. 404 usually means
            # the company moved to a different ATS or changed its token.
            status = exc.response.status_code if exc.response else "?"
            print(f"  FAIL  {source}:{board_token} — HTTP {status}")
            failures += 1
            continue
        except requests.RequestException as exc:
            print(f"  FAIL  {source}:{board_token} — {type(exc).__name__}")
            failures += 1
            continue

        written = upsert_postings(postings)
        closed = close_missing(
            source, board_token, [p.canonical_id for p in postings]
        )
        total_upserted += written
        total_closed += closed

        print(f"  ok    {source}:{board_token:14} {written:5} upserted, {closed:4} closed")
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\n{total_upserted} upserted, {total_closed} closed, {failures} failed")
    return 1 if failures == len(boards) else 0


if __name__ == "__main__":
    sys.exit(run())
