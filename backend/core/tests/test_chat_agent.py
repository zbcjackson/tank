"""Tests for ChatAgent."""

from unittest.mock import MagicMock

from tank_backend.agents.base import AgentOutputType, AgentState
from tank_backend.agents.chat_agent import ChatAgent, _translate
from tank_backend.core.events import UpdateType


def _make_llm_gen(events):
    """Create an async generator that yields (UpdateType, content, metadata) tuples."""

    async def gen():
        for event in events:
            yield event

    mock_gen = gen()
    return mock_gen


def _make_llm(events):
    """Create a mock LLM whose chat_stream returns a predefined sequence."""
    llm = MagicMock()

    async def chat_stream(**kwargs):
        for event in events:
            yield event

    llm.chat_stream = chat_stream
    return llm


class TestTranslate:
    def test_text(self):
        out = _translate(UpdateType.TEXT, "hello", {"turn": 1})
        assert out is not None
        assert out.type == AgentOutputType.TOKEN
        assert out.content == "hello"

    def test_thought(self):
        out = _translate(UpdateType.THOUGHT, "thinking...", {"turn": 1})
        assert out is not None
        assert out.type == AgentOutputType.THOUGHT

    def test_tool_calling(self):
        out = _translate(UpdateType.TOOL, "", {"status": "calling", "name": "calc"})
        assert out is not None
        assert out.type == AgentOutputType.TOOL_CALLING

    def test_tool_executing(self):
        out = _translate(UpdateType.TOOL, "", {"status": "executing", "name": "calc"})
        assert out is not None
        assert out.type == AgentOutputType.TOOL_EXECUTING

    def test_tool_success(self):
        out = _translate(UpdateType.TOOL, "42", {"status": "success", "name": "calc"})
        assert out is not None
        assert out.type == AgentOutputType.TOOL_RESULT

    def test_tool_error(self):
        out = _translate(UpdateType.TOOL, "Error: bad", {"status": "error", "name": "calc"})
        assert out is not None
        assert out.type == AgentOutputType.TOOL_RESULT


class TestChatAgent:
    async def test_basic_text_stream(self):
        events = [
            (UpdateType.TEXT, "Hello", {"turn": 1}),
            (UpdateType.TEXT, " world", {"turn": 1}),
        ]
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        outputs = []
        async for output in agent.run(state):
            outputs.append(output)

        # Should get 2 TOKEN + 1 DONE
        token_outputs = [o for o in outputs if o.type == AgentOutputType.TOKEN]
        done_outputs = [o for o in outputs if o.type == AgentOutputType.DONE]
        assert len(token_outputs) == 2
        assert token_outputs[0].content == "Hello"
        assert token_outputs[1].content == " world"
        assert len(done_outputs) == 1

    async def test_appends_to_state_messages(self):
        events = [
            (UpdateType.TEXT, "Hi there!", {"turn": 1}),
        ]
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "hello"}])
        async for _ in agent.run(state):
            pass

        # ChatAgent should append assistant message to state
        assert len(state.messages) == 2
        assert state.messages[1]["role"] == "assistant"
        assert state.messages[1]["content"] == "Hi there!"

    async def test_thought_events(self):
        events = [
            (UpdateType.THOUGHT, "Let me think...", {"turn": 1}),
            (UpdateType.TEXT, "Answer", {"turn": 1}),
        ]
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "why?"}])
        outputs = []
        async for output in agent.run(state):
            outputs.append(output)

        thoughts = [o for o in outputs if o.type == AgentOutputType.THOUGHT]
        assert len(thoughts) == 1
        assert thoughts[0].content == "Let me think..."

    async def test_tool_events(self):
        events = [
            (UpdateType.TOOL, "", {"status": "calling", "name": "calc", "turn": 1}),
            (UpdateType.TOOL, "", {"status": "executing", "name": "calc", "turn": 1}),
            (UpdateType.TOOL, "42", {"status": "success", "name": "calc", "turn": 1}),
            (UpdateType.TEXT, "The answer is 42.", {"turn": 1}),
        ]
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "calc 6*7"}])
        outputs = []
        async for output in agent.run(state):
            outputs.append(output)

        tool_outputs = [o for o in outputs if o.type in (
            AgentOutputType.TOOL_CALLING,
            AgentOutputType.TOOL_EXECUTING,
            AgentOutputType.TOOL_RESULT,
        )]
        assert len(tool_outputs) == 3

    async def test_system_prompt_prepended(self):
        """When system_prompt is set, it should be prepended to messages."""
        captured_messages = []

        async def chat_stream(messages, **kwargs):
            captured_messages.extend(messages)
            yield (UpdateType.TEXT, "ok", {"turn": 1})

        llm = MagicMock()
        llm.chat_stream = chat_stream

        agent = ChatAgent(name="chat", llm=llm, system_prompt="You are a search agent.")
        state = AgentState(messages=[{"role": "user", "content": "find stuff"}])
        async for _ in agent.run(state):
            pass

        assert captured_messages[0]["role"] == "system"
        assert captured_messages[0]["content"] == "You are a search agent."

    async def test_tool_filter(self):
        """Tool filter should restrict which tools are passed to LLM."""
        captured_tools = []

        async def chat_stream(messages, tools=None, **kwargs):
            captured_tools.extend(tools or [])
            yield (UpdateType.TEXT, "ok", {"turn": 1})

        llm = MagicMock()
        llm.chat_stream = chat_stream

        tool_manager = MagicMock()
        tool_manager.get_openai_tools.return_value = [
            {"type": "function", "function": {"name": "web_search", "description": "search"}},
            {"type": "function", "function": {"name": "calculator", "description": "calc"}},
            {"type": "function", "function": {"name": "weather", "description": "weather"}},
        ]

        agent = ChatAgent(
            name="search",
            llm=llm,
            tool_manager=tool_manager,
            tool_filter=["web_search"],
        )
        state = AgentState(messages=[{"role": "user", "content": "find"}])
        async for _ in agent.run(state):
            pass

        assert len(captured_tools) == 1
        assert captured_tools[0]["function"]["name"] == "web_search"

    async def test_empty_response_no_append(self):
        """If LLM returns no text, don't append empty assistant message."""
        events = []  # No events yielded
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        async for _ in agent.run(state):
            pass

        # Only the original user message should remain
        assert len(state.messages) == 1


