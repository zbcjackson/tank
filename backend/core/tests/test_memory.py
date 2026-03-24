"""Tests for the MemoryService wrapper around mem0."""

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.memory.config import MemoryConfig
from tank_backend.memory.service import MemoryService


class TestMemoryConfig:
    """Unit tests for MemoryConfig."""

    def test_defaults(self):
        cfg = MemoryConfig()
        assert cfg.enabled is False
        assert cfg.db_path == "../data/memory"
        assert cfg.llm_api_key == ""
        assert cfg.llm_base_url == ""
        assert cfg.llm_model == ""
        assert cfg.search_limit == 5

    def test_from_dict_full(self):
        raw = {
            "enabled": True,
            "db_path": "/tmp/mem",
            "llm_api_key": "sk-test",
            "llm_base_url": "https://example.com/v1",
            "llm_model": "gpt-4.1-nano",
            "search_limit": 10,
        }
        cfg = MemoryConfig.from_dict(raw)
        assert cfg.enabled is True
        assert cfg.db_path == "/tmp/mem"
        assert cfg.llm_api_key == "sk-test"
        assert cfg.llm_base_url == "https://example.com/v1"
        assert cfg.llm_model == "gpt-4.1-nano"
        assert cfg.search_limit == 10

    def test_from_dict_ignores_unknown_keys(self):
        raw = {"enabled": True, "unknown_key": "value"}
        cfg = MemoryConfig.from_dict(raw)
        assert cfg.enabled is True

    def test_from_dict_defaults(self):
        cfg = MemoryConfig.from_dict({})
        assert cfg.enabled is False
        assert cfg.search_limit == 5

    def test_frozen(self):
        cfg = MemoryConfig()
        with pytest.raises(AttributeError):
            cfg.enabled = True  # type: ignore[misc]


MODULE = "tank_backend.memory.service"


class TestMemoryService:
    """Unit tests for MemoryService (mem0 calls mocked)."""

    @pytest.fixture
    def config(self):
        return MemoryConfig(
            enabled=True,
            db_path="/tmp/test_memory",
            llm_api_key="sk-test",
            llm_base_url="https://example.com/v1",
            llm_model="gpt-4.1-nano",
            search_limit=3,
        )

    @pytest.fixture
    def mock_mem0(self):
        """Patch mem0.Memory.from_config to return a mock Memory instance."""
        mock_memory = MagicMock()
        mock_memory.add = MagicMock()
        mock_memory.search = MagicMock(return_value={"results": []})
        mock_memory.get_all = MagicMock(return_value={"results": []})
        return mock_memory

    @pytest.fixture
    def service(self, config, mock_mem0):
        with patch("mem0.Memory") as mock_mem0_cls:
            mock_mem0_cls.from_config.return_value = mock_mem0
            svc = MemoryService(config)
        # Overwrite the _mem with our mock (in case from_config path differs)
        svc._mem = mock_mem0
        return svc

    async def test_store_turn_calls_mem0_add(self, service, mock_mem0):
        await service.store_turn("jackson", "What's the weather?", "It's sunny today.")

        mock_mem0.add.assert_called_once()
        call_args = mock_mem0.add.call_args
        messages = call_args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert call_args[1]["user_id"] == "jackson"

    async def test_recall_returns_memory_strings(self, service, mock_mem0):
        mock_mem0.search.return_value = {
            "results": [
                {"memory": "Likes coffee", "id": "1"},
                {"memory": "Works in tech", "id": "2"},
            ]
        }

        result = await service.recall("jackson", "What do I like?")

        assert result == ["Likes coffee", "Works in tech"]
        mock_mem0.search.assert_called_once()
        assert mock_mem0.search.call_args[1]["user_id"] == "jackson"
        assert mock_mem0.search.call_args[1]["limit"] == 3

    async def test_recall_returns_empty_for_no_results(self, service, mock_mem0):
        mock_mem0.search.return_value = {"results": []}
        result = await service.recall("jackson", "anything")
        assert result == []

    async def test_recall_filters_empty_memories(self, service, mock_mem0):
        mock_mem0.search.return_value = {
            "results": [
                {"memory": "Valid fact", "id": "1"},
                {"memory": "", "id": "2"},
                {"id": "3"},  # no "memory" key
            ]
        }
        result = await service.recall("jackson", "query")
        assert result == ["Valid fact"]

    async def test_recall_respects_custom_limit(self, service, mock_mem0):
        mock_mem0.search.return_value = {"results": []}
        await service.recall("jackson", "query", limit=10)
        assert mock_mem0.search.call_args[1]["limit"] == 10

    async def test_get_all_returns_all_memories(self, service, mock_mem0):
        mock_mem0.get_all.return_value = {
            "results": [
                {"memory": "Fact 1", "id": "1"},
                {"memory": "Fact 2", "id": "2"},
            ]
        }
        result = await service.get_all("jackson")
        assert result == ["Fact 1", "Fact 2"]

    async def test_store_turn_error_propagates(self, service, mock_mem0):
        """Store errors should propagate (Brain wraps in try/except)."""
        mock_mem0.add.side_effect = RuntimeError("mem0 down")
        with pytest.raises(RuntimeError, match="mem0 down"):
            await service.store_turn("jackson", "hello", "hi there")

    async def test_recall_error_propagates(self, service, mock_mem0):
        """Recall errors should propagate (Brain wraps in try/except)."""
        mock_mem0.search.side_effect = RuntimeError("search failed")
        with pytest.raises(RuntimeError, match="search failed"):
            await service.recall("jackson", "query")
