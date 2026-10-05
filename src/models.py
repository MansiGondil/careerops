from dataclasses import dataclass
from datetime import datetime


@dataclass
class JobPosting:
    """Normalized job posting. Every source adapter returns this shape."""

    # Identity
    source: str              # "greenhouse" | "lever" | "ashby"
    board_token: str         # company slug on that source
    source_job_id: str       # the source's own posting id
    canonical_id: str        # f"{source}:{board_token}:{source_job_id}"

    # Core content
    company_name: str
    title: str
    location_raw: str        # free text, normalized later
    apply_url: str

    # Timing
    posted_at: datetime | None
    updated_at: datetime | None
    first_seen_at: datetime  # when WE saw it — drives discovery latency

    # Optional
    description: str | None = None
    compensation_raw: str | None = None   # only some sources publish this
    job_family_id: str | None = None   # grouping hint, NOT identity
    raw: dict | None = None            # original payload, kept for debugging
