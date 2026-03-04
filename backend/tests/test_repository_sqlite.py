"""Tests for SQLite speaker repository."""

from __future__ import annotations

import numpy as np
import pytest

from tank_backend.audio.input.repository_sqlite import SQLiteSpeakerRepository


@pytest.fixture
def repository():
    """Create in-memory SQLite repository for testing."""
    repo = SQLiteSpeakerRepository(db_path=":memory:")
    yield repo
    repo.close()


@pytest.fixture
def sample_embedding():
    """Create a sample embedding vector."""
    return np.random.randn(192).astype(np.float32)


def test_repository_init(tmp_path):
    """Test repository initialization."""
    db_path = tmp_path / "test.db"
    repo = SQLiteSpeakerRepository(str(db_path))

    assert db_path.exists()
    repo.close()


def test_add_speaker(repository, sample_embedding):
    """Test adding a new speaker."""
    repository.add_speaker("alice", "Alice", sample_embedding)

    speaker = repository.get_speaker("alice")
    assert speaker is not None
    assert speaker.user_id == "alice"
    assert speaker.name == "Alice"
    assert len(speaker.embeddings) == 1
    assert np.allclose(speaker.embeddings[0], sample_embedding)


def test_add_multiple_embeddings_for_same_speaker(repository, sample_embedding):
    """Test adding multiple embeddings for the same speaker."""
    embedding1 = sample_embedding
    embedding2 = np.random.randn(192).astype(np.float32)

    repository.add_speaker("alice", "Alice", embedding1)
    repository.add_speaker("alice", "Alice", embedding2)

    speaker = repository.get_speaker("alice")
    assert speaker is not None
    assert len(speaker.embeddings) == 2
    assert np.allclose(speaker.embeddings[0], embedding1)
    assert np.allclose(speaker.embeddings[1], embedding2)


def test_update_speaker_name(repository, sample_embedding):
    """Test updating speaker name."""
    repository.add_speaker("alice", "Alice", sample_embedding)
    repository.add_speaker("alice", "Alice Smith", sample_embedding)

    speaker = repository.get_speaker("alice")
    assert speaker.name == "Alice Smith"


def test_get_speaker_not_found(repository):
    """Test getting non-existent speaker."""
    speaker = repository.get_speaker("nonexistent")
    assert speaker is None


def test_list_speakers(repository):
    """Test listing all speakers."""
    embedding1 = np.random.randn(192).astype(np.float32)
    embedding2 = np.random.randn(192).astype(np.float32)

    repository.add_speaker("alice", "Alice", embedding1)
    repository.add_speaker("bob", "Bob", embedding2)

    speakers = repository.list_speakers()
    assert len(speakers) == 2

    user_ids = {s.user_id for s in speakers}
    assert user_ids == {"alice", "bob"}


def test_list_speakers_empty(repository):
    """Test listing speakers when repository is empty."""
    speakers = repository.list_speakers()
    assert speakers == []


def test_delete_speaker(repository, sample_embedding):
    """Test deleting a speaker."""
    repository.add_speaker("alice", "Alice", sample_embedding)

    deleted = repository.delete_speaker("alice")
    assert deleted is True

    speaker = repository.get_speaker("alice")
    assert speaker is None


def test_delete_speaker_not_found(repository):
    """Test deleting non-existent speaker."""
    deleted = repository.delete_speaker("nonexistent")
    assert deleted is False


def test_delete_speaker_cascades_embeddings(repository, sample_embedding):
    """Test that deleting speaker also deletes embeddings."""
    repository.add_speaker("alice", "Alice", sample_embedding)
    repository.add_speaker("alice", "Alice", sample_embedding)

    repository.delete_speaker("alice")

    # Verify speaker and embeddings are gone
    speaker = repository.get_speaker("alice")
    assert speaker is None