class TestChatAgentExcludeTools:
    """Tests for exclude_tools parameter (ToolManager-based filtering)."""

    async def test_exclude_tools_passed_to_tool_manager(self):
        """exclude_tools should be forwarded to tool_manager.get_openai_tools()."""
        captured_exclude = []

        async def chat_stream(messages, tools=None, **kwargs):
            yield (UpdateType.TEXT, "ok", {"turn": 1})

        llm = MagicMock()
        llm.chat_stream = chat_stream

        tool_manager = MagicMock()

        def get_openai_tools(exclude=None):
            captured_exclude.append(exclude)
            return [
                {"type": "function", "function": {"name": "calculator", "description": "calc"}},
            ]

        tool_manager.get_openai_tools = get_openai_tools

        agent = ChatAgent(
            name="chat", llm=llm,
            tool_manager=tool_manager,
            exclude_tools={"run_command"},
        )
        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        async for _ in agent.run(state):
            pass

        assert captured_exclude == [{"run_command"}]

    async def test_no_exclude_passes_none(self):
        """Without exclude_tools, get_openai_tools gets exclude=None."""
        captured_exclude = []

        async def chat_stream(messages, tools=None, **kwargs):
            yield (UpdateType.TEXT, "ok", {"turn": 1})

        llm = MagicMock()
        llm.chat_stream = chat_stream

        tool_manager = MagicMock()

        def get_openai_tools(exclude=None):
            captured_exclude.append(exclude)
            return []

        tool_manager.get_openai_tools = get_openai_tools

        agent = ChatAgent(name="chat", llm=llm, tool_manager=tool_manager)
        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        async for _ in agent.run(state):
            pass

        assert captured_exclude == [None]

    async def test_no_tool_manager_returns_empty(self):
        """ChatAgent without tool_manager should return no tools."""
        events = [(UpdateType.TEXT, "ok", {"turn": 1})]
        llm = _make_llm(events)
        agent = ChatAgent(name="chat", llm=llm)

        state = AgentState(messages=[{"role": "user", "content": "hi"}])
        outputs = [o async for o in agent.run(state)]

        tokens = [o for o in outputs if o.type == AgentOutputType.TOKEN]
        assert len(tokens) == 1
