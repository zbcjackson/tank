"""Tests for TTS text normalizer — pure function, no mocks needed."""

from __future__ import annotations

from tank_backend.pipeline.processors.tts_normalizer import normalize_for_tts


class TestMarkdownStripping:
    def test_bold_asterisks(self):
        assert normalize_for_tts("This is **bold** text") == "This is bold text"

    def test_bold_underscores(self):
        assert normalize_for_tts("This is __bold__ text") == "This is bold text"

    def test_italic_asterisks(self):
        assert normalize_for_tts("This is *italic* text") == "This is italic text"

    def test_italic_underscores(self):
        assert normalize_for_tts("This is _italic_ text") == "This is italic text"

    def test_bold_italic(self):
        assert normalize_for_tts("This is ***bold italic*** text") == "This is bold italic text"

    def test_inline_code(self):
        assert normalize_for_tts("Use `print()` here") == "Use print() here"

    def test_code_block_fenced(self):
        text = "Here is code:\n```python\nprint('hello')\n```\nDone."
        assert normalize_for_tts(text) == "Here is code: Done."

    def test_code_block_no_language(self):
        text = "Example:\n```\nsome code\n```\nEnd."
        assert normalize_for_tts(text) == "Example: End."

    def test_headers(self):
        assert normalize_for_tts("# Title") == "Title"
        assert normalize_for_tts("## Subtitle") == "Subtitle"
        assert normalize_for_tts("### Deep header") == "Deep header"

    def test_links(self):
        assert normalize_for_tts("Click [here](https://example.com)") == "Click here"

    def test_images(self):
        assert normalize_for_tts("![alt text](image.png)") == "alt text"

    def test_strikethrough(self):
        assert normalize_for_tts("This is ~~deleted~~ text") == "This is deleted text"

    def test_horizontal_rule(self):
        text = "Above\n---\nBelow"
        result = normalize_for_tts(text)
        assert "---" not in result
        assert "Above" in result
        assert "Below" in result

    def test_blockquote(self):
        assert normalize_for_tts("> This is a quote") == "This is a quote"

    def test_unordered_list(self):
        text = "Items:\n- First\n- Second\n- Third"
        result = normalize_for_tts(text)
        assert "First" in result
        assert "Second" in result
        assert "-" not in result.replace("First", "").replace("Second", "").replace("Third", "")

    def test_ordered_list(self):
        text = "Steps:\n1. First\n2. Second\n3. Third"
        result = normalize_for_tts(text)
        assert "First" in result
        assert "Second" in result


class TestEmojiRemoval:
    def test_simple_emoji(self):
        assert normalize_for_tts("Hello 😀 world") == "Hello world"

    def test_multiple_emoji(self):
        assert normalize_for_tts("Great 🎉🎊 job 👍") == "Great job"

    def test_emoji_only(self):
        assert normalize_for_tts("😀😃😄") == ""

    def test_flag_emoji(self):
        result = normalize_for_tts("Hello 🇺🇸 world")
        assert "Hello" in result
        assert "world" in result

    def test_compound_emoji(self):
        # Family emoji, skin tone modifiers, etc.
        result = normalize_for_tts("Hi 👨‍👩‍👧‍👦 there")
        assert "Hi" in result
        assert "there" in result


class TestSpecialCharacters:
    def test_em_dash(self):
        result = normalize_for_tts("word — another")
        assert "—" not in result

    def test_en_dash(self):
        result = normalize_for_tts("word – another")
        assert "–" not in result

    def test_smart_quotes(self):
        result = normalize_for_tts("\u201cHello\u201d and \u2018world\u2019")
        assert "\u201c" not in result
        assert "\u201d" not in result
        assert "\u2018" not in result
        assert "\u2019" not in result
        assert "Hello" in result
        assert "world" in result

    def test_bullet_chars(self):
        result = normalize_for_tts("• Item one\n▪ Item two")
        assert "•" not in result
        assert "▪" not in result
        assert "Item one" in result
        assert "Item two" in result

    def test_ellipsis_char(self):
        result = normalize_for_tts("Wait\u2026 okay")
        assert "Wait" in result
        assert "okay" in result


class TestWhitespace:
    def test_multiple_spaces(self):
        assert normalize_for_tts("hello    world") == "hello world"

    def test_multiple_newlines(self):
        result = normalize_for_tts("hello\n\n\nworld")
        assert result == "hello world"

    def test_tabs(self):
        assert normalize_for_tts("hello\tworld") == "hello world"

    def test_leading_trailing(self):
        assert normalize_for_tts("  hello world  ") == "hello world"


class TestPreservesSpeechPunctuation:
    def test_period(self):
        assert normalize_for_tts("Hello. World.") == "Hello. World."

    def test_comma(self):
        assert normalize_for_tts("Hello, world.") == "Hello, world."

    def test_question_mark(self):
        assert normalize_for_tts("How are you?") == "How are you?"

    def test_exclamation(self):
        assert normalize_for_tts("Wow!") == "Wow!"

    def test_semicolon_colon(self):
        assert normalize_for_tts("First; second: third.") == "First; second: third."


class TestChineseText:
    def test_chinese_passthrough(self):
        assert normalize_for_tts("你好世界") == "你好世界"

    def test_chinese_with_markdown(self):
        assert normalize_for_tts("这是**加粗**文字") == "这是加粗文字"

    def test_mixed_chinese_english(self):
        result = normalize_for_tts("Hello 你好 **world** 世界")
        assert result == "Hello 你好 world 世界"


class TestEdgeCases:
    def test_empty_string(self):
        assert normalize_for_tts("") == ""

    def test_whitespace_only(self):
        assert normalize_for_tts("   \n\n  ") == ""

    def test_already_clean(self):
        text = "The weather today is sunny and warm."
        assert normalize_for_tts(text) == text

    def test_nested_markdown(self):
        assert normalize_for_tts("This is ***bold and italic***") == "This is bold and italic"

    def test_multiple_code_blocks(self):
        text = "First:\n```\ncode1\n```\nMiddle.\n```\ncode2\n```\nEnd."
        assert normalize_for_tts(text) == "First: Middle. End."

    def test_complex_real_world(self):
        text = (
            "## Weather Report\n\n"
            "The temperature is **72°F** (22°C). "
            "It's a *beautiful* day! 🌞\n\n"
            "- Humidity: 45%\n"
            "- Wind: 10 mph\n\n"
            "For more info, visit [weather.com](https://weather.com)."
        )
        result = normalize_for_tts(text)
        assert "**" not in result
        assert "##" not in result
        assert "🌞" not in result
        assert "[" not in result
        assert "72°F" in result
        assert "beautiful" in result
        assert "Humidity: 45%" in result
