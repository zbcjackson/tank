"""ORM-backed speaker repository.

Delegates all I/O to a shared :class:`Database`. Maintains the
``SpeakerRepository`` contract so :class:`VoiceprintRecognizer` is
agnostic to the storage backend.
"""

from __future__ import annotations

import logging
import time

import numpy as np
from sqlalchemy import select

from ...persistence import Database
from ...persistence.models import EmbeddingRow, SpeakerRow
from .repository import Speaker, SpeakerRepository

logger = logging.getLogger("SQLiteSpeakerRepo")


class SQLiteSpeakerRepository(SpeakerRepository):
    """Speaker storage backed by the unified Tank database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def add_speaker(self, user_id: str, name: str, embedding: np.ndarray) -> None:
        now = time.time()
        blob = embedding.astype(np.float32).tobytes()
        with self._db.session() as s:
            existing = s.get(SpeakerRow, user_id)
            if existing is None:
                s.add(SpeakerRow(
                    user_id=user_id, name=name, created_at=now, updated_at=now,
                ))
                # Flush so the FK target exists before the embedding insert.
                s.flush()
            else:
                existing.name = name
                existing.updated_at = now
            s.add(EmbeddingRow(user_id=user_id, embedding=blob, created_at=now))
        logger.info("Added embedding for speaker: %s (%s)", user_id, name)

    def get_speaker(self, user_id: str) -> Speaker | None:
        with self._db.session() as s:
            row = s.get(SpeakerRow, user_id)
            if row is None:
                return None
            embs = s.execute(
                select(EmbeddingRow.embedding).where(EmbeddingRow.user_id == user_id)
            ).scalars().all()
            return Speaker(
                user_id=row.user_id,
                name=row.name,
                embeddings=[np.frombuffer(e, dtype=np.float32) for e in embs],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_speakers(self) -> list[Speaker]:
        with self._db.session() as s:
            speaker_rows = s.execute(
                select(SpeakerRow).order_by(SpeakerRow.user_id)
            ).scalars().all()
            if not speaker_rows:
                return []
            emb_rows = s.execute(
                select(EmbeddingRow.user_id, EmbeddingRow.embedding)
            ).all()

        by_user: dict[str, list[np.ndarray]] = {}
        for uid, blob in emb_rows:
            by_user.setdefault(uid, []).append(np.frombuffer(blob, dtype=np.float32))

        return [
            Speaker(
                user_id=r.user_id,
                name=r.name,
                embeddings=by_user.get(r.user_id, []),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in speaker_rows
        ]

    def delete_speaker(self, user_id: str) -> bool:
        with self._db.session() as s:
            existing = s.get(SpeakerRow, user_id)
            if existing is None:
                return False
            s.delete(existing)
        logger.info("Deleted speaker: %s", user_id)
        return True

    def identify(self, embedding: np.ndarray, threshold: float = 0.6) -> str | None:
        speakers = self.list_speakers()
        if not speakers:
            return None

        best_score = -1.0
        best_user_id: str | None = None
        for speaker in speakers:
            for stored in speaker.embeddings:
                score = self._cosine_similarity(embedding, stored)
                if score > best_score:
                    best_score = score
                    best_user_id = speaker.user_id

        if best_score >= threshold:
            logger.debug("Identified speaker: %s (score=%.3f)", best_user_id, best_score)
            return best_user_id
        logger.debug("No match above threshold (best=%.3f)", best_score)
        return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def close(self) -> None:
        """No-op: the Database owns the engine lifecycle."""
        return
