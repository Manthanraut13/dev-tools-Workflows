from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from dailydevfinds.models import Candidate


class BaseCollector(ABC):
    """Base class for all collectors."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    @abstractmethod
    async def collect(self) -> list[Candidate]:
        """Collect candidates from the source."""
        ...

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET request with retry logic."""
        response = await self.client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST request with retry logic."""
        response = await self.client.post(url, **kwargs)
        response.raise_for_status()
        return response

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "BaseCollector":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
