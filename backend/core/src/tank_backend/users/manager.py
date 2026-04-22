"""UserManager — thin aggregation layer over SpeakerRepository + user filesystem.

Speaker DB is the source of truth for user identity.
Filesystem (~/.tank/users/{user_id}/) is only for prompt assembly files:
  - USER.md (static per-user instructions)
  - preferences.md (dynamic learned preferences, managed by PreferenceStore)
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..audio.input.repository import SpeakerRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User:
    """User view derived from speaker DB."""

    user_id: str
    name: str
    sample_count: int
    created_at: float
    updated_at: float


class UserManager:
    """Aggregates speaker DB reads with user folder path resolution.

    Speaker DB (``SpeakerRepository``) is the sole source of truth for user
    identity.  The filesystem under ``users_dir`` holds only prompt-assembly
    files (``USER.md``, ``preferences.md``) and is created lazily.
    """

    def __init__(self, speaker_repo: SpeakerRepository | None, users_dir: Path) -> None:
        self._repo = speaker_repo
        self._users_dir = users_dir

    def list_users(self) -> list[User]:
        """List all users from speaker DB, sorted by name."""
        if self._repo is None:
            return []
        speakers = self._repo.list_speakers()
        users = [
            User(
                user_id=s.user_id,
                name=s.name,
                sample_count=len(s.embeddings),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in speakers
        ]
        return sorted(users, key=lambda u: u.name.lower())

    def get_user(self, user_id: str) -> User | None:
        """Get user by ID from speaker DB."""
        if self._repo is None:
            return None
        speaker = self._repo.get_speaker(user_id)
        if speaker is None:
            return None
        return User(
            user_id=speaker.user_id,
            name=speaker.name,
            sample_count=len(speaker.embeddings),
            created_at=speaker.created_at,
            updated_at=speaker.updated_at,
        )

    def resolve_name(self, user_id: str) -> str:
        """Resolve user_id to display name. Returns 'Guest' if not found."""
        user = self.get_user(user_id)
        return user.name if user else "Guest"

    def delete_user(self, user_id: str) -> bool:
        """Delete user from speaker DB and remove user folder if it exists."""
        if self._repo is None:
            return False
        deleted = self._repo.delete_speaker(user_id)
        if deleted:
            user_dir = self._users_dir / user_id
            if user_dir.is_dir():
                shutil.rmtree(user_dir)
                logger.info("Removed user folder: %s", user_dir)
        return deleted

    def user_dir(self, user_id: str) -> Path:
        """Return the user folder path (may not exist on disk)."""
        return self._users_dir / user_id
