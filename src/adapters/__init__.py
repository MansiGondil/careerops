from abc import ABC, abstractmethod
from src.models import JobPosting


class SourceAdapter(ABC):
    """Contract for every job source. Adding a source = one new subclass."""

    name: str

    @abstractmethod
    def fetch(self, board_token: str) -> list[JobPosting]:
        """Fetch all open postings for one company board."""
        ...
