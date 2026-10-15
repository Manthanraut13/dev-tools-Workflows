import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from dailydevfinds.config import get_config
from dailydevfinds.models import Candidate, FactsBundle

logger = logging.getLogger(__name__)

MIN_IMAGE_WIDTH = 600
MIN_IMAGE_HEIGHT = 400


async def enrich_candidate(candidate: Candidate) -> FactsBundle:
    """Enrich a candidate by fetching page content and extracting facts."""
    logger.info(f"Enriching candidate: {candidate.id}")

    # Try to fetch the main page
    content = ""
    website_url = candidate.url
    github_url = candidate.github_url

    # Fetch main page content
    try:
        content = await _fetch_page_content(str(candidate.url))
    except Exception as e:
        logger.warning(f"Failed to fetch main page for {candidate.id}: {e}")

    # If GitHub URL exists and different from main, fetch README
    readme_content = ""
    if github_url and str(github_url) != str(candidate.url):
        try:
            readme_content = await _fetch_github_readme(str(github_url))
            if readme_content:
                content += "\n\n--- GITHUB README ---\n\n" + readme_content
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub README for {candidate.id}: {e}")

    # Verify links are live
    website_url = await _verify_url(str(candidate.url)) and str(candidate.url) or None
    github_url_verified = await _verify_url(str(candidate.github_url)) and str(candidate.github_url) or None if candidate.github_url else None

    # Extract facts from content
    facts = _extract_facts(candidate, content)

    # Override with verified URLs
    facts.website_url = website_url
    facts.github_url = github_url_verified

    # Try to get image
    image_path = await _fetch_image(candidate, content)
    if image_path:
        logger.info(f"Found image for {candidate.id}: {image_path}")

    return facts


async def _fetch_page_content(url: str) -> str:
    """Fetch and extract text content from a web page."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "DailyDevFinds/0.1"})
        response.raise_for_status()

        # Use trafilatura for clean extraction
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        if extracted:
            return extracted[:10000]  # Limit size

        # Fallback to BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        return soup.get_text()[:10000]


async def _fetch_github_readme(repo_url: str) -> str:
    """Fetch README from GitHub repository."""
    # Convert to raw GitHub content URL
    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(raw_url)
            if response.status_code == 200:
                return response.text[:8000]

    return ""


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
)
async def _verify_url(url: str) -> bool:
    """Verify URL returns 200 OK."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code == 405:  # HEAD not allowed, try GET
                response = await client.get(url)
            return response.status_code == 200
    except Exception:
        return False


def _extract_facts(candidate: Candidate, content: str) -> FactsBundle:
    """Extract structured facts from content."""
    # Basic facts from candidate
    facts = FactsBundle(
        name=candidate.title,
        what_it_does=_extract_what_it_does(candidate, content),
        key_features=_extract_features(content),
        license=_extract_license(content),
        pricing=_extract_pricing(content),
        stars=int(candidate.source_score) if candidate.source_score else None,
        language=_extract_language(content),
        website_url=str(candidate.url),
        github_url=str(candidate.github_url) if candidate.github_url else None,
        raw_content=content[:5000],
    )

    return facts


def _extract_what_it_does(candidate: Candidate, content: str) -> str:
    """Extract what the tool does."""
    desc = candidate.description
    if desc is not None:
        return desc[:500]  # type: ignore[no-any-return]

    # Try to get first meaningful sentence from content
    sentences = re.split(r"[.!?]+", content)
    for s in sentences:
        s = s.strip()
        if len(s) > 50 and len(s) < 300:
            return s

    return f"{candidate.title} - a {candidate.source.value} resource for developers."


def _extract_features(content: str) -> list[str]:
    """Extract key features from content."""
    features = []

    # Look for feature-like patterns
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if any(kw in line.lower() for kw in ["feature", "supports", "includes", "provides", "offers", "enables"]) and 20 < len(line) < 200:
            features.append(line[:200])

    return features[:5]  # Max 5 features


