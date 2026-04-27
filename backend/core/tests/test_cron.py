"""Tests for jobs/cron.py — cron expression parsing and human schedule conversion."""

from __future__ import annotations

from tank_backend.jobs.cron import parse_human_schedule, validate_cron


class TestValidateCron:
    def test_valid_expressions(self):
        assert validate_cron("0 9 * * *") is True
        assert validate_cron("*/5 * * * *") is True
        assert validate_cron("0 0 1 * *") is True
        assert validate_cron("30 14 * * 1-5") is True

    def test_invalid_expressions(self):
        assert validate_cron("not a cron") is False
        assert validate_cron("") is False
        assert validate_cron("60 * * * *") is False  # minute > 59


class TestParseHumanSchedule:
    def test_every_minutes(self):
        assert parse_human_schedule("every 30m") == "*/30 * * * *"
        assert parse_human_schedule("every 5 minutes") == "*/5 * * * *"
        assert parse_human_schedule("every 15min") == "*/15 * * * *"

    def test_every_hours(self):
        assert parse_human_schedule("every 2h") == "0 */2 * * *"
        assert parse_human_schedule("every 1 hour") == "0 */1 * * *"

    def test_every_hour(self):
        assert parse_human_schedule("every hour") == "0 * * * *"

    def test_every_day(self):
        assert parse_human_schedule("every day") == "0 0 * * *"
        assert parse_human_schedule("daily") == "0 0 * * *"

    def test_every_week(self):
        assert parse_human_schedule("every week") == "0 0 * * 0"
        assert parse_human_schedule("weekly") == "0 0 * * 0"

    def test_every_day_at_time(self):
        assert parse_human_schedule("every day at 9am") == "0 9 * * *"
        assert parse_human_schedule("every day at 2pm") == "0 14 * * *"
        assert parse_human_schedule("every day at 14:30") == "30 14 * * *"
        assert parse_human_schedule("every day at 12am") == "0 0 * * *"
        assert parse_human_schedule("every day at 12pm") == "0 12 * * *"

    def test_weekdays_at_time(self):
        assert parse_human_schedule("weekdays at 9am") == "0 9 * * 1-5"
        assert parse_human_schedule("weekdays at 14:30") == "30 14 * * 1-5"

    def test_unrecognized(self):
        assert parse_human_schedule("something random") is None
        assert parse_human_schedule("") is None

    def test_case_insensitive(self):
        assert parse_human_schedule("Every Day At 9AM") == "0 9 * * *"
        assert parse_human_schedule("EVERY HOUR") == "0 * * * *"

    def test_invalid_ranges(self):
        assert parse_human_schedule("every 0m") is None
        assert parse_human_schedule("every 60m") is None
        assert parse_human_schedule("every 0h") is None
        assert parse_human_schedule("every 24h") is None
