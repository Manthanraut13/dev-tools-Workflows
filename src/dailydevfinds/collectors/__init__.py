import asyncio
import logging

from dailydevfinds.config import get_config
from dailydevfinds.models import Candidate

logger = logging.getLogger(__name__)


async def collect_all() -> list[Candidate]:
    """Collect candidates from all enabled sources concurrently."""
    from dailydevfinds.collectors.devto import collect_devto
    from dailydevfinds.collectors.github import collect_github
    from dailydevfinds.collectors.hn import collect_hackernews
    from dailydevfinds.collectors.producthunt import collect_producthunt
    from dailydevfinds.collectors.reddit import collect_reddit

    config = get_config()
    sources_config = config.get("sources", {})

    tasks = []

    # Hacker News
    if sources_config.get("hackernews", {}).get("enabled", True):
        hn_config = sources_config["hackernews"]
        tasks.append(
            collect_hackernews(
                min_score=hn_config.get("min_score", 50),
                max_age_days=hn_config.get("max_age_days", 7),
            )
        )

    # GitHub
    if sources_config.get("github", {}).get("enabled", True):
        gh_config = sources_config["github"]
        tasks.append(
            collect_github(
                min_stars=gh_config.get("min_stars", 100),
                max_age_days=gh_config.get("max_age_days", 30),
                queries=gh_config.get("search_queries"),
            )
        )

    # Product Hunt
    if sources_config.get("producthunt", {}).get("enabled", True):
        ph_config = sources_config["producthunt"]
        tasks.append(
            collect_producthunt(
                min_votes=ph_config.get("min_votes", 50),
                max_age_days=ph_config.get("max_age_days", 14),
            )
        )

    # dev.to
    if sources_config.get("devto", {}).get("enabled", True):
        dt_config = sources_config["devto"]
        tasks.append(
            collect_devto(
                min_reactions=dt_config.get("min_reactions", 20),
                max_age_days=dt_config.get("max_age_days", 14),
            )
        )

    # Reddit
    if sources_config.get("reddit", {}).get("enabled", True):
        rd_config = sources_config["reddit"]
        tasks.append(
            collect_reddit(
                subreddits=rd_config.get("subreddits"),
                min_score=rd_config.get("min_score", 100),
                max_age_days=rd_config.get("max_age_days", 7),
            )
        )

    if not tasks:
        logger.warning("No sources enabled!")
        return []

    logger.info(f"Starting collection from {len(tasks)} sources...")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_candidates = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Source {i} failed: {result}")
        elif isinstance(result, list):
            all_candidates.extend(result)
            logger.info(f"Source {i} returned {len(result)} candidates")
        else:
            logger.warning(f"Source {i} returned unexpected type: {type(result)}")

    logger.info(f"Total candidates collected: {len(all_candidates)}")
    return all_candidates
