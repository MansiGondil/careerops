"""
Read ATS email and keep the tracker current.

Two jobs:
  1. Transition tracked applications when a status email arrives
  2. Create rows for applications made outside the pipeline, which would
     otherwise be invisible and make every funnel number wrong

Extraction is layered, strongest signal first:

  job link  -> an ATS posting URL carries the id, which maps onto a jobs
               row exactly, linking the application to a scored posting
               rather than an external stub
  subject   -> "thank you for applying to <Company>" names the employer
               even when the sender is an ATS relay (greenhouse-mail,
               ashbyhq, myworkday)
  body role -> "your application for the <Role> position"
  fallback  -> company only, title null

Classification is rule-based, not LLM-driven: a wrong transition silently
corrupts the outcome data Phase 6 trains on, and silent corruption is
worse than a missed email.

Two-pass over Gmail. Metadata-only listing is cheap; full bodies cost
~25x more quota and blew the per-minute limit on a 175-message scan. Only
messages whose subject already looks like ATS mail get fetched in full.
"""

import base64
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError
from sqlalchemy import text

from src.db import engine
from src.gmail import get_service
from src.track import external, set_status

# ---------------------------------------------------------------- patterns

STATUS_PATTERNS = [
    ("rejected", [
        r"\bunfortunately\b",
        r"not (moving|move) forward",
        r"not (be )?proceed",
        r"decided to (move forward with other|pursue other)",
        r"(selected|chosen|moving forward with|proceeding with) other candidates",
        r"will not be moving",
        r"regret to inform",
        r"no longer under consideration",
        r"(decided|chosen) to (progress|proceed) with other",
        r"not (be )?progressing",
    ]),
    ("interview", [
        r"\binterview\b",
        r"\bonsite\b",
        r"final round",
        r"technical (round|screen)",
        r"hiring manager (call|chat)",
    ]),
    ("screen", [
        r"schedule (a |an )?(call|chat|conversation|time)",
        r"recruiter (call|screen|chat)",
        r"phone screen",
        r"online assessment",
        r"coding (challenge|assessment)",
        r"take[- ]home",
        r"\bnext steps\b",
    ]),
]

ACK_PATTERNS = [
    r"thank(s| you) for applying",
    r"thank you for your application",
    r"thank you for your interest",
    r"application (has been )?received",
    r"we received your application",
]

NOISE_PATTERNS = [
    r"career fair",
    r"\d+% match",
]

# Cheap subject-only test deciding whether a full body fetch is worth the
# quota. Deliberately broad: a false positive costs one fetch, a false
# negative loses an outcome.
RELEVANT_SUBJECT = re.compile(
    r"appl(y|ying|ication)|interview|recruit|candidat|position|role|"
    r"opportunit|next step|assessment|screen|offer|hiring|thank you for "
    r"your interest|action needed",
    re.IGNORECASE,
)

COMPANY_PATTERNS = [
    r"^((?-i:[A-Z])[\w&.' -]{1,40}?) application:",    
    r"appl(?:ying|ication) to ((?-i:[A-Z])[\w&.' -]{1,40}?)(?:,? Inc\.?|,? LLC)?[!?.]?\s*$",
    r"appl(?:ying|ication) to ((?-i:[A-Z])[\w&.' -]{1,40}?)(?:,|!|\?|\.|$)",
    r"your application (?:to|with) ((?-i:[A-Z])[\w&.' -]{1,40}?)(?:,|!|\?|\.|$)",
    r"interest in ((?-i:[A-Z])[\w&.' -]{1,40}?)(?:,|!|\?|\.|$)",
]

ROLE_PATTERNS = [
    r"application for the ((?-i:[A-Z])[^<>{}]{3,90}?\(ID: ?\d+\)) position",
    r"position of ((?-i:[A-Z])[^<>{}]{3,90}?\(ID: ?\d+\))",    
    r"application for (?:the )?([A-Z][^.\n<>{}]{3,60}?) (?:role|position|opening|req)",
    r"applied (?:to|for) (?:the )?([A-Z][^.\n<>{}]{3,60}?) (?:role|position|opening)",
    r"your interest in (?:the )?([A-Z][^.\n<>{}]{3,60}?) (?:role|position|opening)",
    r"(?:^|\s)(?:role|position)\s*:\s*([A-Za-z][^\n<>{}]{3,60})",
]

JOB_LINK_PATTERNS = [
    (r"boards\.greenhouse\.io/[\w-]+/jobs/(\d+)", "greenhouse"),
    (r"job-boards\.greenhouse\.io/[\w-]+/jobs/(\d+)", "greenhouse"),
    (r"gh_jid=(\d+)", "greenhouse"),
    (r"jobs\.lever\.co/[\w-]+/([\w-]{8,})", "lever"),
    (r"jobs\.ashbyhq\.com/[\w-]+/([\w-]{8,})", "ashby"),
]

