"""Tests for PartialTranscriptStabilizer (append-only ASR partials)."""

from __future__ import annotations

from tank_backend.pipeline.text.transcript_stabilizer import (
    PartialTranscriptStabilizer,
)


def feed_all(stabilizer: PartialTranscriptStabilizer, hypotheses: list[str]) -> list[str | None]:
    """Feed a fixed hypothesis sequence, collecting display texts."""
    return [stabilizer.feed(h) for h in hypotheses]


class TestPartialTranscriptStabilizer:
    def test_first_hypothesis_shows_nothing(self):
        """A single hypothesis confirms nothing — it has no prior to agree with."""
        s = PartialTranscriptStabilizer()
        assert s.feed("hello world") is None

    def test_english_growing_hypotheses_append_only(self):
        """Confirmed words accumulate; the newest edge word is held back."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "hello world",
            "hello world again",
            "hello world again now",
        ])
        # "hello" confirmed by hypotheses 1+2 (edge "world" held);
        # then "hello world" confirmed by 2+3 (edge "again" held).
        assert shown == [None, "hello", "hello world"]

    def test_tail_churn_does_not_flicker_shown_text(self):
        """The unstable tail can churn freely without retracting shown text."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "the weather is sun",
            "the weather is sunny",
            "the weather is sunny and",
            "the weather is sunny and warm",
        ])
        assert shown == [None, "the weather", "the weather is", "the weather is sunny"]

    def test_chinese_confirms_per_character(self):
        """CJK characters are stability tokens — confirmed one char at a time."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "今天天气",
            "今天天气很好",
            "今天天气很好我们出发",
        ])
        # 气 confirmed by hypotheses 1+2 (edge held) → 今天天;
        # then 好 confirmed by 2+3 → 今天天气很.
        assert shown == [None, "今天天", "今天天气很"]

    def test_mixed_bilingual(self):
        """CJK chars and latin words intermix in one token stream."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "今天weather",
            "今天weather is good",
        ])
        # 今/天/weather confirmed by both; edge "weather" held back.
        assert shown == [None, "今天"]

    def test_punctuation_dropped_from_comparison(self):
        """Punctuation changes don't break agreement between hypotheses."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "你好，世界",
            "你好世界 today",
        ])
        # 你/好/世/界 agree once the comma is ignored; edge "界" held back.
        assert shown == [None, "你好世"]

    def test_case_insensitive_comparison(self):
        """Case changes between hypotheses don't break agreement."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "Hello World",
            "hello world again",
        ])
        assert shown == [None, "hello"]

    def test_internal_punctuation_stays_in_display(self):
        """A URL's inner dot is part of the token and survives in the display."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "see example.com for",
            "see example.com for more",
        ])
        assert shown == [None, "see example.com"]

    def test_unconfirmed_tail_revision_does_not_retract(self):
        """A re-scored tail word stays hidden instead of flickering."""
        s = PartialTranscriptStabilizer()
        shown = feed_all(s, [
            "hello world",
            "hello world foo",
            "hello world bar",
        ])
        # "foo" → "bar" never confirmed; display stays at "hello".
        assert shown == [None, "hello", None]

    def test_rare_rescore_of_shown_word_corrects_display(self):
        """When an already-shown word is genuinely revised, the correction
        is shown (tank's UI replaces partials wholesale — no delta protocol)."""
        s = PartialTranscriptStabilizer()
        assert s.feed("hello world") is None
        assert s.feed("hello world foo") == "hello"
        assert s.feed("hello earth foo") == ""

    def test_reset_clears_utterance_state(self):
        """After reset, the next utterance starts from no history."""
        s = PartialTranscriptStabilizer()
        feed_all(s, ["hello world", "hello world again"])
        s.reset()
        assert s.feed("hello world") is None
        assert s.feed("hello world again") == "hello"

    def test_edge_churn_below_confirmed_boundary_not_repeated(self):
        """Tail churn that confirms nothing new → None (caller skips posting)."""
        s = PartialTranscriptStabilizer()
        assert s.feed("hello world foo") is None
        assert s.feed("hello world bar") == "hello"
        assert s.feed("hello world baz") is None
