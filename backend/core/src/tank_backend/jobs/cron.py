"""Cron expression parsing and next-run calculation."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from croniter import croniter

# Human-friendly schedule patterns → cron expressions
# Each entry: (compiled regex, static result or None, handler tag)
_HUMAN_PATTERNS: list[tuple[re.Pattern[str], str | None, str]] = [
    # "every 30m" / "every 30 minutes"
    (re.compile(r"^every\s+(\d+)\s*m(?:in(?:ute)?s?)?$", re.I), None, "minutes"),
    # "every 2h" / "every 2 hours"
    (re.compile(r"^every\s+(\d+)\s*h(?:ours?)?$", re.I), None, "hours"),
    # "every day at 9am" / "every day at 14:30"
    (re.compile(r"^every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.I), None, "day_at"),
    # "every hour"
    (re.compile(r"^every\s+hour$", re.I), "0 * * * *", "static"),
    # "every day" / "daily"
    (re.compile(r"^(?:every\s+day|daily)$", re.I), "0 0 * * *", "static"),
    # "every week" / "weekly"
    (re.compile(r"^(?:every\s+week|weekly)$", re.I), "0 0 * * 0", "static"),
    # "weekdays at 9am" / "weekdays at 14:30"
    (re.compile(r"^weekdays\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.I), None, "weekdays_at"),
]


def validate_cron(expression: str) -> bool:
    """Return True if *expression* is a valid 5-field cron expression."""
    return croniter.is_valid(expression)


def next_run_time(
    expression: str,
    base_time: datetime | None = None,
) -> datetime:
    """Calculate the next run time from *base_time* (default: now UTC)."""
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    cron = croniter(expression, base_time)
    return cron.get_next(datetime)


def parse_human_schedule(text: str) -> str | None:
    """Convert a human-friendly schedule string to a cron expression.

    Returns ``None`` if the text is not recognised.

    Examples::

        "every 30m"          → "*/30 * * * *"
        "every 2h"           → "0 */2 * * *"
        "every day at 9am"   → "0 9 * * *"
        "every hour"         → "0 * * * *"
        "weekdays at 14:30"  → "30 14 * * 1-5"
    """
    text = text.strip()

    for pattern, static_result, tag in _HUMAN_PATTERNS:
        m = pattern.match(text)
        if m is None:
            continue

        if static_result is not None:
            return static_result

        groups = m.groups()

        if tag == "minutes":
            minutes = int(groups[0])
            if 1 <= minutes <= 59:
                return f"*/{minutes} * * * *"
            return None

        if tag == "hours":
            hours = int(groups[0])
            if 1 <= hours <= 23:
                return f"0 */{hours} * * *"
            return None

        # "every day at ..." / "weekdays at ..."
        hour = int(groups[0])
        minute = int(groups[1]) if groups[1] else 0
        ampm = groups[2]

        if ampm:
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        dow = "1-5" if tag == "weekdays_at" else "*"
        return f"{minute} {hour} * * {dow}"

    return None
