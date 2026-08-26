"""Tests for SentenceBuffer — sentence-level batching of streamed LLM tokens."""

from __future__ import annotations

from tank_backend.pipeline.text.sentence_splitter import SentenceBuffer


def feed_by_token(buf: SentenceBuffer, text: str) -> list[str]:
    """Feed text one char at a time, collecting every drained batch."""
    batches: list[str] = []
    for ch in text:
        buf.feed(ch)
        batches.extend(buf.drain_ready())
    batches.append(buf.flush())
    return [b for b in (x.strip() for x in batches) if b]


class TestChineseSentences:
    def test_two_sentences_batch_then_flush_tail(self):
        buf = SentenceBuffer(min_sentences=2)
        buf.feed("今天天气很好。我们去公园吧。然后吃饭。")

        batches = buf.drain_ready()
        assert batches == ["今天天气很好。我们去公园吧。"]
        assert buf.flush() == "然后吃饭。"

    def test_punctuation_run_is_one_boundary(self):
        """Consecutive sentence-end punctuation (。。。) is a single boundary."""
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("等等。。。好吧。")

        # CJK punctuation is an immediate boundary (no trailing space needed)
        assert buf.drain_ready() == ["等等。。。", "好吧。"]
        assert buf.flush() == ""

    def test_trailing_closing_quote_stays_with_sentence(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("他说：“走吧。”然后离开了。")

        assert buf.drain_ready() == ["他说：“走吧。”", "然后离开了。"]
        assert buf.flush() == ""

    def test_semicolon_is_a_boundary(self):
        buf = SentenceBuffer(min_sentences=2)
        buf.feed("第一；第二；第三。")

        assert buf.drain_ready() == ["第一；第二；"]
        assert buf.flush() == "第三。"

    def test_ellipsis_char_is_a_boundary(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("我想想…算了。")

        assert buf.drain_ready() == ["我想想…", "算了。"]
        assert buf.flush() == ""


class TestEnglishSentences:
    def test_basic_batching(self):
        buf = SentenceBuffer(min_sentences=2)
        buf.feed("Hello there. How are you? I am fine!")

        assert buf.drain_ready() == ["Hello there. How are you?"]
        assert buf.flush() == "I am fine!"

    def test_decimal_point_not_a_boundary(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Pi is 3.14159. It is useful.")

        assert buf.drain_ready() == ["Pi is 3.14159."]
        assert buf.flush() == "It is useful."

    def test_abbreviation_not_a_boundary(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Mr. Smith arrived. He sat down.")

        assert buf.drain_ready() == ["Mr. Smith arrived."]
        assert buf.flush() == "He sat down."

    def test_url_dots_not_boundaries(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("See example.com for details. It works.")

        assert buf.drain_ready() == ["See example.com for details."]
        assert buf.flush() == "It works."

    def test_paragraph_break_is_a_boundary(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("First paragraph.\n\nSecond paragraph.")

        assert buf.drain_ready() == ["First paragraph."]
        assert buf.flush() == "Second paragraph."

    def test_ellipsis_dots_single_boundary(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Wait... okay.")

        assert buf.drain_ready() == ["Wait..."]
        assert buf.flush() == "okay."


class TestWithholding:
    def test_no_cut_inside_closed_code_block(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Start. ```python\nprint(1)\n```\nAll done here.")

        # Boundary inside the fence is suppressed; text after the closing
        # fence becomes speakable again (TTS normalizer drops the fence).
        assert buf.drain_ready() == ["Start."]
        tail = buf.flush()
        assert "All done here." in tail
        assert tail.startswith("```")

    def test_unclosed_code_block_withheld_until_flush_and_dropped(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Hello. ```code never closed")

        assert buf.drain_ready() == ["Hello."]
        assert buf.flush() == ""

    def test_image_markdown_removed(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Look at ![pic](https://x.com/a.png) this picture. Nice.")

        batches = buf.drain_ready()
        assert batches == ["Look at this picture."]
        assert "![" not in batches[0]
        assert "https" not in batches[0]

    def test_image_split_across_tokens_removed(self):
        buf = SentenceBuffer(min_sentences=2)
        for ch in "Before. See ![im](http://y.io/b.png) it. After words here.":
            buf.feed(ch)
            buf.drain_ready()

        assert "![" not in buf.flush()
        assert "http" not in buf.flush()

    def test_text_after_closed_fence_streams(self):
        """Prose following a closed code block is not held hostage."""
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("Intro. ```js\ncode()\n``` Tail sentence one. More prose.")

        batches = buf.drain_ready()
        assert batches[0] == "Intro."
        # The whole fence rides along in one batch (never split mid-block);
        # the TTS normalizer drops complete fences per item downstream.
        assert batches[1].startswith("```")
        assert "Tail sentence one." in batches[1]
        assert buf.flush() == "More prose."


class TestBatchingBehaviour:
    def test_min_sentences_accumulates(self):
        buf = SentenceBuffer(min_sentences=3)
        buf.feed("One. Two.")
        assert buf.drain_ready() == []

        buf.feed(" Three. ")  # trailing space: the "." needs a follower to be a boundary
        assert buf.drain_ready() == ["One. Two. Three."]

    def test_multiple_batches_in_one_drain(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("A. B. C.")

        assert buf.drain_ready() == ["A.", "B."]
        assert buf.flush() == "C."

    def test_char_by_char_matches_whole_string(self):
        text = "这是第一句。这是第二句！English third. 3.5 stays. Done?"
        buf = SentenceBuffer(min_sentences=2)
        buf.feed(text)
        whole = [*buf.drain_ready(), buf.flush()]

        assert feed_by_token(SentenceBuffer(min_sentences=2), text) == [
            b.strip() for b in whole if b.strip()
        ]

    def test_flush_empties_buffer(self):
        buf = SentenceBuffer(min_sentences=5)
        buf.feed("Only one sentence.")
        first = buf.flush()

        assert first == "Only one sentence."
        assert buf.flush() == ""

    def test_empty_and_blank_input(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("")
        buf.feed("   ")
        assert buf.drain_ready() == []
        assert buf.flush() == ""

    def test_whitespace_between_batches_stripped(self):
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("First.   \n   Second here.")

        assert buf.drain_ready() == ["First."]
        assert buf.flush() == "Second here."

    def test_min_sentences_clamped_to_one(self):
        buf = SentenceBuffer(min_sentences=0)
        buf.feed("Solo. ")

        assert buf.drain_ready() == ["Solo."]


class TestMarkdownEmphasis:
    def test_emphasis_within_sentence_not_split(self):
        """Bold spanning words inside one sentence stays in one batch."""
        buf = SentenceBuffer(min_sentences=1)
        buf.feed("He is **very important**. Next one.")

        assert buf.drain_ready() == ["He is **very important**."]
        assert buf.flush() == "Next one."
