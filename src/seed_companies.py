"""One-time seed of the companies table from config/companies.yml."""
from sqlalchemy import text

from src.db import engine
from src.ingest import load_boards

with engine.begin() as conn:
    conn.execute(
        text("""
            INSERT INTO companies (source, board_token)
            VALUES (:source, :board_token)
            ON CONFLICT (source, board_token) DO NOTHING
        """),
        [{"source": s, "board_token": t} for s, t in load_boards()],
    )
    count = conn.execute(text("SELECT count(*) FROM companies")).scalar()

print(f"{count} companies registered")
