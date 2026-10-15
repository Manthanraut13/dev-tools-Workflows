import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG: dict[str, Any] | None = None
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load configuration from config.yaml."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {_CONFIG_PATH}")

    with open(_CONFIG_PATH) as f:
        _CONFIG = yaml.safe_load(f)

    # Override with environment variables
    _apply_env_overrides(_CONFIG)
    return _CONFIG


def get_config() -> dict[str, Any]:
    """Get the loaded configuration."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def _apply_env_overrides(config: dict[str, Any]) -> None:
    """Apply environment variable overrides to config."""
    env_mappings: dict[str, list[str]] = {
        "ANTHROPIC_API_KEY": ["llm", "api_key"],
        "RESEND_API_KEY": ["email", "api_key"],
        "GH_TOKEN": ["sources", "github", "token"],
        "PRODUCTHUNT_TOKEN": ["sources", "producthunt", "token"],
        "OWNER_EMAIL": ["email", "owner"],
        "FROM_EMAIL": ["email", "from"],
    }

    for env_var, path in env_mappings.items():
        value = os.getenv(env_var)
        if value:
            _set_nested(config, path, value)


def _set_nested(d: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a nested dictionary value by path."""
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = value
