"""Configuration helpers for Nano Ant."""

from __future__ import annotations

import os
import re
from typing import Any


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_placeholders(value: Any) -> Any:
    """Resolve ${ENV_VAR} placeholders recursively."""
    if isinstance(value, dict):
        return {key: resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_env_placeholders(item) for item in value]
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda match: os.getenv(match.group(1).strip(), ""), value)
    return value
