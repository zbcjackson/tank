"""Tests for /api/metrics endpoint."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tank_backend.api import metrics as metrics_module


@pytest.fixture
def mock_session_manager():
    return MagicMock()


@pytest.fixture
def client(mock_session_manager):
    """Create a test client with mocked session manager."""
    from tank_backend.api.server import app

    # Inject mock into the metrics module directly
    metrics_module.set_session_manager(mock_session_manager)
    yield TestClient(app)
    # Reset
    metrics_module._session_manager = None


class TestMetricsAPI:
    def test_get_session_metrics_found(self, client, mock_session_manager) -> None:
        mock_assistant = MagicMock()
        mock_assistant.metrics = {
            "turns": 3,
            "latencies": {
                "end_to_end": {"last": 2.5, "avg": 2.0, "min": 1.5, "max": 2.5, "history": []},
                "asr": {"last": 0.4, "avg": 0.4, "min": 0.4, "max": 0.4, "history": []},
                "llm": {"last": 1.0, "avg": 1.0, "min": 1.0, "max": 1.0, "history": []},
                "tts": {"last": 0.5, "avg": 0.5, "min": 0.5, "max": 0.5, "history": []},
            },
            "echo_discards": 0,
            "interrupts": 1,
            "langfuse_trace_ids": ["trace_1"],
        }
        mock_session_manager.get_assistant.return_value = mock_assistant

        response = client.get("/api/metrics/test-session")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session"
        assert data["turns"] == 3
        assert data["latencies"]["end_to_end"]["last"] == 2.5

    def test_get_session_metrics_not_found(self, client, mock_session_manager) -> None:
        mock_session_manager.get_assistant.return_value = None

        response = client.get("/api/metrics/nonexistent")
        assert response.status_code == 404

    def test_get_all_metrics(self, client, mock_session_manager) -> None:
        mock_assistant_1 = MagicMock()
        mock_assistant_1.metrics = {
            "turns": 2,
            "latencies": {
                "end_to_end": {"last": None, "avg": None, "min": None, "max": None, "history": []},
                "asr": {"last": None, "avg": None, "min": None, "max": None, "history": []},
                "llm": {"last": None, "avg": None, "min": None, "max": None, "history": []},
                "tts": {"last": None, "avg": None, "min": None, "max": None, "history": []},
            },
            "echo_discards": 0,
            "interrupts": 0,
            "langfuse_trace_ids": [],
        }
        mock_session_manager._sessions = {"s1": mock_assistant_1}

        response = client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["active_sessions"] == 1
        assert "s1" in data["sessions"]

    def test_get_all_metrics_empty(self, client, mock_session_manager) -> None:
        mock_session_manager._sessions = {}

        response = client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["active_sessions"] == 0
        assert data["sessions"] == {}
