"""Tests for the enhanced /health endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from tank_backend.api.server import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_basic(self):
        """GET /health returns 200 with status ok (backward compatible)."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_no_detail_ignores_sessions(self):
        """GET /health without detail=true should not iterate sessions."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" not in data

    @patch("tank_backend.api.server.session_manager")
    def test_health_detail_no_sessions(self, mock_sm):
        """GET /health?detail=true with no sessions returns healthy."""
        mock_sm.iter_sessions.return_value = iter([])
        response = client.get("/health?detail=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["sessions"] == {}

    @patch("tank_backend.api.server.session_manager")
    def test_health_detail_healthy_session(self, mock_sm):
        """GET /health?detail=true with a healthy session returns 200."""
        mock_assistant = MagicMock()
        mock_assistant.health_snapshot.return_value = {
            "pipeline": {"running": True, "is_healthy": True, "queues": [], "processors": []},
        }
        mock_sm.iter_sessions.return_value = iter([("session-1", mock_assistant)])

        response = client.get("/health?detail=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "session-1" in data["sessions"]

    @patch("tank_backend.api.server.session_manager")
    def test_health_detail_unhealthy_session(self, mock_sm):
        """GET /health?detail=true with an unhealthy session returns 503."""
        mock_assistant = MagicMock()
        mock_assistant.health_snapshot.return_value = {
            "pipeline": {
                "running": True,
                "is_healthy": False,
                "queues": [
                    {
                        "name": "q_0_vad",
                        "size": 10,
                        "maxsize": 10,
                        "is_stuck": True,
                        "consumer_alive": True,
                    }
                ],
                "processors": [],
            },
        }
        mock_sm.iter_sessions.return_value = iter([("session-1", mock_assistant)])

        response = client.get("/health?detail=true")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"

    @patch("tank_backend.api.server.session_manager")
    def test_health_detail_mixed_sessions(self, mock_sm):
        """Multiple sessions: one healthy + one unhealthy = degraded."""
        healthy_asst = MagicMock()
        healthy_asst.health_snapshot.return_value = {
            "pipeline": {"running": True, "is_healthy": True},
        }
        unhealthy_asst = MagicMock()
        unhealthy_asst.health_snapshot.return_value = {
            "pipeline": {"running": True, "is_healthy": False},
        }
        mock_sm.iter_sessions.return_value = iter([
            ("s1", healthy_asst),
            ("s2", unhealthy_asst),
        ])

        response = client.get("/health?detail=true")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"

    @patch("tank_backend.api.server.session_manager")
    def test_health_detail_no_pipeline(self, mock_sm):
        """Session with no pipeline (not started yet) is considered healthy."""
        mock_assistant = MagicMock()
        mock_assistant.health_snapshot.return_value = {"pipeline": None}
        mock_sm.iter_sessions.return_value = iter([("session-1", mock_assistant)])

        response = client.get("/health?detail=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
