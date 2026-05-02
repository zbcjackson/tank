"""Tests for jobs/cron.py — cron expression validation."""

from __future__ import annotations

from tank_backend.jobs.cron import validate_cron


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
