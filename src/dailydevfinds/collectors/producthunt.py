import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from dailydevfinds.collectors.base import BaseCollector
from dailydevfinds.models import Candidate, Source


class ProductHuntCollector(BaseCollector):  # type: ignore[misc]
    """Collects candidates from Product Hunt via GraphQL API."""

    BASE_URL = "https://api.producthunt.com/v2/api/graphql"
    MIN_VOTES = 50
    MAX_AGE_DAYS = 14

    GRAPHQL_QUERY = """
    query GetPosts($first: Int!, $after: String, $order: PostOrder!) {
      posts(first: $first, after: $after, order: $order) {
        edges {
          node {
            id
            name
            tagline
            description
            url
            votesCount
            createdAt
            website
            thumbnail {
              url
            }
            topics {
              edges {
                node {
                  name
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    def __init__(
        self,
        token: str | None = None,
        min_votes: int = MIN_VOTES,
        max_age_days: int = MAX_AGE_DAYS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.token = token or os.getenv("PRODUCTHUNT_TOKEN")
        self.min_votes = min_votes
        self.max_age_days = max_age_days

        if self.token:
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        self.client.headers.update({"Content-Type": "application/json"})

    async def collect(self) -> list[Candidate]:
        """Fetch posts from Product Hunt GraphQL API."""
        if not self.token:
            return []

        cutoff_date = datetime.now(UTC) - timedelta(days=self.max_age_days)
        all_candidates: list[Candidate] = []

        try:
            variables: dict[str, Any] = {
                "first": 50,
                "order": "VOTES",
            }

            while True:
                response = await self._post(
                    self.BASE_URL,
                    json={"query": self.GRAPHQL_QUERY, "variables": variables},
                )
                data = response.json()

                if "errors" in data:
                    break

                posts_data = data.get("data", {}).get("posts", {})
                edges: list[dict[str, Any]] = posts_data.get("edges", [])

                for edge in edges:
                    node = edge.get("node", {})
                    candidate = self._node_to_candidate(node)
                    if candidate and candidate.source_score >= self.min_votes:
                        created_at = candidate.created_at
                        if created_at and created_at >= cutoff_date:
                            all_candidates.append(candidate)

                page_info = posts_data.get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    break

                variables["after"] = page_info.get("endCursor")

        except httpx.HTTPError:
            pass

        return all_candidates

    def _node_to_candidate(self, node: dict[str, Any]) -> Candidate | None:
        """Convert GraphQL node to Candidate."""
        try:
            name = node.get("name", "").strip()
            if not name:
                return None

            url = node.get("url", "").strip()
            if not url:
                return None

            description = node.get("description") or node.get("tagline")
            if description:
                description = description.strip()[:500]

            votes = node.get("votesCount", 0)
            created_at_str = node.get("createdAt")
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else None

            topics: list[str] = []
            for topic_edge in node.get("topics", {}).get("edges", []):
                topic_name = topic_edge.get("node", {}).get("name", "")
                if topic_name:
                    topics.append(topic_name.lower().replace(" ", "-"))

            return Candidate(
                id=f"ph:{node.get('id', '')}",
                title=name[:200],
                url=url,
                source=Source.PRODUCTHUNT,
                source_score=float(votes),
                description=description,
                author=None,
                created_at=created_at,
                tags=["producthunt"] + topics,
            )
        except Exception:
            return None


async def collect_producthunt(
    token: str | None = None,
    min_votes: int = 50,
    max_age_days: int = 14,
) -> list[Candidate]:
    """Convenience function for collecting from Product Hunt."""
    async with ProductHuntCollector(token=token, min_votes=min_votes, max_age_days=max_age_days) as collector:
        return await collector.collect()  # type: ignore[no-any-return]
