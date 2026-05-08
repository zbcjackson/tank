"""Tests for the multi-modal content block module."""

import pytest

from tank_backend.core.content import (
    MODALITY_AUDIO,
    MODALITY_FILE,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    AudioBlock,
    DocumentBlock,
    ImageBlock,
    TextBlock,
    block_from_dict,
    block_modality,
    block_to_dict,
    blocks_modalities,
    blocks_to_text,
    normalize_content,
)


class TestBlockConstruction:
    def test_text_block_defaults(self):
        b = TextBlock(text="hi")
        assert b.type == "text"
        assert b.text == "hi"

    def test_image_block_defaults(self):
        b = ImageBlock(source="/x.png", mime_type="image/png")
        assert b.type == "image"
        assert b.detail == "auto"

    def test_image_block_detail_override(self):
        b = ImageBlock(source="/x.png", mime_type="image/png", detail="high")
        assert b.detail == "high"

    def test_document_block_with_extracted_text(self):
        b = DocumentBlock(
            source="/doc.pdf",
            mime_type="application/pdf",
            extracted_text="hello world",
        )
        assert b.extracted_text == "hello world"
        assert b.page_images == ()

    def test_document_block_with_page_images(self):
        pages = (
            ImageBlock(source="/p1.png", mime_type="image/png"),
            ImageBlock(source="/p2.png", mime_type="image/png"),
        )
        b = DocumentBlock(
            source="/doc.pdf",
            mime_type="application/pdf",
            page_images=pages,
        )
        assert len(b.page_images) == 2

    def test_audio_block_with_transcript(self):
        b = AudioBlock(
            source="/x.wav",
            mime_type="audio/wav",
            transcript="hello",
        )
        assert b.transcript == "hello"

    def test_blocks_are_frozen(self):
        from dataclasses import FrozenInstanceError

        b = TextBlock(text="hi")
        with pytest.raises(FrozenInstanceError):
            b.text = "bye"  # type: ignore[misc]


class TestModalityClassification:
    def test_text_modality(self):
        assert block_modality(TextBlock(text="x")) == MODALITY_TEXT

    def test_image_modality(self):
        assert (
            block_modality(ImageBlock(source="/x.png", mime_type="image/png"))
            == MODALITY_IMAGE
        )

    def test_document_modality(self):
        assert (
            block_modality(
                DocumentBlock(source="/x.pdf", mime_type="application/pdf")
            )
            == MODALITY_FILE
        )

    def test_audio_modality(self):
        assert (
            block_modality(AudioBlock(source="/x.wav", mime_type="audio/wav"))
            == MODALITY_AUDIO
        )

    def test_blocks_modalities_aggregates(self):
        blocks = [
            TextBlock(text="t"),
            ImageBlock(source="/x.png", mime_type="image/png"),
            ImageBlock(source="/y.png", mime_type="image/png"),
        ]
        assert blocks_modalities(blocks) == frozenset(
            {MODALITY_TEXT, MODALITY_IMAGE}
        )

    def test_blocks_modalities_empty(self):
        assert blocks_modalities([]) == frozenset()


class TestSerialization:
    def test_text_roundtrip(self):
        b = TextBlock(text="hello")
        assert block_from_dict(block_to_dict(b)) == b

    def test_image_roundtrip(self):
        b = ImageBlock(source="/x.png", mime_type="image/png", detail="high")
        assert block_from_dict(block_to_dict(b)) == b

    def test_document_roundtrip_with_pages(self):
        pages = (
            ImageBlock(source="/p1.png", mime_type="image/png"),
            ImageBlock(source="/p2.png", mime_type="image/png", detail="low"),
        )
        b = DocumentBlock(
            source="/doc.pdf",
            mime_type="application/pdf",
            extracted_text="abc",
            page_images=pages,
        )
        restored = block_from_dict(block_to_dict(b))
        assert restored == b

    def test_audio_roundtrip(self):
        b = AudioBlock(
            source="/x.wav",
            mime_type="audio/wav",
            transcript="hi",
        )
        assert block_from_dict(block_to_dict(b)) == b

    def test_audio_roundtrip_no_transcript(self):
        b = AudioBlock(source="/x.wav", mime_type="audio/wav")
        assert block_from_dict(block_to_dict(b)) == b

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown content block type"):
            block_from_dict({"type": "nonsense"})


class TestNormalizeContent:
    def test_string_wraps_to_text_block(self):
        result = normalize_content("hello")
        assert result == [TextBlock(text="hello")]

    def test_block_list_passes_through(self):
        blocks = [TextBlock(text="a"), ImageBlock(source="/x", mime_type="image/png")]
        result = normalize_content(blocks)
        assert result == blocks
        # Defensive copy: mutations don't leak
        result.append(TextBlock(text="b"))
        assert len(blocks) == 2


class TestBlocksToText:
    def test_plain_text(self):
        blocks = [TextBlock(text="line one"), TextBlock(text="line two")]
        assert blocks_to_text(blocks) == "line one\nline two"

    def test_image_gets_placeholder(self):
        blocks = [ImageBlock(source="/x.png", mime_type="image/png")]
        assert blocks_to_text(blocks) == "[image: image/png @ /x.png]"

    def test_document_prefers_extracted_text(self):
        blocks = [
            DocumentBlock(
                source="/x.pdf",
                mime_type="application/pdf",
                extracted_text="full doc text",
            )
        ]
        assert blocks_to_text(blocks) == "full doc text"

    def test_document_without_text_gets_placeholder(self):
        blocks = [DocumentBlock(source="/x.pdf", mime_type="application/pdf")]
        assert blocks_to_text(blocks) == "[document: application/pdf @ /x.pdf]"

    def test_audio_prefers_transcript(self):
        blocks = [
            AudioBlock(
                source="/x.wav", mime_type="audio/wav", transcript="hello world"
            )
        ]
        assert blocks_to_text(blocks) == "hello world"

    def test_audio_without_transcript_gets_placeholder(self):
        blocks = [AudioBlock(source="/x.wav", mime_type="audio/wav")]
        assert blocks_to_text(blocks) == "[audio: audio/wav @ /x.wav]"

    def test_mixed(self):
        blocks = [
            TextBlock(text="Here is a chart:"),
            ImageBlock(source="/chart.png", mime_type="image/png"),
            TextBlock(text="What do you see?"),
        ]
        assert blocks_to_text(blocks) == (
            "Here is a chart:\n[image: image/png @ /chart.png]\nWhat do you see?"
        )
