"""Tests for token counting via Brain._context.count_tokens()."""


from brain_test_helpers import make_brain, make_mock_context


class TestCountTokens:
    def test_count_tokens_delegates_to_context(self):
        """Brain should delegate token counting to context."""
        ctx = make_mock_context()
        ctx.count_tokens.return_value = 42
        brain = make_brain(context=ctx)

        result = brain._context.count_tokens([{"role": "user", "content": "hello"}])
        assert result == 42
        ctx.count_tokens.assert_called_once()

    def test_count_tokens_empty_messages(self):
        ctx = make_mock_context()
        ctx.count_tokens.return_value = 0
        brain = make_brain(context=ctx)

        result = brain._context.count_tokens([])
        assert result == 0

    def test_count_tokens_multiple_messages(self):
        ctx = make_mock_context()
        ctx.count_tokens.return_value = 100
        brain = make_brain(context=ctx)

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        result = brain._context.count_tokens(messages)
        assert result == 100
