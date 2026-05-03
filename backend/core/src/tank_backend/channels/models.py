"""Channel data models and slug validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_SLUG_RE = re.compile(r"^[\w][\w\-]{1,48}[\w]$", re.UNICODE)


def validate_slug(slug: str) -> str:
    """Validate and return a channel slug.

    Rules:
    - 3–50 characters
    - Must start and end with a word character (Unicode letter, digit, underscore)
    - Middle characters may also contain hyphens
    - Supports Chinese, Japanese, and other Unicode scripts

    Raises:
        ValueError: If the slug is invalid.
    """
    if not slug:
        raise ValueError("Slug must not be empty")
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid slug '{slug}': must be 3-50 characters, "
            "start/end with a letter/number/underscore, "
            "and contain only letters, numbers, hyphens, or underscores"
        )
    return slug


def slugify(name: str) -> str:
    """Convert a display name to a valid slug.

    Examples:
        "Daily Report" -> "daily-report"
        "每日新闻" -> "每日新闻"
        "My Channel #1!" -> "my-channel-1"
    """
    slug = re.sub(r"[^\w\s\-]", "", name.strip(), flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    slug = slug.lower()
    # Ensure minimum length
    if len(slug) < 3:
        slug = slug + "-" + datetime.now(timezone.utc).strftime("%H%M%S")
    return validate_slug(slug)


def _humanize_slug(slug: str) -> str:
    """Convert a slug to a display name. Fallback for auto-created channels."""
    return slug.replace("-", " ").replace("_", " ").strip().title()


@dataclass(frozen=True)
class ChannelData:
    """Persistent channel record mapping slug to a conversation."""

    slug: str
    name: str
    conversation_id: str
    description: str = ""
    auto_created: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "conversation_id": self.conversation_id,
            "description": self.description,
            "auto_created": self.auto_created,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ChannelData:
        return ChannelData(
            slug=data["slug"],
            name=data["name"],
            conversation_id=data["conversation_id"],
            description=data.get("description", ""),
            auto_created=data.get("auto_created", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass(frozen=True)
class ChannelSummary:
    """Lightweight channel listing (no messages)."""

    slug: str
    name: str
    description: str
    message_count: int
    last_message_at: str
