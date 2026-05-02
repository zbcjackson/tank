"""Cron expression validation."""

from __future__ import annotations

from croniter import croniter


def validate_cron(expression: str) -> bool:
    """Return True if *expression* is a valid 5-field cron expression."""
    return croniter.is_valid(expression)
