"""
Application tracker.

    python -m src.track apply <canonical_id> [--explore] [--note "..."]
    python -m src.track status <canonical_id> <new_status> [--note "..."]
    python -m src.track list [status]
    python -m src.track funnel
    python -m src.track ghost [days]

Outcome data is the fuel for Phase 6 and accumulates only in wall-clock
time, so logging has to be cheap enough to actually do. Everything here is
one short command.
"""

import sys
from datetime import datetime, timezone

from sqlalchemy import text

from src.db import engine

# Ordered progression. rejected and ghosted are terminal from anywhere.
PIPELINE = ["applied", "screen", "interview", "offer"]
TERMINAL = ["rejected", "ghosted", "withdrawn"]
VALID = PIPELINE + TERMINAL

# A role with no response after this long is treated as ghosted. Silence is
# the most common outcome and it has to become a recorded label, not an
# application that sits in "applied" forever.
GHOST_AFTER_DAYS = 30


def _record(conn, canonical_id: str, from_status: str | None,
            to_status: str, source: str, note: str | None) -> None:
    conn.execute(
        text("""
            INSERT INTO outcomes (canonical_id, from_status, to_status, source, note)
            VALUES (:cid, :frm, :to, :src, :note)
        """),
        {"cid": canonical_id, "frm": from_status, "to": to_status,
         "src": source, "note": note},
    )


def apply_to(canonical_id: str, explore: bool = False, note: str | None = None) -> None:
    with engine.begin() as conn:
        job = conn.execute(
            text("""
                SELECT title, company_name, fit_score, scoring_model
                  FROM jobs WHERE canonical_id = :cid
            """),
            {"cid": canonical_id},
        ).fetchone()

        if job is None:
            print(f"no such job: {canonical_id}")
            return

        existing = conn.execute(
            text("SELECT status FROM applications WHERE canonical_id = :cid"),
            {"cid": canonical_id},
        ).fetchone()

        if existing:
            print(f"already logged — status '{existing.status}'")
            return

        # fit_score is copied, not joined. Re-scoring or a profile edit
        # changes the job's current score, but the score that predicted
        # this outcome is the one at the moment of applying.
        conn.execute(
            text("""
                INSERT INTO applications (
                    canonical_id, fit_score_at_apply, scoring_model,
                    is_exploration, notes
                ) VALUES (:cid, :score, :model, :explore, :note)
            """),
            {"cid": canonical_id, "score": job.fit_score,
             "model": job.scoring_model, "explore": explore, "note": note},
        )
        _record(conn, canonical_id, None, "applied", "manual", note)

    tag = "  [exploration]" if explore else ""
    score = f"{job.fit_score:.2f}" if job.fit_score is not None else "n/a"
    print(f"logged  {job.company_name} — {job.title}  (fit {score}){tag}")


def set_status(canonical_id: str, new_status: str,
               note: str | None = None, source: str = "manual") -> None:
    if new_status not in VALID:
        print(f"invalid status. one of: {', '.join(VALID)}")
        return

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT status FROM applications WHERE canonical_id = :cid"),
            {"cid": canonical_id},
        ).fetchone()

        if row is None:
            print(f"not tracked: {canonical_id}")
            return

        if row.status == new_status:
            print(f"already '{new_status}'")
            return

        conn.execute(
            text("""
                UPDATE applications
                   SET status = :status, last_change_at = now()
                 WHERE canonical_id = :cid
            """),
            {"status": new_status, "cid": canonical_id},
        )
        _record(conn, canonical_id, row.status, new_status, source, note)

    print(f"{row.status} -> {new_status}")


def ghost(days: int = GHOST_AFTER_DAYS) -> None:
    """Silence is an outcome. Make it an explicit label rather than a gap."""
    with engine.begin() as conn:
        stale = conn.execute(
            text("""
                SELECT canonical_id FROM applications
                 WHERE status = 'applied'
                   AND last_change_at < now() - make_interval(days => :days)
            """),
            {"days": days},
        ).fetchall()

        for row in stale:
            conn.execute(
                text("""
                    UPDATE applications
                       SET status = 'ghosted', last_change_at = now()
                     WHERE canonical_id = :cid
                """),
                {"cid": row.canonical_id},
            )
            _record(conn, row.canonical_id, "applied", "ghosted",
                    "inferred", f"no response after {days} days")

    print(f"{len(stale)} marked ghosted")


def list_applications(status: str | None = None) -> None:
    query = """
        SELECT a.status, a.applied_at::date AS applied,
               a.fit_score_at_apply AS fit, a.is_exploration,
               j.company_name, j.title
          FROM applications a JOIN jobs j USING (canonical_id)
    """
    params = {}
    if status:
        query += " WHERE a.status = :status"
        params["status"] = status
    query += " ORDER BY a.applied_at DESC"

    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    if not rows:
        print("nothing tracked yet")
        return

    for r in rows:
        fit = f"{r.fit:.2f}" if r.fit is not None else " n/a"
        flag = " *" if r.is_exploration else "  "
        print(f"{r.applied}  {r.status:10} {fit}{flag} {r.company_name[:16]:18} {r.title[:48]}")

    print(f"\n{len(rows)} applications  (* = exploration)")


def funnel() -> None:
    """
    Denominators stated explicitly. Rates are over applications submitted,
    never over pipeline size — that is the most common way these numbers
    get inflated.
    """
    with engine.begin() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM applications")
        ).scalar()

        if not total:
            print("no applications logged yet")
            return

        reached = conn.execute(
            text("""
                SELECT to_status, count(DISTINCT canonical_id) AS n
                  FROM outcomes
                 WHERE to_status IN ('screen', 'interview', 'offer')
                 GROUP BY 1
            """)
        ).fetchall()

        current = conn.execute(
            text("SELECT status, count(*) AS n FROM applications GROUP BY 1")
        ).fetchall()

    counts = {r.to_status: r.n for r in reached}

    print(f"\napplications submitted   {total}")
    print("-" * 42)
    for stage in ("screen", "interview", "offer"):
        n = counts.get(stage, 0)
        print(f"reached {stage:12} {n:5}   {n/total:6.1%} of submitted")

    print("\ncurrent status")
    print("-" * 42)
    for r in sorted(current, key=lambda r: r.n, reverse=True):
        print(f"  {r.status:12} {r.n:5}")
    print()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    cmd, rest = args[0], args[1:]

    note = None
    if "--note" in rest:
        i = rest.index("--note")
        note = rest[i + 1] if len(rest) > i + 1 else None
        rest = rest[:i] + rest[i + 2:]

    explore = "--explore" in rest
    rest = [a for a in rest if a != "--explore"]

    if cmd == "apply" and rest:
        apply_to(rest[0], explore=explore, note=note)
    elif cmd == "status" and len(rest) >= 2:
        set_status(rest[0], rest[1], note=note)
    elif cmd == "list":
        list_applications(rest[0] if rest else None)
    elif cmd == "funnel":
        funnel()
    elif cmd == "ghost":
        ghost(int(rest[0]) if rest else GHOST_AFTER_DAYS)
    else:
        print(__doc__)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
