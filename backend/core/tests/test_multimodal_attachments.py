"""Integration tests for multi-modal attachment flow.

These tests exercise the Phase 2 glue: the capability-gated upload
endpoint, the attachment parser at the WebSocket boundary, and the
materialization step in ContextManager. They stop short of hitting a
real LLM — the assertion target is the *shape* of the message list
handed to the LLM, not a round-trip.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tank_backend.api.router import _parse_attachments
from tank_backend.core.content import (
    DocumentBlock,
    ImageBlock,
    modality_for_mime,
)
from tank_backend.media import MediaStore

# ---------------------------------------------------------------------------
# MIME → modality classification
# ---------------------------------------------------------------------------


class TestModalityForMime:
    @pytest.mark.parametrize(
        ("mime", "expected"),
        [
            ("image/png", "image"),
            ("image/jpeg", "image"),
            ("image/webp", "image"),
            ("image/gif", "image"),
            ("audio/wav", "audio"),
            ("audio/mp3", "audio"),
            ("audio/ogg", "audio"),
            ("video/mp4", "video"),
            ("video/webm", "video"),
            ("text/plain", "text"),
            ("text/markdown", "text"),
            ("application/pdf", "file"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # noqa: E501
                "file",
            ),
        ],
    )
    def test_known_mime(self, mime, expected):
        assert modality_for_mime(mime) == expected

    def test_unknown_mime_returns_none(self):
        assert modality_for_mime("application/x-weird") is None
        assert modality_for_mime("") is None

    def test_charset_param_stripped(self):
        assert modality_for_mime("text/plain; charset=utf-8") == "text"


# ---------------------------------------------------------------------------
# WebSocket attachment parser
# ---------------------------------------------------------------------------


class TestParseAttachments:
    def test_image_attachment_builds_image_block(self):
        blocks = _parse_attachments(
            [{"media_uri": "media://sess-1/abc.png", "mime_type": "image/png"}],
            session_id="sess-1",
        )
        assert len(blocks) == 1
        assert isinstance(blocks[0], ImageBlock)
        assert blocks[0].source == "media://sess-1/abc.png"
        assert blocks[0].mime_type == "image/png"

    def test_pdf_attachment_builds_document_block(self):
        blocks = _parse_attachments(
            [{
                "media_uri": "media://sess-1/x.pdf",
                "mime_type": "application/pdf",
            }],
            session_id="sess-1",
        )
        assert len(blocks) == 1
        assert isinstance(blocks[0], DocumentBlock)
        assert blocks[0].mime_type == "application/pdf"

    def test_cross_session_attachment_dropped(self):
        blocks = _parse_attachments(
            [{"media_uri": "media://other-sess/x.png", "mime_type": "image/png"}],
            session_id="sess-1",
        )
        assert blocks == []

    def test_non_dict_entry_dropped(self):
        blocks = _parse_attachments(
            ["not-a-dict", {"media_uri": "media://s/x.png", "mime_type": "image/png"}],
            session_id="s",
        )
        assert len(blocks) == 1

    def test_missing_fields_dropped(self):
        blocks = _parse_attachments(
            [
                {"media_uri": "media://s/x.png"},  # no mime_type
                {"mime_type": "image/png"},         # no uri
                {},                                  # empty
            ],
            session_id="s",
        )
        assert blocks == []

    def test_audio_modality_not_yet_carried(self):
        """Phase 2 scope is images+docs on user input. Audio attachments
        on the user turn are dropped with an info log — Phase 5 enables them.
        """
        blocks = _parse_attachments(
            [{"media_uri": "media://s/x.wav", "mime_type": "audio/wav"}],
            session_id="s",
        )
        assert blocks == []

    def test_unknown_mime_dropped(self):
        blocks = _parse_attachments(
            [{"media_uri": "media://s/x.bin", "mime_type": "application/x-weird"}],
            session_id="s",
        )
        assert blocks == []


# ---------------------------------------------------------------------------
# ContextManager materialization (unit level)
# ---------------------------------------------------------------------------


class TestContextManagerMaterialization:
    """prepare_turn turns attachments into OpenAI content parts.

    The manager is real; the media store is real (points at tmp_path);
    only the upstream bits (memory service, summarizer, skill provider)
    are stubbed out so we can isolate the materialization logic.
    """

    @pytest.fixture()
    def app_config(self):
        """A minimal config good enough to satisfy ContextManager."""

        class _Cfg:
            # ContextManager only reads a handful of attributes — stub
            # just those, keep the rest AttributeError-raisy so we see
            # if something else starts depending on the config.
            memory = type("M", (), {"enabled": False})()
            preferences = type("P", (), {"enabled": False})()

            def get_llm_profile(self, _name):
                from tank_backend.llm.profile import LLMProfile
                return LLMProfile(
                    name="default",
                    api_key="x",
                    model="gpt-4o",
                    base_url="https://api.openai.com/v1",
                )

            def is_feature_enabled(self, _name):
                return False

        return _Cfg()

    @pytest.fixture()
    def media_store(self, tmp_path):
        return MediaStore(tmp_path / "media")

    @pytest.fixture()
    def context_manager(self, app_config, media_store):
        from datetime import datetime, timezone

        from tank_backend.config.models import ContextConfig
        from tank_backend.context.conversation import ConversationData
        from tank_backend.context.manager import ContextManager

        mgr = ContextManager(
            app_config=app_config,
            resolver=None,
            bus=None,
            config=ContextConfig(max_history_tokens=0),
            media_store=media_store,
        )
        # Seed with an empty conversation so prepare_turn has something
        # to append to. Using a bare dict-backed conversation skips the
        # full resolver machinery.
        mgr._conversation = ConversationData(
            id="test-conv",
            start_time=datetime.now(timezone.utc),
            pid=0,
            messages=[{"role": "system", "content": "You are a test."}],
        )
        # Disable persistence — no resolver means _persist has to be a no-op.
        mgr._persist = lambda: None  # type: ignore[method-assign]
        return mgr

    @pytest.mark.asyncio()
    async def test_text_only_turn_unchanged(self, context_manager):
        messages = await context_manager.prepare_turn("alice", "hello")
        # Last message should be the user turn with string content.
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "hello"

    @pytest.mark.asyncio()
    async def test_image_attachment_produces_content_parts(
        self, context_manager, media_store,
    ):
        png = b"\x89PNG\r\n\x1a\n" + b"x" * 16
        stored = await media_store.put(png, "image/png", session_id="sess")
        block = ImageBlock(source=stored.media_uri, mime_type="image/png")

        messages = await context_manager.prepare_turn(
            "alice", "what's in this image?", attachments=[block],
        )
        # User message's wire content is now a list of parts.
        user_msg = messages[-1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)
        # Expect: [text, image_url]
        types = [p["type"] for p in user_msg["content"]]
        assert types == ["text", "image_url"]
        # Image URL was materialized to a data URL.
        assert user_msg["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )

    @pytest.mark.asyncio()
    async def test_persisted_message_keeps_text_only(
        self, context_manager, media_store,
    ):
        """The stored message must remain plain-text for token counting
        and future replay — only the wire message gets the parts form.
        """
        png = b"\x89PNG" + b"y" * 32
        stored = await media_store.put(png, "image/png", session_id="s")
        block = ImageBlock(source=stored.media_uri, mime_type="image/png")

        await context_manager.prepare_turn(
            "bob", "describe it", attachments=[block],
        )

        persisted = context_manager._conversation.messages[-1]
        assert persisted["role"] == "user"
        assert persisted["content"] == "describe it"  # plain text retained
        # And the attachments ride alongside as serialized dicts.
        assert persisted["attachments"][0]["type"] == "image"
        assert persisted["attachments"][0]["source"].startswith("media://")

    @pytest.mark.asyncio()
    async def test_pdf_document_with_extracted_text(
        self, context_manager, media_store,
    ):
        pdf_bytes = b"%PDF-fake"
        stored = await media_store.put(
            pdf_bytes, "application/pdf", session_id="s",
        )
        doc = DocumentBlock(
            source=stored.media_uri,
            mime_type="application/pdf",
            extracted_text="Doc body here",
        )

        messages = await context_manager.prepare_turn(
            "charlie", "summarise", attachments=[doc],
        )
        user_msg = messages[-1]
        assert isinstance(user_msg["content"], list)
        # Text-heavy doc: the extracted text merges into the prefix text part.
        text_part = next(
            p for p in user_msg["content"] if p["type"] == "text"
        )
        assert "summarise" in text_part["text"]
        assert "Doc body here" in text_part["text"]


# ---------------------------------------------------------------------------
# Upload endpoint (HTTP-level)
# ---------------------------------------------------------------------------


class TestUploadEndpoint:
    """End-to-end sanity checks for POST /api/upload via FastAPI TestClient.

    Import of server.py pulls in real dependencies (sqlite bootstrap,
    plugin manager, etc), so we skip this class when those can't run.
    """

    @pytest.fixture()
    def client(self, monkeypatch, tmp_path):
        """Spin up the FastAPI app against an isolated config/home.

        Requires a full server bootstrap. When that fails (missing
        config, missing plugin, etc) the fixture aborts with skip().
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        try:
            from fastapi.testclient import TestClient

            import tank_backend.api.server as server_mod
        except Exception as exc:
            pytest.skip(f"Cannot bootstrap server: {exc}")
        return TestClient(server_mod.app)

    def test_reject_unsupported_mime(self, client, tmp_path):
        # A model that supports image only would reject audio/wav. We
        # patch the exact symbol the handler imports locally.
        from tank_backend.llm.capabilities import (
            CapabilitySource,
            ModelCapabilities,
        )

        forced = ModelCapabilities(
            model_id="gpt-4o",
            input_modalities=frozenset({"text", "image"}),
            source=CapabilitySource.PATTERN_MATCH,
        )
        with patch(
            "tank_backend.llm.capabilities.resolve_capabilities_sync",
            return_value=forced,
        ):
            response = client.post(
                "/api/upload",
                params={"session_id": "sess-1"},
                files={"file": ("x.wav", b"RIFF....WAVEfake", "audio/wav")},
            )
        assert response.status_code == 415
        assert "audio" in response.json()["detail"].lower()

    def test_happy_path_image(self, client, tmp_path):
        from tank_backend.llm.capabilities import (
            CapabilitySource,
            ModelCapabilities,
        )

        forced = ModelCapabilities(
            model_id="gpt-4o",
            input_modalities=frozenset({"text", "image"}),
            source=CapabilitySource.PATTERN_MATCH,
        )
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452"
            "000000010000000108020000009077"
            "53de0000000c49444154789c6300"
            "010000000005000168220500000000"
            "049454ae426082"
        )
        with patch(
            "tank_backend.llm.capabilities.resolve_capabilities_sync",
            return_value=forced,
        ):
            response = client.post(
                "/api/upload",
                params={"session_id": "sess-ok"},
                files={"file": ("tiny.png", png, "image/png")},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["mime_type"] == "image/png"
        assert body["modality"] == "image"
        assert body["media_uri"].startswith("media://sess-ok/")
