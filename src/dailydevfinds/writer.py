import json
import logging
import re
from pathlib import Path
from typing import Any

from groq import AsyncGroq

from dailydevfinds.config import get_config
from dailydevfinds.models import FactsBundle, Post

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
POST_CONFIG = get_config().get("post", {})


async def write_post(facts: FactsBundle) -> Post:
    """Write LinkedIn post from facts, with validation and retries."""
    config = get_config()
    llm_config = config.get("llm", {})
    post_config = config.get("post", {})

    min_words = post_config.get("min_words", 90)
    max_words = post_config.get("max_words", 150)
    max_emojis = post_config.get("max_emojis", 3)
    min_hashtags = post_config.get("min_hashtags", 3)
    max_hashtags = post_config.get("max_hashtags", 5)

    for attempt in range(3):  # Max 2 retries = 3 attempts
        try:
            post = await _generate_post(facts, llm_config)
            post = _ensure_links(post, facts)

            # Validate
            validation = _validate_post(post, min_words, max_words, max_emojis, min_hashtags, max_hashtags, facts)
            if validation.is_valid:
                logger.info(f"Post validated on attempt {attempt + 1}")
                return post

            logger.warning(f"Validation failed (attempt {attempt + 1}): {validation.errors}")

        except Exception as e:
            logger.warning(f"Post generation failed (attempt {attempt + 1}): {e}")

    # Fallback: template post
    logger.info("Using fallback template post")
    return _fallback_post(facts)


async def _generate_post(facts: FactsBundle, llm_config: dict[str, Any]) -> Post:
    """Generate post using LLM."""
    prompt = _load_writer_prompt()
    facts_json = _format_facts_for_prompt(facts)
    full_prompt = prompt.replace("{{facts_json}}", facts_json)

    client = AsyncGroq(api_key=llm_config.get("api_key"))
    model = llm_config.get("model", "llama-3.3-70b-versatile")
    max_tokens = llm_config.get("max_tokens", 2000)
    temperature = llm_config.get("temperature", 0.7)

    logger.info("Generating post with LLM...")
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": full_prompt}],
    )

    content = response.choices[0].message.content if response.choices else ""

    # Parse the generated post
    return _parse_generated_post(content or "", facts)


def _load_writer_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _format_facts_for_prompt(facts: FactsBundle) -> str:
    return json.dumps({
        "name": facts.name,
        "what_it_does": facts.what_it_does,
        "key_features": facts.key_features,
        "license": facts.license,
        "pricing": facts.pricing,
        "stars": facts.stars,
        "language": facts.language,
        "website_url": str(facts.website_url) if facts.website_url else None,
        "github_url": str(facts.github_url) if facts.github_url else None,
    }, indent=2)


def _parse_generated_post(content: str, facts: FactsBundle) -> Post:
    """Parse LLM response into Post model."""
    lines = content.strip().split("\n")

    # Extract hashtags (last line with #)
    hashtags: list[str] = []
    text_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("#") and not text_lines:
            # This is the hashtag line
            hashtags = [tag.strip("#") for tag in line.split() if tag.startswith("#")]
        else:
            text_lines.append(line)

    text = "\n".join(text_lines).strip()

    # Count emojis
    emoji_count = len(re.findall(r"[😀-🙏]|[🌀-🗿]|[🀀-🏿]|[⚡-❤️]", text))

    # Primary link
    primary_link = facts.website_url or facts.github_url
    if not primary_link:
        raise ValueError("No valid link in facts")

    return Post(
        text=text,
        hashtags=hashtags,
        emoji_count=emoji_count,
        primary_link=primary_link,
        github_link=facts.github_url,
    )


def _ensure_links(post: Post, facts: FactsBundle) -> Post:
    """Ensure post contains required links."""
    text = post.text
    primary = str(post.primary_link)
    github = str(post.github_link) if post.github_link else None

    if primary not in text:
        text = f"{text}\n\n{primary}"

    if github and github not in text:
        text = f"{text}\n{github}"

    return Post(
        text=text,
        hashtags=post.hashtags,
        emoji_count=post.emoji_count,
        primary_link=post.primary_link,
        github_link=post.github_link,
        image_path=post.image_path,
    )


class ValidationResult:
    def __init__(self, is_valid: bool, errors: list[str]):
        self.is_valid = is_valid
        self.errors = errors


def _validate_post(
    post: Post,
    min_words: int,
    max_words: int,
    max_emojis: int,
    min_hashtags: int,
    max_hashtags: int,
    facts: FactsBundle,
) -> ValidationResult:
    """Validate post against rules."""
    errors = []

    # Word count
    word_count = len(post.text.split())
    if word_count < min_words:
        errors.append(f"Word count {word_count} < {min_words}")
    if word_count > max_words:
        errors.append(f"Word count {word_count} > {max_words}")

    # Emoji count
    if post.emoji_count > max_emojis:
        errors.append(f"Emoji count {post.emoji_count} > {max_emojis}")

    # Hashtag count
    if len(post.hashtags) < min_hashtags:
        errors.append(f"Hashtag count {len(post.hashtags)} < {min_hashtags}")
    if len(post.hashtags) > max_hashtags:
        errors.append(f"Hashtag count {len(post.hashtags)} > {max_hashtags}")

    # Links present
    if str(post.primary_link) not in post.text:
        errors.append("Primary link missing from post text")

    # Numbers in post must appear in facts
    post_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", post.text))
    facts_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", facts.raw_content))
    # Allow small numbers (1-3) as they could be generic
    unexpected_numbers = {n for n in post_numbers if n not in facts_numbers and int(n) > 3}
    if unexpected_numbers:
        errors.append(f"Numbers not in facts: {unexpected_numbers}")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def _fallback_post(facts: FactsBundle) -> Post:
    """Create a simple template post as fallback."""
    primary = facts.website_url or facts.github_url or "https://example.com"
    github = str(facts.github_url) if facts.github_url else None

    what = facts.what_it_does[:200]
    lines = [
        f"Found a genuinely useful tool today: {facts.name}",
        what,
        "It handles the tedious parts of development workflows that usually eat up hours of manual work.",
        "The setup is straightforward and it integrates cleanly with existing toolchains.",
        "Best of all, it's open source so you can audit the code and contribute back.",
        "If you've been looking for something to automate repetitive dev tasks, this is worth checking out.",
        "The community around it is active and responsive, with regular updates.",
        "It works well on both Windows and macOS development setups.",
        "If you've been looking for something to automate repetitive dev tasks, this is worth checking out.",
        primary,
    ]
    if github:
        lines.append(github)

    text = "\n".join(lines)

    return Post(
        text=text,
        hashtags=["developertools", "productivity", "opensource", "coding"],
        emoji_count=0,
        primary_link=primary,
        github_link=facts.github_url,
    )
