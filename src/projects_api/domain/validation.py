"""Server-side validation rules for project creation.

This module is the single source of truth for the name rules. The Pydantic
request model calls into it, and the unit tests exercise it directly.
"""

import re

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 63

# Letters, digits, spaces, hyphens and underscores. Must start and end with a
# letter or digit so the name can later be turned into a DNS label / hostname.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$")

_WHITESPACE = re.compile(r"\s+")


def normalise_name(raw: str) -> str:
    """Trim and collapse internal whitespace. Preserves case for display."""
    return _WHITESPACE.sub(" ", raw.strip())


def validate_name(raw: str) -> str:
    """Return the normalised display name, or raise ValueError with a user-facing message."""
    name = normalise_name(raw)
    if len(name) < NAME_MIN_LENGTH:
        raise ValueError(f"Project name must be at least {NAME_MIN_LENGTH} characters.")
    if len(name) > NAME_MAX_LENGTH:
        raise ValueError(f"Project name must be at most {NAME_MAX_LENGTH} characters.")
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Project name may only contain letters, digits, spaces, hyphens and underscores, "
            "and must start and end with a letter or digit."
        )
    return name


def name_key(name: str) -> str:
    """Canonical uniqueness key: lower-cased, whitespace-collapsed name."""
    return normalise_name(name).lower()
