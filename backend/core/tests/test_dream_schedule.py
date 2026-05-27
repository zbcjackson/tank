"""Tests for Dream Consolidation cron registration in server lifespan."""

from __future__ import annotations

from unittest.mock import MagicMock

from tank_backend.api.server import (
    _dream_consolidation_tick,
    _register_dream_schedule,
)
from tank_backend.config.models import ConsolidationConfig


def _make_config(enabled: bool, schedule: str = "0 3 * * *") -> MagicMock:
    cfg = MagicMock()
    cfg.consolidation = ConsolidationConfig(enabled=enabled, schedule=schedule)
    return cfg


class TestRegisterDreamSchedule:
    def test_no_op_when_disabled(self):
        scheduler = MagicMock()
        cfg = _make_config(enabled=False)

        _register_dream_schedule(scheduler, cfg)

        scheduler.register_recurring.assert_not_called()

    def test_registers_when_enabled(self):
        scheduler = MagicMock()
        cfg = _make_config(enabled=True, schedule="*/15 * * * *")

        _register_dream_schedule(scheduler, cfg)

        scheduler.register_recurring.assert_called_once()
        call = scheduler.register_recurring.call_args
        assert call.kwargs["schedule_id"] == "tank_dream_consolidation"
        assert call.kwargs["cron"] == "*/15 * * * *"

    def test_callback_is_module_level_for_apscheduler(self):
        """APScheduler refuses nested functions — the registered callback
        must be a module-level reference (a ``functools.partial`` wrapping
        the module-level tick)."""
        import functools

        scheduler = MagicMock()
        cfg = _make_config(enabled=True)

        _register_dream_schedule(scheduler, cfg)

        callback = scheduler.register_recurring.call_args.kwargs["callback"]
        assert isinstance(callback, functools.partial)
        assert callback.func is _dream_consolidation_tick
