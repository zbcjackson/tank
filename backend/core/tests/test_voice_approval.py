"""Tests for voice-based approval intent classification and TTS prompt building."""

from __future__ import annotations

import pytest

from tank_backend.pipeline.processors.brain import (
    _build_approval_prompt,
    _classify_approval_intent,
)


class TestClassifyApprovalIntent:
    """Test the keyword-based intent classifier."""

    @pytest.mark.parametrize("text", [
        "yes", "Yeah", "YEP", "sure", "ok", "okay",
        "go ahead", "proceed", "continue", "approve", "do it",
        "confirmed", "go for it",
    ])
    def test_positive_english(self, text: str):
        assert _classify_approval_intent(text) is True

    @pytest.mark.parametrize("text", [
        "是", "是的", "好", "好的", "行", "可以",
        "继续", "执行", "没问题", "确认",
    ])
    def test_positive_chinese(self, text: str):
        assert _classify_approval_intent(text) is True

    @pytest.mark.parametrize("text", [
        "no", "Nope", "CANCEL", "stop", "don't", "deny",
        "reject", "abort", "never", "negative",
    ])
    def test_negative_english(self, text: str):
        assert _classify_approval_intent(text) is False

    @pytest.mark.parametrize("text", [
        "不", "不要", "不行", "取消", "停止", "拒绝", "算了", "别",
    ])
    def test_negative_chinese(self, text: str):
        assert _classify_approval_intent(text) is False

    @pytest.mark.parametrize("text", [
        "yes, please", "ok let's do it", "sure thing",
    ])
    def test_positive_with_trailing_text(self, text: str):
        assert _classify_approval_intent(text) is True

    @pytest.mark.parametrize("text", [
        "no way", "cancel that", "don't do it",
    ])
    def test_negative_with_trailing_text(self, text: str):
        assert _classify_approval_intent(text) is False

    @pytest.mark.parametrize("text", [
        "what does this code do?",
        "tell me more about it",
        "I'm not sure",
        "maybe",
        "let me think",
        "",
        "  ",
    ])
    def test_ambiguous_returns_none(self, text: str):
        assert _classify_approval_intent(text) is None

    def test_case_insensitive(self):
        assert _classify_approval_intent("YES") is True
        assert _classify_approval_intent("No") is False

    def test_whitespace_stripped(self):
        assert _classify_approval_intent("  yes  ") is True
        assert _classify_approval_intent("  no  ") is False


class TestBuildApprovalPrompt:
    """Test TTS prompt generation for approval requests."""

    def test_english_prompt(self):
        prompt = _build_approval_prompt("run Python code: print(1)", "en")
        assert "I'd like to" in prompt
        assert "print(1)" in prompt
        assert "Should I proceed" in prompt

    def test_chinese_prompt(self):
        prompt = _build_approval_prompt("运行Python代码", "zh")
        assert "我想要" in prompt
        assert "可以继续吗" in prompt

    def test_default_to_english(self):
        prompt = _build_approval_prompt("test action", "")
        assert "I'd like to" in prompt

    def test_none_language_defaults_to_english(self):
        prompt = _build_approval_prompt("test action", None)
        assert "I'd like to" in prompt
