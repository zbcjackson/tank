"""Tests for users.manager — UserManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from tank_backend.users.manager import User, UserManager


def _make_speaker(user_id: str, name: str, n_embeddings: int = 1) -> MagicMock:
    """Create a mock Speaker object matching the real dataclass shape."""
    speaker = MagicMock()
    speaker.user_id = user_id
    speaker.name = name
    speaker.embeddings = [np.zeros(192, dtype=np.float32)] * n_embeddings
    speaker.created_at = 1000000.0
    speaker.updated_at = 1000001.0
    return speaker


@pytest.fixture()
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.list_speakers.return_value = []
    repo.get_speaker.return_value = None
    repo.delete_speaker.return_value = False
    return repo


@pytest.fixture()
def manager(mock_repo: MagicMock, tmp_path: Path) -> UserManager:
    return UserManager(mock_repo, tmp_path)


class TestListUsers:
    def test_empty(self, manager: UserManager):
        assert manager.list_users() == []

    def test_returns_sorted(self, manager: UserManager, mock_repo: MagicMock):
        mock_repo.list_speakers.return_value = [
            _make_speaker("id1", "Charlie"),
            _make_speaker("id2", "Alice", n_embeddings=3),
            _make_speaker("id3", "Bob"),
        ]
        users = manager.list_users()
        assert [u.name for u in users] == ["Alice", "Bob", "Charlie"]
        assert users[0].sample_count == 3

    def test_none_repo(self, tmp_path: Path):
        mgr = UserManager(None, tmp_path)
        assert mgr.list_users() == []


class TestGetUser:
    def test_found(self, manager: UserManager, mock_repo: MagicMock):
        mock_repo.get_speaker.return_value = _make_speaker("abc", "Alice", n_embeddings=2)
        user = manager.get_user("abc")
        assert user is not None
        assert user.user_id == "abc"
        assert user.name == "Alice"
        assert user.sample_count == 2
        mock_repo.get_speaker.assert_called_once_with("abc")

    def test_not_found(self, manager: UserManager):
        assert manager.get_user("nonexistent") is None

    def test_none_repo(self, tmp_path: Path):
        mgr = UserManager(None, tmp_path)
        assert mgr.get_user("abc") is None


class TestResolveName:
    def test_found(self, manager: UserManager, mock_repo: MagicMock):
        mock_repo.get_speaker.return_value = _make_speaker("abc", "Alice")
        assert manager.resolve_name("abc") == "Alice"

    def test_not_found(self, manager: UserManager):
        assert manager.resolve_name("nonexistent") == "Guest"

    def test_none_repo(self, tmp_path: Path):
        mgr = UserManager(None, tmp_path)
        assert mgr.resolve_name("abc") == "Guest"


class TestDeleteUser:
    def test_deletes_speaker_and_folder(
        self, manager: UserManager, mock_repo: MagicMock, tmp_path: Path
    ):
        mock_repo.delete_speaker.return_value = True
        # Create a user folder
        user_dir = tmp_path / "abc123"
        user_dir.mkdir()
        (user_dir / "preferences.md").write_text("- Some pref")

        assert manager.delete_user("abc123") is True
        mock_repo.delete_speaker.assert_called_once_with("abc123")
        assert not user_dir.exists()

    def test_deletes_speaker_no_folder(self, manager: UserManager, mock_repo: MagicMock):
        mock_repo.delete_speaker.return_value = True
        assert manager.delete_user("abc123") is True

    def test_speaker_not_found(self, manager: UserManager):
        assert manager.delete_user("nonexistent") is False

    def test_none_repo(self, tmp_path: Path):
        mgr = UserManager(None, tmp_path)
        assert mgr.delete_user("abc") is False


class TestUserDir:
    def test_returns_path(self, manager: UserManager, tmp_path: Path):
        path = manager.user_dir("abc123")
        assert path == tmp_path / "abc123"

    def test_path_may_not_exist(self, manager: UserManager):
        path = manager.user_dir("nonexistent")
        assert not path.exists()


class TestUserDataclass:
    def test_frozen(self):
        user = User(user_id="abc", name="Alice", sample_count=1, created_at=0.0, updated_at=0.0)
        with pytest.raises(AttributeError):
            user.name = "Bob"  # type: ignore[misc]
