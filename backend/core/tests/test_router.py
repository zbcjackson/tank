"""Tests for Router agent."""

from unittest.mock import AsyncMock, MagicMock

from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.router import Route, Router


def _collect(outputs):
    """Helper to extract handoff targets from outputs."""
    return [o.target_agent for o in outputs if o.type == AgentOutputType.HANDOFF]


class TestFastPath:
    async def test_keyword_match(self):
        routes = [
            Route(name="search", agent_name="search", keywords=["search", "look up", "google"]),
            Route(name="code", agent_name="code", keywords=["run code", "execute", "python"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[{"role": "user", "content": "search for cats"}])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["search"]

    async def test_keyword_case_insensitive(self):
        routes = [
            Route(name="search", agent_name="search", keywords=["search", "google"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[{"role": "user", "content": "GOOGLE something"}])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["search"]

    async def test_no_keyword_match_falls_to_default(self):
        routes = [
            Route(name="search", agent_name="search", keywords=["search"]),
        ]
        router = Router(routes=routes, default_agent="chat")

        state = AgentState(messages=[{"role": "user", "content": "hello there"}])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]

    async def test_first_matching_route_wins(self):
        routes = [
            Route(name="search", agent_name="search", keywords=["find"]),
            Route(name="task", agent_name="task", keywords=["find"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[{"role": "user", "content": "find something"}])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["search"]

    async def test_empty_messages_returns_default(self):
        routes = [Route(name="search", agent_name="search", keywords=["search"])]
        router = Router(routes=routes, default_agent="chat")

        state = AgentState(messages=[])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]

    async def test_multi_word_keyword(self):
        routes = [
            Route(name="code", agent_name="code", keywords=["run code"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[{"role": "user", "content": "please run code for me"}])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["code"]

    async def test_cjk_keyword_substring_match(self):
        """Chinese keywords should match as substrings (no word boundaries)."""
        routes = [
            Route(name="task", agent_name="task", keywords=["天气", "计算"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[
            {"role": "user", "content": "明天上海天气如何"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["task"]

    async def test_cjk_keyword_no_false_negative(self):
        """Chinese keyword at start/end of sentence should still match."""
        routes = [
            Route(name="search", agent_name="search", keywords=["搜索"]),
        ]
        router = Router(routes=routes)

        state = AgentState(messages=[
            {"role": "user", "content": "搜索一下猫的图片"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["search"]

    async def test_mixed_cjk_and_latin_keywords(self):
        """Route with both CJK and Latin keywords should match either."""
        routes = [
            Route(name="search", agent_name="search",
                  keywords=["search", "搜索", "查找"]),
        ]
        router = Router(routes=routes)

        # Latin match
        state1 = AgentState(messages=[
            {"role": "user", "content": "search for cats"},
        ])
        outputs1 = [o async for o in router.run(state1)]
        assert _collect(outputs1) == ["search"]

        # CJK match
        state2 = AgentState(messages=[
            {"role": "user", "content": "帮我查找一下"},
        ])
        outputs2 = [o async for o in router.run(state2)]
        assert _collect(outputs2) == ["search"]

    async def test_latin_keyword_still_uses_word_boundary(self):
        """Latin keywords should NOT match as substrings (e.g. 'search' in 'research')."""
        routes = [
            Route(name="search", agent_name="search", keywords=["search"]),
        ]
        router = Router(routes=routes, default_agent="chat")

        state = AgentState(messages=[
            {"role": "user", "content": "I need to research this topic"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]  # should NOT match


class TestSlowPath:
    async def test_llm_classification(self):
        routes = [
            Route(name="search", agent_name="search",
                  keywords=[], description="Web search and info retrieval"),
        ]

        llm = MagicMock()
        llm.chat_completion_async = AsyncMock(return_value={
            "choices": [{"message": {"content": "search"}}],
        })

        router = Router(routes=routes, llm=llm, default_agent="chat")

        state = AgentState(messages=[
            {"role": "user", "content": "what is the weather in Tokyo?"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["search"]
        llm.chat_completion_async.assert_called_once()

    async def test_llm_returns_unknown_agent_falls_to_default(self):
        routes = [
            Route(name="search", agent_name="search", keywords=[],
                  description="Web search"),
        ]

        llm = MagicMock()
        llm.chat_completion_async = AsyncMock(return_value={
            "choices": [{"message": {"content": "unknown_agent"}}],
        })

        router = Router(routes=routes, llm=llm, default_agent="chat")

        state = AgentState(messages=[
            {"role": "user", "content": "something ambiguous"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]

    async def test_llm_error_falls_to_default(self):
        routes = [
            Route(name="search", agent_name="search", keywords=[],
                  description="Web search"),
        ]

        llm = MagicMock()
        llm.chat_completion_async = AsyncMock(side_effect=RuntimeError("API error"))

        router = Router(routes=routes, llm=llm, default_agent="chat")

        state = AgentState(messages=[
            {"role": "user", "content": "something"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]

    async def test_no_llm_skips_slow_path(self):
        routes = [
            Route(name="search", agent_name="search", keywords=[],
                  description="Web search"),
        ]
        router = Router(routes=routes, llm=None, default_agent="chat")

        state = AgentState(messages=[
            {"role": "user", "content": "something"},
        ])
        outputs = [o async for o in router.run(state)]
        assert _collect(outputs) == ["chat"]
