"""Unified user management — speaker DB as source of truth."""

from .manager import User, UserManager


def is_guest(user: str) -> bool:
    """Return True for unidentified / guest speakers.

    Guest users should not accumulate preferences, memories, or
    personalised system-prompt sections.
    """
    return not user or user == "Unknown"


__all__ = ["User", "UserManager", "is_guest"]
