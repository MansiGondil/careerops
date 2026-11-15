import sys

from sqlalchemy import text

from src.db import engine

ALLOWED = ("sponsors", "no", "unclear")

if len(sys.argv) == 1:
    # No arguments: list the companies that matter most and have no status yet.
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT c.board_token, c.display_name, count(*) AS open_jobs
              FROM companies c
              JOIN jobs j ON j.source = c.source AND j.board_token = c.board_token
             WHERE c.sponsorship_status IS NULL
               AND j.is_eligible AND j.closed_at IS NULL
             GROUP BY 1, 2
             ORDER BY 3 DESC
             LIMIT 15
        """)).fetchall()
    for r in rows:
        print(f"{r.board_token:24} {str(r.display_name)[:28]:28} {r.open_jobs} open jobs")
    sys.exit()

token, status = sys.argv[1], sys.argv[2]
note = sys.argv[3] if len(sys.argv) > 3 else None
if status not in ALLOWED:
    sys.exit(f"status must be one of {ALLOWED}")

with engine.begin() as c:
    n = c.execute(text("""
        UPDATE companies
           SET sponsorship_status = :s, sponsorship_note = :n, checked_at = now()
         WHERE board_token = :t
    """), {"s": status, "n": note, "t": token}).rowcount
print(f"updated {n} company row(s) for {token}")