def test_identify_exact_match(repository):
    """Test identifying speaker with exact embedding match."""
    embedding = np.random.randn(192).astype(np.float32)
    repository.add_speaker("alice", "Alice", embedding)

    # Identify with same embedding
    user_id = repository.identify(embedding, threshold=0.99)
    assert user_id == "alice"


def test_identify_similar_match(repository):
    """Test identifying speaker with similar embedding."""
    embedding = np.random.randn(192).astype(np.float32)
    repository.add_speaker("alice", "Alice", embedding)

    # Create slightly perturbed embedding
    similar = embedding + np.random.randn(192).astype(np.float32) * 0.1
    similar = similar / np.linalg.norm(similar) * np.linalg.norm(embedding)

    user_id = repository.identify(similar, threshold=0.6)
    assert user_id == "alice"


def test_identify_no_match_below_threshold(repository):
    """Test that identification fails when similarity is below threshold."""
    embedding1 = np.random.randn(192).astype(np.float32)
    embedding2 = np.random.randn(192).astype(np.float32)

    repository.add_speaker("alice", "Alice", embedding1)

    # Different embedding should not match with high threshold
    user_id = repository.identify(embedding2, threshold=0.9)
    assert user_id is None


def test_identify_empty_repository(repository):
    """Test identification when repository is empty."""
    embedding = np.random.randn(192).astype(np.float32)
    user_id = repository.identify(embedding, threshold=0.6)
    assert user_id is None


def test_identify_best_match_among_multiple_speakers(repository):
    """Test that identification returns best match among multiple speakers."""
    # Create embeddings
    embedding_alice = np.random.randn(192).astype(np.float32)
    embedding_bob = np.random.randn(192).astype(np.float32)

    repository.add_speaker("alice", "Alice", embedding_alice)
    repository.add_speaker("bob", "Bob", embedding_bob)

    # Query should match Alice better
    query = embedding_alice + np.random.randn(192).astype(np.float32) * 0.05
    user_id = repository.identify(query, threshold=0.5)
    assert user_id == "alice"


def test_identify_with_multiple_embeddings_per_speaker(repository):
    """Test identification when speaker has multiple embeddings."""
    embedding1 = np.random.randn(192).astype(np.float32)
    embedding2 = np.random.randn(192).astype(np.float32)

    repository.add_speaker("alice", "Alice", embedding1)
    repository.add_speaker("alice", "Alice", embedding2)

    # Query similar to embedding2
    query = embedding2 + np.random.randn(192).astype(np.float32) * 0.05
    user_id = repository.identify(query, threshold=0.6)
    assert user_id == "alice"


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    # Identical vectors
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    similarity = SQLiteSpeakerRepository._cosine_similarity(a, b)
    assert np.isclose(similarity, 1.0)

    # Orthogonal vectors
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    similarity = SQLiteSpeakerRepository._cosine_similarity(a, b)
    assert np.isclose(similarity, 0.0)

    # Opposite vectors
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    similarity = SQLiteSpeakerRepository._cosine_similarity(a, b)
    assert np.isclose(similarity, -1.0)


def test_speaker_timestamps(repository, sample_embedding):
    """Test that timestamps are recorded correctly."""
    import time

    before = time.time()
    repository.add_speaker("alice", "Alice", sample_embedding)
    after = time.time()

    speaker = repository.get_speaker("alice")
    assert speaker.created_at >= before
    assert speaker.created_at <= after
    assert speaker.updated_at >= before
    assert speaker.updated_at <= after


def test_speaker_updated_at_changes(repository, sample_embedding):
    """Test that updated_at changes when adding new embedding."""
    import time

    repository.add_speaker("alice", "Alice", sample_embedding)
    speaker1 = repository.get_speaker("alice")

    time.sleep(0.01)  # Small delay to ensure timestamp difference

    repository.add_speaker("alice", "Alice", sample_embedding)
    speaker2 = repository.get_speaker("alice")

    assert speaker2.updated_at > speaker1.updated_at
