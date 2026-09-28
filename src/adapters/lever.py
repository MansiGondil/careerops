from datetime import datetime, timezone
import requests

from src.models import JobPosting
from src.adapters import SourceAdapter

BASE = "https://api.lever.co/v0/postings"
HEADERS = {"User-Agent": "careerops/0.1 (personal project)"}


def _parse_epoch_ms(value: int | None) -> datetime | None:
    """Lever sends epoch milliseconds, e.g. 1782214185805."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _flatten_location(posting: dict) -> str:
    """
    Lever gives structured locations; Greenhouse gives free text.
    Flatten to a single string so one normalizer handles both sources.
    The structured form survives in JobPosting.raw if ever needed.
    """
    categories = posting.get("categories") or {}
    all_locations = categories.get("allLocations")
    if all_locations:
        return ", ".join(all_locations)
    return categories.get("location") or ""


class LeverAdapter(SourceAdapter):
    name = "lever"

    def fetch(self, board_token: str) -> list[JobPosting]:
        url = f"{BASE}/{board_token}"
        response = requests.get(
            url, params={"mode": "json"}, headers=HEADERS, timeout=30
        )
        response.raise_for_status()

        seen_at = datetime.now(timezone.utc)
        postings = []

        for post in response.json():
            source_job_id = str(post["id"])
            postings.append(
                JobPosting(
                    source=self.name,
                    board_token=board_token,
                    source_job_id=source_job_id,
                    canonical_id=f"{self.name}:{board_token}:{source_job_id}",
                    company_name=board_token,
                    title=post["text"],
                    location_raw=_flatten_location(post),
                    apply_url=post.get("hostedUrl") or post.get("applyUrl", ""),
                    posted_at=_parse_epoch_ms(post.get("createdAt")),
                    updated_at=None,  # Lever's public feed has no update field
                    first_seen_at=seen_at,
                    job_family_id=None,
                    raw=post,
                )
            )

        return postings
