from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.lever import LeverAdapter
from src.adapters.ashby import AshbyAdapter
from src.db import upsert_postings, close_missing

# Which companies live on which source. Board tokens do not transfer
# between ATS providers, so the source is part of the config.
BOARDS = [
    (GreenhouseAdapter(), "stripe"),
    (LeverAdapter(), "spotify"),
    (AshbyAdapter(), "ramp"),
]


def run():
    for adapter, board_token in BOARDS:
        postings = adapter.fetch(board_token)
        written = upsert_postings(postings)
        closed = close_missing(
            adapter.name, board_token, [p.canonical_id for p in postings]
        )
        print(f"{adapter.name}:{board_token}  upserted {written}, closed {closed}")


if __name__ == "__main__":
    run()
