"""Tests for AppContext and SessionContext."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tank_backend.config.app_config import AppConfig
from tank_backend.config.context import AppContext, SessionContext

MINIMAL_RAW = {
    "llm": {
        "default": {
            "api_key": "test-key",
            "model": "gpt-4",
            "base_url": "https://api.example.com/v1",
        },
    },
}


def _make_app_context(**overrides) -> AppContext:
    defaults = dict(
        app_config=AppConfig.from_raw_dict(MINIMAL_RAW),
        job_store=None,
        scheduler=None,
        conversation_store=None,
    )
    defaults.update(overrides)
    return AppContext(**defaults)


def _make_session_context(**overrides) -> SessionContext:
    defaults = dict(
        app=_make_app_context(),
        bus=MagicMock(),
        llm=MagicMock(),
        tool_manager=MagicMock(),
        approval_policy=MagicMock(),
        pending_store=MagicMock(),
    )
    defaults.update(overrides)
    return SessionContext(**defaults)


class TestAppContext:
    def test_holds_app_config(self):
        ctx = _make_app_context()
        assert ctx.app_config.brain.max_history_tokens == 8000

    def test_is_frozen(self):
        ctx = _make_app_context()
        with pytest.raises(AttributeError):
            ctx.app_config = None

    def test_optional_singletons_default_to_none(self):
        ctx = _make_app_context()
        assert ctx.job_store is None
        assert ctx.scheduler is None
        assert ctx.conversation_store is None

    def test_with_job_store(self):
        store = MagicMock()
        ctx = _make_app_context(job_store=store)
        assert ctx.job_store is store


class TestSessionContext:
    def test_holds_session_objects(self):
        bus = MagicMock()
        llm = MagicMock()
        ctx = _make_session_context(bus=bus, llm=llm)
        assert ctx.bus is bus
        assert ctx.llm is llm

    def test_reaches_app_config_through_parent(self):
        ctx = _make_session_context()
        assert ctx.app.app_config.brain.max_history_tokens == 8000

    def test_is_frozen(self):
        ctx = _make_session_context()
        with pytest.raises(AttributeError):
            ctx.bus = MagicMock()

    def test_different_sessions_share_app_context(self):
        app = _make_app_context()
        s1 = _make_session_context(app=app)
        s2 = _make_session_context(app=app)
        assert s1.app is s2.app

    def test_different_sessions_have_independent_bus(self):
        app = _make_app_context()
        s1 = _make_session_context(app=app, bus=MagicMock())
        s2 = _make_session_context(app=app, bus=MagicMock())
        assert s1.bus is not s2.bus
