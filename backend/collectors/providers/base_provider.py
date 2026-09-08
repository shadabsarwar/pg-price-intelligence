from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    source_url: str | None
    fetched_at: datetime
    body: bytes = field(repr=False)
    content_type: str = "text/html"


class BaseProvider(ABC):
    @abstractmethod
    def fetch_result(self, url: str) -> FetchResult:
        """Fetch an explicitly permitted public source, or raise a safe error."""
        raise NotImplementedError
