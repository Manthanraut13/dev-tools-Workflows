from urllib.parse import urlparse

from dailydevfinds.config import get_config
from dailydevfinds.models import Candidate
from dailydevfinds.state import is_posted_recently, load_posted_detailed


def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    parsed = urlparse(url.lower().rstrip("/"))
    # Remove www prefix
    netloc = parsed.netloc.replace("www.", "")
    # Reconstruct without fragment and query for dedup
    normalized = f"{parsed.scheme}://{netloc}{parsed.path}"
    return normalized.rstrip("/")


def is_spam_or_low_quality(candidate: Candidate, blocklist: list[str]) -> bool:
    """Check if candidate is spam, low quality, or blocked."""
    text = f"{candidate.title} {candidate.description or ''}".lower()

    # Check blocklist keywords
    for keyword in blocklist:
        if keyword.lower() in text:
            return True

    # Must have a description
    if not candidate.description or len(candidate.description.strip()) < 20:
        return True

    # Must have a valid-looking URL
    return not (candidate.url and str(candidate.url).startswith(("http://", "https://")))


def filter_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Filter and deduplicate candidates."""
    config = get_config()
    sources_config = config.get("sources", {})
    blocklist = config.get("blocklist", [])
    dedupe_days = config.get("dedupe_days", 90)

    # Load posted URLs (detailed format with timestamps)
    posted_urls = load_posted_detailed()

    # Track seen URLs in this run
    seen_normalized: set[str] = set()

    filtered: list[Candidate] = []

    for candidate in candidates:
        norm_url = candidate.normalized_url()

        # Skip if already seen in this run
        if norm_url in seen_normalized:
            continue

        # Skip if posted recently
        if is_posted_recently(norm_url, posted_urls, dedupe_days):
            continue

        # Skip spam/low quality
        if is_spam_or_low_quality(candidate, blocklist):
            continue

        # Source-specific minimum score checks
        source_config = sources_config.get(candidate.source.value, {})
        min_score = source_config.get("min_score") or source_config.get("min_stars") or source_config.get("min_votes") or source_config.get("min_reactions")
        if min_score and candidate.source_score < min_score:
            continue

        seen_normalized.add(norm_url)
        filtered.append(candidate)

    # Sort by source_score descending
    filtered.sort(key=lambda c: c.source_score, reverse=True)

    return filtered


def top_candidates(candidates: list[Candidate], limit: int = 15) -> list[Candidate]:
    """Get top N candidates by score."""
    return candidates[:limit]
