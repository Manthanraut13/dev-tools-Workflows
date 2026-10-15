from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from dailydevfinds.collectors.base import BaseCollector
from dailydevfinds.models import Candidate, Source


class DevToCollector(BaseCollector):  # type: ignore[misc]
    """Collects candidates from dev.to via public API."""

    BASE_URL = "https://dev.to/api/articles"
    MIN_REACTIONS = 20
    MAX_AGE_DAYS = 14
    PER_PAGE = 30

    def __init__(
        self,
        min_reactions: int = MIN_REACTIONS,
        max_age_days: int = MAX_AGE_DAYS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.min_reactions = min_reactions
        self.max_age_days = max_age_days

    async def collect(self) -> list[Candidate]:
        """Fetch articles from dev.to API."""
        cutoff_date = datetime.now(UTC) - timedelta(days=self.max_age_days)
        all_candidates: list[Candidate] = []

        try:
            params: dict[str, Any] = {
                "per_page": self.PER_PAGE,
                "state": "published",
                "top": 7,
            }

            response = await self._get(self.BASE_URL, params=params)
            articles: list[dict[str, Any]] = response.json()

            for article in articles:
                candidate = self._article_to_candidate(article)
                if candidate and candidate.source_score >= self.min_reactions and candidate.created_at and candidate.created_at >= cutoff_date:
                    all_candidates.append(candidate)

        except httpx.HTTPError:
            pass

        return all_candidates

    def _article_to_candidate(self, article: dict[str, Any]) -> Candidate | None:
        """Convert dev.to article to Candidate."""
        try:
            title = article.get("title", "").strip()
            if not title:
                return None

            url = article.get("url", "").strip()
            if not url:
                return None

            description = article.get("description")
            if description:
                description = description.strip()[:500]

            reactions = article.get("public_reactions_count", 0)
            comments = article.get("comments_count", 0)
            score = float(reactions + comments * 2)

            created_at_str = article.get("published_at")
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else None

            tags_raw = article.get("tag_list", [])
            if isinstance(tags_raw, str):
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            else:
                tags = list(tags_raw) if tags_raw else []
            tags = [f"devto-{t.lower()}" for t in tags]

            return Candidate(
                id=f"devto:{article.get('id', '')}",
                title=title[:200],
                url=url,
                source=Source.DEVTO,
                source_score=score,
                description=description,
                author=article.get("user", {}).get("username"),
                created_at=created_at,
                tags=["devto"] + tags,
            )
        except Exception:
            return None


async def collect_devto(
    min_reactions: int = 20,
    max_age_days: int = 14,
) -> list[Candidate]:
    """Convenience function for collecting from dev.to."""
    async with DevToCollector(min_reactions=min_reactions, max_age_days=max_age_days) as collector:
        return await collector.collect()  # type: ignore[no-any-return]
