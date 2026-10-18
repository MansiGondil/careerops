"""
Read ATS status emails and transition tracked applications.

Rule-based on sender domain and subject. An LLM would be more flexible
and far less predictable; a wrong status transition silently corrupts the
outcome data that Phase 6 trains on, so this stays deterministic and
explicit about what it could not classify.
"""

import base64
import re
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from src.db import engine
from src.gmail import get_service
from src.track import set_status

# Subject patterns, checked in order. First match wins, so terminal and
# high-signal states come before generic acknowledgements.
PATTERNS = [
    ("rejected", [
        r"\bunfortunately\b",
        r"not (moving|move) forward",
        r"not (be )?proceed",
        r"decided to (move forward with other|pursue other)",
        r"\bregret\b",
        r"other candidates",
        r"we will not be",
    ]),
    ("interview", [
        r"\binterview\b",
        r"onsite",
        r"final round",
        r"technical (round|screen)",
    ]),
    ("screen", [
        r"schedule (a |an )?(call|chat|conversation)",
        r"recruiter (call|screen|chat)",
        r"next steps",
        r"phone screen",
        r"\bavailability\b",
        r"online assessment",
        r"coding (challenge|assessment)",
        r"take[- ]home",
    ]),
]

# Applied-acknowledgement subjects. Matched but deliberately ignored:
# the application is already logged, and re-recording it would inflate
# the event log with non-events.
ACK = [
    r"thank you for applying",
    r"thank you for your application",
    r"application (has been )?received",
    r"we received your application",
    r"thanks for applying",
]


def _classify(subject: str, snippet: str) -> str | None:
    blob = f"{subject} {snippet}".lower()

    for status, patterns in PATTERNS:
        if any(re.search(p, blob) for p in patterns):
            return status

    if any(re.search(p, blob) for p in ACK):
        return None  # already known

    return "unclassified"


def _company_from(sender: str) -> str:
    """Extract the domain stem: 'no-reply@hire.lever.co' -> 'lever'."""
    match = re.search(r"@([\w.-]+)", sender)
    if not match:
        return ""
    parts = match.group(1).lower().split(".")
    skip = {"com", "co", "io", "ai", "net", "org", "us", "hire", "mail",
            "email", "notifications", "my", "jobs", "careers", "greenhouse",
            "lever", "ashbyhq", "myworkday"}
    for part in reversed(parts):
        if part not in skip:
            return part
    return parts[0]


def _header(message: dict, name: str) -> str:
    for h in message["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def run(days: int = 14) -> None:
    service = get_service()

    with engine.begin() as conn:
        tracked = conn.execute(text("""
            SELECT a.canonical_id, a.status, j.company_name, j.board_token
              FROM applications a JOIN jobs j USING (canonical_id)
             WHERE a.status NOT IN ('rejected', 'ghosted', 'withdrawn', 'offer')
        """)).fetchall()

    if not tracked:
        print("no open applications to match against")
        return

    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
    result = service.users().messages().list(
        userId="me", q=f"after:{after}", maxResults=200
    ).execute()

    messages = result.get("messages", [])
    print(f"scanning {len(messages)} messages from the last {days} days")

    matched = unmatched = 0

    for ref in messages:
        msg = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject"],
        ).execute()

        sender = _header(msg, "From")
        subject = _header(msg, "Subject")
        snippet = msg.get("snippet", "")

        status = _classify(subject, snippet)
        if status is None:
            continue

        stem = _company_from(sender)
        if not stem:
            continue

        # Match the sender domain against tracked companies. Deliberately
        # loose: ATS senders use varied domains, and a missed match is
        # recoverable while a wrong one corrupts the outcome log.
        candidates = [
            t for t in tracked
            if stem in t.board_token.lower()
            or stem in t.company_name.lower().replace(" ", "")
        ]

        if not candidates:
            continue

        if status == "unclassified":
            unmatched += 1
            print(f"  ?  {candidates[0].company_name}: {subject[:60]}")
            continue

        for t in candidates:
            if t.status != status:
                print(f"  -> {t.company_name}: {t.status} -> {status}")
                set_status(t.canonical_id, status,
                           note=subject[:200], source="email")
                matched += 1

    print(f"\n{matched} transitions, {unmatched} unclassified")


if __name__ == "__main__":
    sys.exit(run(int(sys.argv[1]) if len(sys.argv) > 1 else 14))