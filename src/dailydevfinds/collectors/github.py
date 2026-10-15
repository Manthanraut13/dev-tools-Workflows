import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import tenacity

from dailydevfinds.collectors.base import BaseCollector
from dailydevfinds.models import Candidate, Source


class GitHubCollector(BaseCollector):  # type: ignore[misc]
    """Collects candidates from GitHub via Search REST API."""

    BASE_URL = "https://api.github.com/search/repositories"
    MIN_STARS = 100
    MAX_AGE_DAYS = 30
    DEFAULT_QUERIES = [
        "developer tools",
        "productivity",
        "cli tool",
        "automation",
    ]

    def __init__(
        self,
        token: str | None = None,
        min_stars: int = MIN_STARS,
        max_age_days: int = MAX_AGE_DAYS,
        queries: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.token = token or os.getenv("GH_TOKEN")
        self.min_stars = min_stars
        self.max_age_days = max_age_days
        self.queries = queries or self.DEFAULT_QUERIES

        if self.token:
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        self.client.headers.update({"Accept": "application/vnd.github.v3+json"})

    async def collect(self) -> list[Candidate]:
        """Fetch repositories from GitHub Search API."""
        cutoff_date = (datetime.now(UTC) - timedelta(days=self.max_age_days)).strftime("%Y-%m-%d")
        all_candidates: list[Candidate] = []

        for query in self.queries:
            try:
                params: dict[str, Any] = {
                    "q": f"{query} stars:>={self.min_stars} created:>{cutoff_date}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 30,
                }

                response = await self._get(self.BASE_URL, params=params)
                data = response.json()
                items: list[dict[str, Any]] = data.get("items", [])

                for item in items:
                    candidate = self._item_to_candidate(item, query)
                    if candidate:
                        all_candidates.append(candidate)

            except (httpx.HTTPError, tenacity.RetryError):
                continue

        seen: set[str] = set()
        unique: list[Candidate] = []
        for c in all_candidates:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)

        return unique

    def _item_to_candidate(self, item: dict[str, Any], query: str) -> Candidate | None:
        """Convert GitHub API item to Candidate."""
        try:
            url = item.get("html_url", "")
            if not url:
                return None

            description = item.get("description")
            if description:
                description = description.strip()[:500]

            return Candidate(
                id=f"github:{item.get('id', '')}",
                title=item.get("name", "")[:200],
                url=url,
                source=Source.GITHUB,
                source_score=float(item.get("stargazers_count", 0)),
                description=description,
                github_url=url,
                author=item.get("owner", {}).get("login"),
                created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")) if item.get("created_at") else None,
                tags=["github", "repository", query.replace(" ", "-")],
            )
        except Exception:
            return None


async def collect_github(
    token: str | None = None,
    min_stars: int = 100,
    max_age_days: int = 30,
    queries: list[str] | None = None,
) -> list[Candidate]:
    """Convenience function for collecting from GitHub."""
    async with GitHubCollector(token=token, min_stars=min_stars, max_age_days=max_age_days, queries=queries) as collector:
        return await collector.collect()  # type: ignore[no-any-return]