def _extract_license(content: str) -> str | None:
    """Extract license information."""
    license_patterns = [
        r"(MIT|Apache-2\.0|GPL-3\.0|BSD-3-Clause|BSD-2-Clause|ISC|MPL-2\.0)",
        r"license[:\s]+([A-Za-z0-9\-\.]+)",
    ]

    content_lower = content.lower()
    for pattern in license_patterns:
        match = re.search(pattern, content_lower, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def _extract_pricing(content: str) -> str | None:
    """Extract pricing information."""
    content_lower = content.lower()

    if any(kw in content_lower for kw in ["free", "open source", "opensource", "no cost", "gratis"]):
        return "Free / Open Source"
    elif any(kw in content_lower for kw in ["paid", "subscription", "pricing", "plan", "$", "per month", "/mo"]):
        return "Paid"

    return None


def _extract_language(content: str) -> str | None:
    """Extract programming language."""
    languages = [
        "Python", "JavaScript", "TypeScript", "Rust", "Go", "Java", "C#", "C++",
        "Ruby", "PHP", "Swift", "Kotlin", "Dart", "Scala", "Clojure", "Haskell",
        "Elixir", "Erlang", "Lua", "Perl", "R", "Julia", "Zig", "V",
    ]

    content_lower = content.lower()
    for lang in languages:
        if lang.lower() in content_lower:
            return lang

    return None


async def _fetch_image(candidate: Candidate, content: str) -> str | None:
    """Fetch image using og:image → GitHub card → Playwright screenshot chain."""
    config = get_config()
    img_config = config.get("image", {})
    min_width = img_config.get("min_width", MIN_IMAGE_WIDTH)
    min_height = img_config.get("min_height", MIN_IMAGE_HEIGHT)

    # 1. Try og:image from the page
    og_image = await _fetch_og_image(str(candidate.url))
    if og_image and await _verify_image_size(og_image, min_width, min_height):
        return await _save_image(og_image, candidate.id)

    # 2. Try GitHub social card if GitHub URL exists
    if candidate.github_url:
        gh_card = f"https://opengraph.githubassets.com/1/{candidate.github_url}"
        if await _verify_image_size(gh_card, min_width, min_height):
            return await _save_image(gh_card, candidate.id)

    # 3. Try Playwright screenshot (requires Playwright installed)
    screenshot = await _playwright_screenshot(str(candidate.url), candidate.id)
    if screenshot:
        return screenshot

    return None


async def _fetch_og_image(url: str) -> str | None:
    """Extract og:image from page."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            # Handle case where content might be a list
            if isinstance(img_url, list):
                img_url = img_url[0] if img_url else ""
            # Make absolute
            return urljoin(url, img_url)

        # Also check twitter:image
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            img_url = twitter_image["content"]
            if isinstance(img_url, list):
                img_url = img_url[0] if img_url else ""
            return urljoin(url, img_url)

    except Exception:
        pass

    return None


async def _verify_image_size(url: str, min_width: int, min_height: int) -> bool:
    """Verify image meets minimum dimensions."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(url)
            if response.status_code != 200:
                return False

            # Check content-type
            content_type = response.headers.get("content-type", "")
            return bool(content_type and content_type.startswith("image/"))

    except Exception:
        return False


async def _save_image(url: str, candidate_id: str) -> str | None:
    """Download and save image."""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        # Determine extension
        content_type = response.headers.get("content-type", "")
        ext = ".png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"

        # Save
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", candidate_id)
        filename = f"image_{safe_id}{ext}"
        filepath = Path("images") / filename
        filepath.parent.mkdir(exist_ok=True)

        filepath.write_bytes(response.content)
        return str(filepath)

    except Exception as e:
        logger.warning(f"Failed to save image from {url}: {e}")
        return None


async def _playwright_screenshot(url: str, candidate_id: str) -> str | None:
    """Take screenshot using Playwright."""
    try:
        from playwright.async_api import async_playwright

        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", candidate_id)
        filename = f"screenshot_{safe_id}.png"
        filepath = Path("images") / filename
        filepath.parent.mkdir(exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1200, "height": 800})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=str(filepath), full_page=False)
            await browser.close()

        return str(filepath)

    except ImportError:
        logger.warning("Playwright not installed, skipping screenshot")
        return None
    except Exception as e:
        logger.warning(f"Playwright screenshot failed for {url}: {e}")
        return None
