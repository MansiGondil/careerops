from datetime import datetime, timezone
import requests

from src.models import JobPosting
from src.adapters import SourceAdapter

BASE = "https://boards-api.greenhouse.io/v1/boards"
HEADERS = {"User-Agent": "job-search-platform/0.1 (personal project)"}


def _parse_dt(value: str | None) -> datetime | None:
    """Greenhouse sends ISO-8601 with offset, e.g. 2026-09-09T10:50:29-04:00."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"

    def fetch(self, board_token: str) -> list[JobPosting]:
        url = f"{BASE}/{board_token}/jobs"
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        seen_at = datetime.now(timezone.utc)
        postings = []

        for job in response.json()["jobs"]:
            source_job_id = str(job["id"])
            postings.append(
                JobPosting(
                    source=self.name,
                    board_token=board_token,
                    source_job_id=source_job_id,
                    canonical_id=f"{self.name}:{board_token}:{source_job_id}",
                    company_name=job.get("company_name") or board_token,
                    title=job["title"],
                    location_raw=(job.get("location") or {}).get("name", ""),
                    apply_url=job["absolute_url"],
                    posted_at=_parse_dt(job.get("first_published")),
                    updated_at=_parse_dt(job.get("updated_at")),
                    first_seen_at=seen_at,
                    job_family_id=str(job["internal_job_id"]) if job.get("internal_job_id") else None,
                    raw=job,
                )
            )

        return postings
