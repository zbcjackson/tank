"""Tests for agent base classes and AgentOutput protocol."""

import pytest

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState


class TestAgentState:
    def test_defaults(self):
        state = AgentState()
        assert state.messages == []
        assert state.metadata == {}
        assert state.agent_history == []
        assert state.turn == 0

    def test_messages_mutable(self):
        state = AgentState()
        state.messages.append({"role": "user", "content": "hello"})
        assert len(state.messages) == 1

    def test_agent_history_tracks_agents(self):
        state = AgentState()
        state.agent_history.append("router")
        state.agent_history.append("chat")
        assert state.agent_history == ["router", "chat"]


class TestAgentOutput:
    def test_frozen(self):
        output = AgentOutput(type=AgentOutputType.TOKEN, content="hi")
        with pytest.raises(AttributeError):
            output.content = "changed"  # type: ignore[misc]

    def test_defaults(self):
        output = AgentOutput(type=AgentOutputType.DONE)
        assert output.content == ""
        assert output.metadata == {}
        assert output.target_agent is None

    def test_handoff_with_target(self):
        output = AgentOutput(
            type=AgentOutputType.HANDOFF,
            target_agent="search",
        )
        assert output.target_agent == "search"


class TestAgentOutputType:
    def test_all_types_exist(self):
        expected = {
            "TOKEN", "THOUGHT", "TOOL_CALLING", "TOOL_EXECUTING",
            "TOOL_RESULT", "APPROVAL_NEEDED", "HANDOFF", "DONE",
        }
        actual = {t.name for t in AgentOutputType}
        assert actual == expected


class TestAgentABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Agent("test")  # type: ignore[abstract]

    async def test_concrete_subclass_works(self):
        class DummyAgent(Agent):
            async def run(self, state):
                yield AgentOutput(type=AgentOutputType.DONE)

        agent = DummyAgent("dummy")
        assert agent.name == "dummy"

        outputs = []
        async for output in agent.run(AgentState()):
            outputs.append(output)
        assert len(outputs) == 1
        assert outputs[0].type == AgentOutputType.DONE
