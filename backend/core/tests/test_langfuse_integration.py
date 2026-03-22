"""Tests for Langfuse integration — conditional import and graceful fallback."""

import os
from unittest.mock import patch

from tank_backend.observability import langfuse_client


class TestLangfuseEnabled:
    def setup_method(self) -> None:
        langfuse_client.reset()

    def teardown_method(self) -> None:
        langfuse_client.reset()

    def test_not_enabled_without_env_vars(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            assert langfuse_client.is_langfuse_enabled() is False

    def test_enabled_with_env_vars(self) -> None:
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
        }):
            assert langfuse_client.is_langfuse_enabled() is True

    def test_not_enabled_with_partial_env_vars(self) -> None:
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-test"}, clear=True):
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            assert langfuse_client.is_langfuse_enabled() is False

    def test_get_langfuse_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            langfuse_client.reset()
            result = langfuse_client.get_langfuse()
            assert result is None

    def test_initialize_langfuse_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            langfuse_client.reset()
            result = langfuse_client.initialize_langfuse()
            assert result is None

    def test_initialize_langfuse_idempotent(self) -> None:
        """Calling initialize_langfuse twice returns the same result."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            langfuse_client.reset()
            r1 = langfuse_client.initialize_langfuse()
            r2 = langfuse_client.initialize_langfuse()
            assert r1 is r2

    def test_reset_allows_reinitialization(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            langfuse_client.reset()
            assert langfuse_client.get_langfuse() is None

        langfuse_client.reset()
        assert langfuse_client._initialized is False


class TestTraceId:
    def test_generate_trace_id_format(self) -> None:
        from tank_backend.observability.trace import generate_trace_id

        trace_id = generate_trace_id("session_abc")
        assert trace_id.startswith("session_abc_")
        suffix = trace_id.split("_", 2)[-1]
        assert len(suffix) == 8

    def test_generate_trace_id_unique(self) -> None:
        from tank_backend.observability.trace import generate_trace_id

        ids = {generate_trace_id("s1") for _ in range(100)}
        assert len(ids) == 100
