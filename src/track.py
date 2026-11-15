"""
Application tracker.

    python -m src.track apply <canonical_id> [--explore] [--note "..."]
    python -m src.track external "<Company>" "<Title>" [--note "..."]
    python -m src.track status <id> <new_status> [--note "..."]
    python -m src.track list [status]
    python -m src.track funnel
    python -m src.track ghost [days]

Applications made outside the pipeline are logged too. Excluding them
would make every funnel number wrong — a response rate computed over a
subset of applications is not a response rate. They carry no fit score,
so they inform reporting but not model training.
"""

import re
import secrets
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from src.db import engine

PIPELINE = ["applied", "screen", "interview", "offer"]
TERMINAL = ["rejected", "ghosted", "withdrawn"]
VALID = PIPELINE + TERMINAL

GHOST_AFTER_DAYS = 30


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _record(conn, canonical_id, from_status, to_status, source, note):
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
                SELECT title, company_name, fit_score, scoring_model, apply_url
                  FROM jobs WHERE canonical_id = :cid
            """),
            {"cid": canonical_id},
        ).fetchone()

        if job is None:
            print(f"no such job: {canonical_id}")
            print("for a role found outside the pipeline, use: track external")
            return

        if conn.execute(
            text("SELECT 1 FROM applications WHERE canonical_id = :cid"),
            {"cid": canonical_id},
        ).fetchone():
            print("already logged")
            return

        conn.execute(
            text("""
                INSERT INTO applications (
                    canonical_id, company_name, title, apply_url,
                    fit_score_at_apply, scoring_model, is_exploration,
                    origin, notes
                ) VALUES (
                    :cid, :company, :title, :url,
                    :score, :model, :explore, 'careerops', :note
                )
            """),
            {"cid": canonical_id, "company": job.company_name, "title": job.title,
             "url": job.apply_url, "score": job.fit_score,
             "model": job.scoring_model, "explore": explore, "note": note},
        )
        _record(conn, canonical_id, None, "applied", "manual", note)

    score = f"{job.fit_score:.2f}" if job.fit_score is not None else "n/a"
    tag = "  [exploration]" if explore else ""
    print(f"logged  {job.company_name} — {job.title}  (fit {score}){tag}")


def external(company: str, title: str, note: str | None = None,
             url: str | None = None, when: str | None = None) -> str:
    """
    Log an application to a role the pipeline never saw.

    No fit score: the role was never ingested or embedded. These rows count
    toward the funnel and are excluded from training, where a missing
    feature would be worse than a missing row.

    The id carries a random suffix because multiple roles at one company on
    one day are normal, and a company+date key collides.
    """
    import secrets

    day = when or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    canonical_id = f"external:{_slug(company)}:{day}:{secrets.token_hex(3)}"

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO applications (
                    canonical_id, company_name, title, apply_url,
                    origin, notes, applied_at
                ) VALUES (
                    :cid, :company, :title, :url, 'external', :note,
                    COALESCE(CAST(:day AS timestamptz), now())
                )
                ON CONFLICT (canonical_id) DO NOTHING
            """),
            {"cid": canonical_id, "company": company, "title": title,
             "url": url, "note": note, "day": day},
        )
        _record(conn, canonical_id, None, "applied", "manual", note)

    print(f"logged  {company} — {title}  [external]")
    return canonical_id


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

    print(f"  {row.status} -> {new_status}")


def ghost(days: int = GHOST_AFTER_DAYS) -> None:
    """Silence is an outcome. Make it a label rather than a gap."""
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
                    UPDATE applications SET status = 'ghosted', last_change_at = now()
                     WHERE canonical_id = :cid
                """),
                {"cid": row.canonical_id},
            )
            _record(conn, row.canonical_id, "applied", "ghosted",
                    "inferred", f"no response after {days} days")

    print(f"{len(stale)} marked ghosted")


def list_applications(status: str | None = None) -> None:
    query = """
        SELECT status, applied_at::date AS applied, fit_score_at_apply AS fit,
               is_exploration, origin, company_name, title
          FROM applications
    """
    params = {}
    if status:
        query += " WHERE status = :status"
        params["status"] = status
    query += " ORDER BY applied_at DESC"

    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    if not rows:
        print("nothing tracked yet")
        return

    for r in rows:
        fit = f"{r.fit:.2f}" if r.fit is not None else "  - "
        flag = "*" if r.is_exploration else " "
        mark = "+" if r.origin == "external" else " "
        company = (r.company_name or "?")[:16]
        title = (r.title or "")[:44]
        print(f"{r.applied}  {r.status:10} {fit}{flag}{mark} {company:18} {title}")

    print(f"\n{len(rows)} applications  (* exploration, + external)")


def funnel() -> None:
    """
    Denominators stated explicitly: rates are over applications submitted,
    never over pipeline size.
    """
    with engine.begin() as conn:
        total = conn.execute(text("SELECT count(*) FROM applications")).scalar()
        if not total:
            print("no applications logged yet")
            return

        by_origin = conn.execute(
            text("SELECT origin, count(*) AS n FROM applications GROUP BY 1")
        ).fetchall()

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
    for r in by_origin:
        print(f"   {r.origin:12} {r.n}")
    print("-" * 44)
    for stage in ("screen", "interview", "offer"):
        n = counts.get(stage, 0)
        print(f"reached {stage:12} {n:5}   {n/total:6.1%} of submitted")

    print("\ncurrent status")
    print("-" * 44)
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
    elif cmd == "external" and len(rest) >= 2:
        external(rest[0], rest[1], note=note)
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
