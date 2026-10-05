from datetime import datetime, timezone
import requests

from src.models import JobPosting
from src.adapters import SourceAdapter

BASE = "https://api.ashbyhq.com/posting-api/job-board"
HEADERS = {"User-Agent": "careerops/0.1 (personal project)"}


def _parse_dt(value: str | None) -> datetime | None:
    """Ashby sends ISO-8601 with offset, e.g. 2026-04-07T17:12:35.753+00:00."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _flatten_location(job: dict) -> str:
    """
    Ashby gives a primary location plus structured secondaryLocations.
    Flatten to one string for parity with the other sources; the
    structured addresses survive in JobPosting.raw.
    """
    parts = []
    primary = job.get("location")
    if primary:
        parts.append(primary)
    for secondary in job.get("secondaryLocations") or []:
        label = secondary.get("location")
        if label and label not in parts:
            parts.append(label)
    return ", ".join(parts)


def _compensation(job: dict) -> str | None:
    comp = job.get("compensation") or {}
    return (
        comp.get("scrapeableCompensationSalarySummary")
        or comp.get("compensationTierSummary")
        or None
    )


class AshbyAdapter(SourceAdapter):
    name = "ashby"

    def fetch(self, board_token: str) -> list[JobPosting]:
        url = f"{BASE}/{board_token}"
        response = requests.get(
            url,
            params={"includeCompensation": "true"},
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()

        seen_at = datetime.now(timezone.utc)
        postings = []

        for job in response.json().get("jobs", []):
            # Ashby marks some roles unlisted; they are not meant for
            # public boards, so we do not ingest them.
            if job.get("isListed") is False:
                continue

            source_job_id = str(job["id"])
            postings.append(
                JobPosting(
                    source=self.name,
                    board_token=board_token,
                    source_job_id=source_job_id,
                    canonical_id=f"{self.name}:{board_token}:{source_job_id}",
                    company_name=job.get("companyName") or board_token,
                    title=job["title"],
                    location_raw=_flatten_location(job),
                    apply_url=job.get("jobUrl") or job.get("applyUrl", ""),
                    posted_at=_parse_dt(job.get("publishedAt")),
                    updated_at=None,  # Ashby's public feed has no update field
                    first_seen_at=seen_at,
                    compensation_raw=_compensation(job),
                    job_family_id=None,
                    raw=job,
                )
            )

        return postings
