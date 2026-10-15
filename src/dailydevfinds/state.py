import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dailydevfinds.config import get_config

STATE_FILE = Path(__file__).parent.parent.parent / "state" / "posted.json"


def load_posted() -> list[str]:
    """Load posted URLs from state file (legacy format - just URLs)."""
    if not STATE_FILE.exists():
        return []

    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
            if isinstance(data, list):
                # Handle both old format (list of strings) and new format (list of dicts)
                urls = []
                for item in data:
                    if isinstance(item, str):
                        urls.append(item)
                    elif isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])
                return urls
    except Exception:
        pass

    return []


def load_posted_detailed() -> list[dict[str, Any]]:
    """Load detailed posted entries from state file (new format - list of dicts with url and posted_at)."""
    if not STATE_FILE.exists():
        return []

    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass

    return []


def is_posted_recently(normalized_url: str, posted_urls: list[dict[str, Any]], days: int = 90) -> bool:
    """Check if a URL was posted within the last N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    for posted in posted_urls:
        if posted.get("url", "").rstrip("/").lower() == normalized_url:
            try:
                posted_at = datetime.fromisoformat(posted.get("posted_at", "").replace("Z", "+00:00"))
                if posted_at >= cutoff:
                    return True
            except Exception:
                # If date parsing fails, assume it's recent to be safe
                return True

    return False


def add_posted(url: str) -> None:
    """Add a URL to the posted state."""
    posted = load_posted_detailed()

    # Add new entry
    posted.append({
        "url": url,
        "posted_at": datetime.now(UTC).isoformat(),
    })

    # Keep only last 90 days
    config = get_config()
    dedupe_days = config.get("dedupe_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=dedupe_days)

    filtered = []
    for entry in posted:
        try:
            posted_at = datetime.fromisoformat(entry["posted_at"].replace("Z", "+00:00"))
            if posted_at >= cutoff:
                filtered.append(entry)
        except Exception:
            # Keep entries with unparseable dates
            filtered.append(entry)

    save_posted(filtered)


def save_posted(entries: list[dict[str, Any]]) -> None:
    """Save posted entries to state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def get_posted_count() -> int:
    """Get count of posted items in the last 90 days."""
    posted = load_posted_detailed()
    config = get_config()
    dedupe_days = config.get("dedupe_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=dedupe_days)

    count = 0
    for entry in posted:
        try:
            posted_at = datetime.fromisoformat(entry["posted_at"].replace("Z", "+00:00"))
            if posted_at >= cutoff:
                count += 1
        except Exception:
            count += 1

    return count