# Text that is never a company or a role. CSS and layout fragments leak
# out of HTML mail and matched the role patterns on an earlier run,
# producing rows named "relative; font-size: 15px; border-radius: 3px".
JUNK = re.compile(
    r"font|px\b|margin|padding|border|color|align|width|height|style|"
    r"background|decoration|display|href|http|\{|\}|;|track of your",
    re.IGNORECASE,
)
TITLE_WORDS = re.compile(
    r"\b(engineer|developer|analyst|scientist|manager|intern|architect|"
    r"specialist|consultant|administrator)\b",
    re.IGNORECASE,
)


# ------------------------------------------------------------------ helpers

def _header(message: dict, name: str) -> str:
    for h in message["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _body_text(payload: dict) -> str:
    """
    Flatten the MIME tree to plain text.

    <style> and <script> blocks are removed before tags are stripped:
    stripping tags alone leaves the CSS rules themselves in the text,
    which then match role and company patterns.
    """
    chunks: list[str] = []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
            if mime == "text/html":
                raw = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", raw)
                raw = re.sub(r"<[^>]+>", " ", raw)
                raw = html.unescape(raw)
            chunks.append(raw)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip(" .,:;-!?\"'")
    if not (2 <= len(value) <= 100):
        return None
    if JUNK.search(value):
        return None
    if not re.search(r"[A-Za-z]{2}", value):
        return None
    return value


def _extract(patterns: list[str], *texts: str, reject=None) -> str | None:
    for blob in texts:
        if not blob:
            continue
        for pattern in patterns:
            match = re.search(pattern, blob, re.IGNORECASE)
            if match:
                cleaned = _clean(match.group(1))
                if cleaned and not (reject and reject.search(cleaned)):
                    return cleaned
    return None

def _find_job_link(body: str) -> tuple[str, str] | None:
    for pattern, source in JOB_LINK_PATTERNS:
        match = re.search(pattern, body)
        if match:
            return source, match.group(1)
    return None


def _classify(blob: str) -> str | None:
    """
    Acknowledgements are checked FIRST.

    "Thank you for applying... we'll reach out to discuss next steps" is
    an acknowledgement, but it contains 'next steps', which is a screen
    pattern. Checking status first marked a plain OpenAI acknowledgement
    as an interview — a wrong label is worse than a missed one, because
    it silently corrupts the outcome data.
    """
    low = blob.lower()
    if any(re.search(p, low) for p in NOISE_PATTERNS):
        return "unknown"
    if any(re.search(p, low) for p in ACK_PATTERNS):
        # A rejection can also say "thank you for applying", so only a
        # rejection signal overrides an acknowledgement.
        for pattern in dict(STATUS_PATTERNS)["rejected"]:
            if re.search(pattern, low):
                return "rejected"
        return None

    for status, patterns in STATUS_PATTERNS:
        if any(re.search(p, low) for p in patterns):
            return status

    return "unknown"


def _fetch(service, message_id: str, attempt: int = 0):
    """Full message with backoff; Gmail rate-limits per minute per user."""
    try:
        return service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    except HttpError as exc:
        if exc.resp.status in (403, 429) and attempt < 4:
            wait = 2 ** attempt * 5
            print(f"     rate limited, waiting {wait}s")
            time.sleep(wait)
            return _fetch(service, message_id, attempt + 1)
        raise


# -------------------------------------------------------------- resolution

def _role_key(role: str) -> str:
    """The (ID: n) tag when present, since titles alone collide.
    Without an ID, fall back to the first 20 characters."""
    match = re.search(r"\(ID: ?\d+\)", role)
    return match.group(0) if match else role[:20]

def _resolve(conn, link, company, role):
    """
    Map an email onto an existing application, strongest signal first.

    Company alone resolves only when exactly one open application matches.
    Guessing between several roles at one employer risks closing a live
    application, which is far worse than missing a transition.
    """
    if link:
        source, job_id = link
        row = conn.execute(
            text("""
                SELECT a.canonical_id FROM applications a
                  JOIN jobs j USING (canonical_id)
                 WHERE j.source = :source AND j.source_job_id = :jid
            """),
            {"source": source, "jid": job_id},
        ).fetchone()
        if row:
            return row.canonical_id, "link"

    stem = company.split(",")[0].strip() if company else None

    if stem and role:
        row = conn.execute(
            text("""
                SELECT canonical_id FROM applications
                 WHERE lower(company_name) LIKE lower(:company)
                   AND lower(coalesce(title, '')) LIKE lower(:role)
                 LIMIT 1
            """),
            {"company": f"%{stem}%", "role": f"%{_role_key(role)}%"},
        ).fetchone()
        if row:
            return row.canonical_id, "company+role"

    if stem and not role:
        rows = conn.execute(
            text("""
                SELECT canonical_id FROM applications
                 WHERE lower(company_name) LIKE lower(:company)
                   AND status NOT IN ('rejected', 'ghosted', 'withdrawn')
            """),
            {"company": f"%{stem}%"},
        ).fetchall()
        if len(rows) == 1:
            return rows[0].canonical_id, "company"
        if len(rows) > 1:
            return None, "ambiguous"

    return None, None


def _already_created(conn, company: str, role: str | None) -> bool:
    """Guard against re-creating an external row on every run."""
    stem = company.split(",")[0].strip()

    if role:
        row = conn.execute(
            text("""
                SELECT 1 FROM applications
                 WHERE lower(company_name) LIKE lower(:company)
                   AND lower(coalesce(title, '')) LIKE lower(:role_like)
                 LIMIT 1
            """),
            {"company": f"%{stem}%", "role_like": f"%{_role_key(role)}%"},
        ).fetchone()
    else:
        row = conn.execute(
            text("""
                SELECT 1 FROM applications
                 WHERE lower(company_name) LIKE lower(:company)
                 LIMIT 1
            """),
            {"company": f"%{stem}%"},
        ).fetchone()

    return row is not None


# ------------------------------------------------------------------- driver

def _ensure_processed_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                message_id   text PRIMARY KEY,
                processed_at timestamptz NOT NULL DEFAULT now(),
                outcome      text
            )
        """))


def _processed_ids() -> set[str]:
    with engine.connect() as conn:
        return {r.message_id for r in conn.execute(
            text("SELECT message_id FROM processed_emails"))}


def _mark(message_id: str, outcome: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO processed_emails (message_id, outcome)
                    VALUES (:m, :o) ON CONFLICT DO NOTHING"""),
            {"m": message_id, "o": outcome},
        )

