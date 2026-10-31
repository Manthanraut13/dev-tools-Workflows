#!/usr/bin/env python3
"""
DailyDevFinds - Daily developer resource discovery agent.
Finds one useful tool/app/repo per day and emails a LinkedIn-ready post.
"""

import argparse
import asyncio
import logging
import sys

from dailydevfinds.collectors import collect_all
from dailydevfinds.enricher import enrich_candidate
from dailydevfinds.filters import filter_candidates, top_candidates
from dailydevfinds.mailer import send_email, update_state
from dailydevfinds.models import Candidate
from dailydevfinds.ranker import rank_candidates
from dailydevfinds.writer import write_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _find_candidate_by_id(candidates: list[Candidate], candidate_id: str) -> Candidate | None:
    for c in candidates:
        if c.id == candidate_id:
            return c
    return None


async def _async_main(dry_run: bool = False) -> int:
    """Async main pipeline entry point."""
    logger.info("Starting DailyDevFinds pipeline")

    if dry_run:
        logger.info("DRY RUN MODE - no email will be sent")

    # Phase 2 - Collect candidates from all sources
    candidates: list[Candidate] = await collect_all()
    logger.info(f"Collected {len(candidates)} candidates")

    if not candidates:
        logger.error("No candidates collected!")
        return 1

    # Phase 3 - Filter and deduplicate
    filtered: list[Candidate] = filter_candidates(candidates)
    logger.info(f"After filtering: {len(filtered)} candidates")

    if not filtered:
        logger.error("No candidates after filtering!")
        return 1

    # Take top 15 for ranking
    top = top_candidates(filtered, 15)
    logger.info(f"Top {len(top)} candidates for ranking")

    # Phase 4 - Rank with LLM
    rank_result = await rank_candidates(top)
    logger.info(f"Ranked: pick={rank_result.pick_id}, runner_ups={rank_result.runner_ups}")

    # Get the picked candidate
    picked = _find_candidate_by_id(candidates, rank_result.pick_id)
    if not picked:
        logger.error(f"Picked candidate not found: {rank_result.pick_id}")
        return 1

    runner_up_candidates = [_find_candidate_by_id(candidates, rid) for rid in rank_result.runner_ups]
    runner_up_candidates = [c for c in runner_up_candidates if c]

    # Phase 5 - Enrich and fetch image
    logger.info(f"Enriching candidate: {picked.id}")
    facts = await enrich_candidate(picked)
    logger.info(f"Enriched: {facts.name}")

    # Phase 6 - Write and validate post
    logger.info("Writing LinkedIn post...")
    post = await write_post(facts)
    logger.info(f"Post written: {len(post.text.split())} words, {len(post.hashtags)} hashtags")

    # Phase 7 - Send email
    logger.info("Sending email...")
    success = await send_email(
        post_text=post.full_text(),
        reason=rank_result.reason,
        runner_ups=[c.title for c in runner_up_candidates if c],
        image_path=post.image_path,
        pick_name=picked.title,
        dry_run=dry_run,
    )

    # In dry-run mode, email "failure" is expected since we're just testing the pipeline
    if not success and not dry_run:
        logger.error("Failed to send email")
        return 1

    # Phase 8 - Update state
    if not dry_run:
        await update_state(str(picked.url))
        logger.info("State updated")

    logger.info("Pipeline completed successfully")
    return 0


def main() -> None:
    """Sync entry point for console script."""
    parser = argparse.ArgumentParser(description="DailyDevFinds agent")
    parser.add_argument("--dry-run", action="store_true", help="Print output instead of sending email")
    args = parser.parse_args()

    sys.exit(asyncio.run(_async_main(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
