from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser

from dailydevfinds.collectors.base import BaseCollector
from dailydevfinds.models import Candidate, Source


class RedditCollector(BaseCollector):  # type: ignore[misc]
    """Collects candidates from Reddit via RSS feeds."""

    SUBREDDITS = [
        "programming",
        "productivity",
        "SideProject",
        "selfhosted",
    ]
    MIN_SCORE = 100
    MAX_AGE_DAYS = 7
    RSS_TEMPLATE = "https://www.reddit.com/r/{subreddit}/top/.rss?t=week&limit=50"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        min_score: int = MIN_SCORE,
        max_age_days: int = MAX_AGE_DAYS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.subreddits = subreddits or self.SUBREDDITS
        self.min_score = min_score
        self.max_age_days = max_age_days
        self.client.headers.update({"User-Agent": "DailyDevFinds/0.1"})

    async def collect(self) -> list[Candidate]:
        """Fetch posts from Reddit RSS feeds."""
        cutoff_date = datetime.now(UTC) - timedelta(days=self.max_age_days)
        all_candidates: list[Candidate] = []

        for subreddit in self.subreddits:
            try:
                url = self.RSS_TEMPLATE.format(subreddit=subreddit)
                response = await self._get(url)
                feed = feedparser.parse(response.text)

                for entry in feed.entries:
                    candidate = self._entry_to_candidate(entry, subreddit)
                    if candidate and candidate.source_score >= self.min_score and candidate.created_at and candidate.created_at >= cutoff_date:
                        all_candidates.append(candidate)

            except Exception:
                continue

        return all_candidates

    def _entry_to_candidate(self, entry: Any, subreddit: str) -> Candidate | None:
        """Convert RSS entry to Candidate."""
        try:
            title = getattr(entry, "title", "").strip()
            if not title:
                return None

            url = getattr(entry, "link", "").strip()
            if not url:
                return None

            score, clean_title = self._extract_score_and_title(title, entry)

            description = getattr(entry, "summary", "")
            if description:
                import re
                description = re.sub(r"<[^>]+>", "", description)
                description = description.strip()[:500]

            created_at = None
            published_parsed = getattr(entry, "published_parsed", None)
            if published_parsed:
                created_at = datetime(*published_parsed[:6]).replace(tzinfo=UTC)

            return Candidate(
                id=f"reddit:{subreddit}:{getattr(entry, 'id', '')}",
                title=clean_title[:200],
                url=url,
                source=Source.REDDIT,
                source_score=float(score),
                description=description,
                author=getattr(entry, "author", None),
                created_at=created_at,
                tags=["reddit", f"r-{subreddit}"],
            )
        except Exception:
            return None

    def _extract_score_and_title(self, title: str, entry: Any) -> tuple[int, str]:
        """Extract score from title and return (score, cleaned_title)."""
        import re
        match = re.match(r"\[(\d+)\]\s*(.*)", title)
        if match:
            return int(match.group(1)), match.group(2).strip()

        score = getattr(entry, "score", 0)
        return score, title


async def collect_reddit(
    subreddits: list[str] | None = None,
    min_score: int = 100,
    max_age_days: int = 7,
) -> list[Candidate]:
    """Convenience function for collecting from Reddit."""
    async with RedditCollector(subreddits=subreddits, min_score=min_score, max_age_days=max_age_days) as collector:
        return await collector.collect()  # type: ignore[no-any-return]