def run(days: int = 30, create_missing: bool = True, limit: int = 300) -> None:
    service = get_service() 
    _ensure_processed_table()

    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
    listed = service.users().messages().list(
        userId="me", q=f"after:{after}", maxResults=limit
    ).execute()
    refs = listed.get("messages", [])

    done = _processed_ids()
    fresh = [r for r in refs if r["id"] not in done]
    print(f"listing {len(refs)} messages from the last {days} days, "
          f"{len(fresh)} not seen before")

    # Pass one: metadata only, and only for messages not yet handled.
    candidates = []
    for ref in fresh:
        meta = service.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        subject = _header(meta, "Subject")
        if RELEVANT_SUBJECT.search(subject):
            candidates.append((ref["id"], subject))
        else:
            _mark(ref["id"], "irrelevant")

    candidates.reverse()
    print(f"{len(candidates)} look like ATS mail; reading oldest first\n")   

    transitions = created = known = ambiguous = unmatched = 0

    for message_id, subject in candidates:
        msg = _fetch(service, message_id)
        body = _body_text(msg["payload"])
        blob = f"{subject} {body[:3000]}"

        status = _classify(blob)
        if status == "unknown":
            continue

        company = _extract(COMPANY_PATTERNS, subject, body[:1200], reject=TITLE_WORDS)
        role = _extract(ROLE_PATTERNS, subject, body[:2500])
        link = _find_job_link(body)

        if not company and not link:
            continue

        with engine.begin() as conn:
            canonical_id, how = _resolve(conn, link, company, role)

        if how == "ambiguous":
            ambiguous += 1
            print(f"  !  {company}: several open applications — {subject[:50]}")
            continue

        if canonical_id:
            if status is None:
                known += 1
                _mark(message_id, "known")
                continue
            set_status(canonical_id, status, note=subject[:200], source="email")
            print(f"  {status:9} {company or canonical_id}  [{how}]")
            transitions += 1
            _mark(message_id, "transition")
            continue

        if status is None and create_missing and company:
            with engine.begin() as conn:
                if _already_created(conn, company, role):
                    known += 1
                    _mark(message_id, "known")
                    continue
            external(company, role or "(role not stated)",
                     note=f"auto-created from: {subject[:150]}")
            created += 1
            _mark(message_id, "created")
            continue

        unmatched += 1
        print(f"  ?  {company or '?'}: {subject[:55]}")

    print(f"\n{transitions} transitions, {created} created, {known} already known, "
          f"{ambiguous} ambiguous, {unmatched} unmatched")


if __name__ == "__main__":
    sys.exit(run(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
