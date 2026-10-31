import json
import logging
from pathlib import Path

from groq import AsyncGroq
from pydantic import ValidationError

from dailydevfinds.config import get_config
from dailydevfinds.models import Candidate, RankResult

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "ranker.md"


def load_ranker_prompt() -> str:
    """Load the ranker prompt from file."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def format_candidates_for_prompt(candidates: list[Candidate]) -> str:
    """Format candidates as JSON for the prompt."""
    return json.dumps(
        [
            {
                "id": c.id,
                "title": c.title,
                "url": str(c.url),
                "source": c.source.value,
                "score": c.source_score,
                "description": c.description,
                "github_url": str(c.github_url) if c.github_url else None,
                "tags": c.tags,
            }
            for c in candidates
        ],
        indent=2,
    )


async def rank_candidates(candidates: list[Candidate]) -> RankResult:
    """Rank candidates using LLM, with fallback to highest score."""
    if not candidates:
        raise ValueError("No candidates to rank")

    config = get_config()
    llm_config = config.get("llm", {})

    # Try LLM ranking
    try:
        prompt = load_ranker_prompt()
        candidates_json = format_candidates_for_prompt(candidates)
        full_prompt = prompt.replace("{{candidates_json}}", candidates_json)

        client = AsyncGroq(api_key=llm_config.get("api_key"))
        model = llm_config.get("model", "llama-3.3-70b-versatile")
        max_tokens = llm_config.get("max_tokens", 2000)
        temperature = llm_config.get("temperature", 0.7)

        logger.info(f"Ranking {len(candidates)} candidates with LLM...")
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": full_prompt}],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content if response.choices else ""
        result = _parse_rank_result(content or "", candidates)

        if result:
            logger.info(f"LLM picked: {result.pick_id} - {result.reason[:100]}...")
            return result

    except Exception as e:
        logger.warning(f"LLM ranking failed: {e}, falling back to highest score")

    # Fallback: highest source_score
    logger.info("Using fallback: highest source_score")
    return _fallback_rank(candidates)


def _parse_rank_result(content: str, candidates: list[Candidate]) -> RankResult | None:
    """Parse and validate LLM response."""
    try:
        # Extract JSON from response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        json_str = content[start:end]
        data = json.loads(json_str)

        # Validate with pydantic
        result = RankResult(**data)

        # Verify pick_id exists in candidates
        candidate_ids = {c.id for c in candidates}
        if result.pick_id not in candidate_ids:
            logger.warning(f"LLM picked unknown ID: {result.pick_id}")
            return None

        # Verify runner_ups exist
        for rid in result.runner_ups:
            if rid not in candidate_ids:
                logger.warning(f"LLM runner-up unknown ID: {rid}")
                return None

        return result

    except (json.JSONDecodeError, ValidationError, KeyError) as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return None


def _fallback_rank(candidates: list[Candidate]) -> RankResult:
    """Fallback ranking by source_score."""
    sorted_candidates = sorted(candidates, key=lambda c: c.source_score, reverse=True)
    pick = sorted_candidates[0]
    runner_ups = [c.id for c in sorted_candidates[1:3]]

    return RankResult(
        pick_id=pick.id,
        reason=f"Highest score ({pick.source_score:.0f}) from {pick.source.value}: {pick.title}",
        runner_ups=runner_ups,
    )
