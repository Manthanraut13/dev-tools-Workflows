import json
from pathlib import Path
import pytest
import respx
import httpx

from dailydevfinds.collectors.hn import collect_hackernews, HackerNewsCollector
from dailydevfinds.collectors.github import collect_github, GitHubCollector
from dailydevfinds.collectors.producthunt import collect_producthunt, ProductHuntCollector
from dailydevfinds.collectors.devto import collect_devto, DevToCollector
from dailydevfinds.collectors.reddit import collect_reddit, RedditCollector
from dailydevfinds.models import Candidate, Source


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def load_fixture_text(name: str) -> str:
    with open(FIXTURES_DIR / name) as f:
        return f.read()


@pytest.mark.asyncio
async def test_hn_collector_parses_hits():
    """Test HN collector parses Algolia response correctly."""
    fixture = load_fixture("hn_response.json")

    with respx.mock:
        route = respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_hackernews(min_score=50, max_age_days=7)

    assert route.called
    assert len(candidates) == 2  # Third item has no URL, should be skipped

    c1 = candidates[0]
    assert isinstance(c1, Candidate)
    assert c1.source == Source.HACKERNEWS
    assert c1.title == "Amazing CLI Tool for Developers"
    assert str(c1.url) == "https://github.com/user/amazing-cli"
    assert c1.source_score == 245
    assert c1.author == "developer123"
    assert "hackernews" in c1.tags


@pytest.mark.asyncio
async def test_hn_collector_skips_no_url():
    """Test HN collector skips items without URL (Ask HN, etc.)."""
    fixture = load_fixture("hn_response.json")

    with respx.mock:
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_hackernews()

    # Only 2 items have URLs
    assert len(candidates) == 2
    for c in candidates:
        assert str(c.url).startswith("http")


@pytest.mark.asyncio
async def test_github_collector_parses_items():
    """Test GitHub collector parses search response correctly."""
    fixture = load_fixture("github_response.json")

    with respx.mock:
        route = respx.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_github(min_stars=100, max_age_days=30)

    assert route.called
    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.source == Source.GITHUB
    assert c1.title == "super-cli"
    assert str(c1.url) == "https://github.com/user/super-cli"
    assert c1.source_score == 1500
    assert c1.github_url == c1.url
    assert c1.author == "devuser"
    assert "github" in c1.tags


@pytest.mark.asyncio
async def test_producthunt_collector_parses_graphql():
    """Test Product Hunt collector parses GraphQL response correctly."""
    fixture = load_fixture("producthunt_response.json")

    with respx.mock:
        route = respx.post("https://api.producthunt.com/v2/api/graphql").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_producthunt(token="test-token", min_votes=50, max_age_days=3650)

    assert route.called
    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.source == Source.PRODUCTHUNT
    assert c1.title == "DevTool Pro"
    assert str(c1.url) == "https://producthunt.com/posts/devtool-pro"
    assert c1.source_score == 342
    assert "producthunt" in c1.tags
    assert "developer-tools" in c1.tags


@pytest.mark.asyncio
async def test_devto_collector_parses_articles():
    """Test dev.to collector parses API response correctly."""
    fixture = load_fixture("devto_response.json")

    with respx.mock:
        route = respx.get("https://dev.to/api/articles").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_devto(min_reactions=20, max_age_days=3650)

    assert route.called
    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.source == Source.DEVTO
    assert c1.title == "10 VS Code Extensions That Will Change Your Life"
    assert str(c1.url) == "https://dev.to/user/10-vscode-extensions"
    # score = reactions + comments*2 = 245 + 64 = 309
    assert c1.source_score == 309
    assert c1.author == "coder123"
    assert "devto" in c1.tags


@pytest.mark.asyncio
async def test_reddit_collector_parses_rss():
    """Test Reddit collector parses RSS feed correctly."""
    fixture_text = load_fixture_text("reddit_response.xml")

    with respx.mock:
        route = respx.get("https://www.reddit.com/r/programming/top/.rss?t=week&limit=50").mock(
            return_value=httpx.Response(200, text=fixture_text)
        )

        candidates = await collect_reddit(subreddits=["programming"], min_score=100, max_age_days=3650)

    assert route.called
    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.source == Source.REDDIT
    assert c1.title == "Amazing new Rust CLI tool for code analysis"
    assert "r-programming" in c1.tags
    assert c1.source_score == 245


@pytest.mark.asyncio
async def test_collectors_handle_http_error():
    """Test collectors return empty list on HTTP error."""
    with respx.mock:
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(500)
        )

        candidates = await collect_hackernews()

    assert candidates == []


@pytest.mark.asyncio
async def test_collectors_deduplicate_by_url():
    """Test that duplicate URLs are handled (simulated)."""
    # This tests the GitHub collector's internal dedupe logic
    fixture = {
        "total_count": 2,
        "items": [
            {
                "id": 1,
                "name": "repo",
                "html_url": "https://github.com/user/repo",
                "description": "First",
                "stargazers_count": 100,
                "owner": {"login": "user1"},
                "created_at": "2024-10-01T12:00:00Z"
            },
            {
                "id": 2,
                "name": "repo",
                "html_url": "https://github.com/user/repo",  # Same URL
                "description": "Second",
                "stargazers_count": 200,
                "owner": {"login": "user2"},
                "created_at": "2024-10-01T12:00:00Z"
            }
        ]
    }

    with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        candidates = await collect_github()

    # Should deduplicate by URL
    assert len(candidates) == 1