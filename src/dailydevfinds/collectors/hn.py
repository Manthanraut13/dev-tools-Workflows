from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import tenacity

from dailydevfinds.collectors.base import BaseCollector
from dailydevfinds.models import Candidate, Source


class HackerNewsCollector(BaseCollector):  # type: ignore[misc]
    """Collects candidates from Hacker News via Algolia API."""

    BASE_URL = "https://hn.algolia.com/api/v1/search"
    MIN_SCORE = 50
    MAX_AGE_DAYS = 7

    def __init__(self, min_score: int = MIN_SCORE, max_age_days: int = MAX_AGE_DAYS, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.min_score = min_score
        self.max_age_days = max_age_days

    async def collect(self) -> list[Candidate]:
        """Fetch top stories from HN Algolia API."""
        cutoff_date = datetime.now(UTC) - timedelta(days=self.max_age_days)
        cutoff_timestamp = int(cutoff_date.timestamp())

        params: dict[str, Any] = {
            "tags": "story",
            "numericFilters": f"points>={self.min_score},created_at_i>={cutoff_timestamp}",
            "hitsPerPage": 50,
        }

        try:
            response = await self._get(self.BASE_URL, params=params)
            data = response.json()
            hits: list[dict[str, Any]] = data.get("hits", [])

            candidates: list[Candidate] = []
            for hit in hits:
                if not hit.get("url"):
                    continue

                candidate = self._hit_to_candidate(hit)
                if candidate:
                    candidates.append(candidate)

            return candidates
        except (httpx.HTTPError, tenacity.RetryError):
            return []

    def _hit_to_candidate(self, hit: dict[str, Any]) -> Candidate | None:
        """Convert Algolia hit to Candidate."""
        try:
            title = hit.get("title", "").strip()
            if not title:
                return None

            url = hit.get("url", "").strip()
            if not url:
                return None

            return Candidate(
                id=f"hn:{hit.get('objectID', '')}",
                title=title[:200],
                url=url,
                source=Source.HACKERNEWS,
                source_score=float(hit.get("points", 0)),
                description=self._clean_text(hit.get("story_text", ""))[:500] if hit.get("story_text") else None,
                author=hit.get("author"),
                created_at=datetime.fromtimestamp(hit.get("created_at_i", 0), tz=UTC) if hit.get("created_at_i") else None,
                tags=["hackernews", "story"],
            )
        except Exception:
            return None

    def _clean_text(self, text: str) -> str:
        """Clean HTML entities and whitespace from text."""
        import html
        return html.unescape(text).replace("\n", " ").strip()


async def collect_hackernews(min_score: int = 50, max_age_days: int = 7) -> list[Candidate]:
    """Convenience function for collecting from HN."""
    async with HackerNewsCollector(min_score=min_score, max_age_days=max_age_days) as collector:
        return await collector.collect()  # type: ignore[no-any-return]
