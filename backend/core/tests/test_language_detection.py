"""Tests for core language detection utility."""

from tank_backend.core.language import LanguageDetection, detect_language


class TestDetectLanguage:
    """Tests for detect_language()."""

    def test_pure_chinese(self):
        r = detect_language("今天天气很好")
        assert r.language == "zh"
        assert r.confidence >= 0.8

    def test_pure_english(self):
        r = detect_language("What is the weather like today")
        assert r.language == "en"
        assert r.confidence >= 0.8

    def test_code_switching_zh_dominant(self):
        """Chinese sentence with English words → still Chinese."""
        r = detect_language("今天weather很好啊")
        assert r.language == "zh"

    def test_code_switching_en_dominant(self):
        """English sentence with a few Chinese words → English."""
        r = detect_language(
            "The meeting is at three o'clock, let's discuss the project details"
        )
        assert r.language == "en"

    def test_empty_string(self):
        r = detect_language("")
        assert r.language == "zh"  # preferred default
        assert r.confidence == 0.0

    def test_numbers_only(self):
        r = detect_language("12345 67890")
        assert r.language == "zh"  # preferred default (no alphabetic content)
        assert r.confidence == 0.0

    def test_symbols_only(self):
        r = detect_language("!@#$%^&*()")
        assert r.language == "zh"
        assert r.confidence == 0.0

    def test_preferred_fallback(self):
        """When preferred is 'en', empty text should return 'en'."""
        r = detect_language("", preferred="en")
        assert r.language == "en"

    def test_custom_candidates(self):
        """Detection constrained to candidate set."""
        r = detect_language("こんにちは世界", candidates=("zh", "en", "ja"), preferred="zh")
        assert r.language == "ja"

    def test_returns_dataclass(self):
        r = detect_language("Hello")
        assert isinstance(r, LanguageDetection)
        assert isinstance(r.language, str)
        assert isinstance(r.confidence, float)


class TestSelectVoice:
    """Tests for select_voice() helper in contracts."""

    def test_exact_match(self):
        from tank_contracts.tts import select_voice
        voices = {"zh": "XiaoxiaoNeural", "en": "JennyNeural"}
        assert select_voice("en", voices, "JennyNeural") == "JennyNeural"
        assert select_voice("zh", voices, "JennyNeural") == "XiaoxiaoNeural"

    def test_prefix_match(self):
        from tank_contracts.tts import select_voice
        voices = {"zh": "XiaoxiaoNeural", "en": "JennyNeural"}
        assert select_voice("zh-CN", voices, "JennyNeural") == "XiaoxiaoNeural"

    def test_unknown_language_returns_default(self):
        from tank_contracts.tts import select_voice
        voices = {"zh": "XiaoxiaoNeural", "en": "JennyNeural"}
        assert select_voice("fr", voices, "JennyNeural") == "JennyNeural"

    def test_auto_returns_default(self):
        from tank_contracts.tts import select_voice
        voices = {"zh": "XiaoxiaoNeural", "en": "JennyNeural"}
        assert select_voice("auto", voices, "JennyNeural") == "JennyNeural"

    def test_empty_returns_default(self):
        from tank_contracts.tts import select_voice
        voices = {"zh": "XiaoxiaoNeural", "en": "JennyNeural"}
        assert select_voice("", voices, "JennyNeural") == "JennyNeural"
