"""Tests for WorkerTool — wraps a ChatAgent as a callable tool."""

import json

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType, AgentState
from tank_backend.agents.worker_tool import WorkerTool
from tank_backend.tools.base import ToolInfo


class _MockWorkerAgent(Agent):
    """Agent that yields a predefined sequence of outputs."""

    def __init__(self, outputs: list[AgentOutput]):
        super().__init__("mock_worker")
        self._outputs = outputs

    async def run(self, state: AgentState):
        for output in self._outputs:
            yield output


class _SlowAgent(Agent):
    """Agent that sleeps longer than the timeout."""

    def __init__(self, delay: float):
        super().__init__("slow_worker")
        self._delay = delay

    async def run(self, state: AgentState):
        import asyncio
        await asyncio.sleep(self._delay)
        yield AgentOutput(type=AgentOutputType.TOKEN, content="too late")
        yield AgentOutput(type=AgentOutputType.DONE)


class _ErrorAgent(Agent):
    """Agent that raises an exception."""

    def __init__(self, error: Exception):
        super().__init__("error_worker")
        self._error = error

    async def run(self, state: AgentState):
        raise self._error
        yield  # make it a generator  # noqa: E501


class TestWorkerToolGetInfo:
    def test_returns_correct_schema(self):
        agent = _MockWorkerAgent([AgentOutput(type=AgentOutputType.DONE)])
        tool = WorkerTool(
            name="delegate_to_coder",
            description="Run code tasks",
            worker_agent=agent,
        )
        info = tool.get_info()

        assert isinstance(info, ToolInfo)
        assert info.name == "delegate_to_coder"
        assert info.description == "Run code tasks"
        assert len(info.parameters) == 1
        assert info.parameters[0].name == "task"
        assert info.parameters[0].type == "string"
        assert info.parameters[0].required is True


class TestWorkerToolExecute:
    async def test_success_with_tokens(self):
        outputs = [
            AgentOutput(type=AgentOutputType.TOKEN, content="Hello"),
            AgentOutput(type=AgentOutputType.TOKEN, content=" world"),
            AgentOutput(type=AgentOutputType.DONE),
        ]
        agent = _MockWorkerAgent(outputs)
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="say hello")
        result = json.loads(raw)

        assert result["status"] == "success"
        assert result["response"] == "Hello world"

    async def test_success_with_tool_results(self):
        outputs = [
            AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content="42",
                metadata={"name": "calculator", "status": "success"},
            ),
            AgentOutput(type=AgentOutputType.TOKEN, content="The answer is 42"),
            AgentOutput(type=AgentOutputType.DONE),
        ]
        agent = _MockWorkerAgent(outputs)
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="calculate 6*7")
        result = json.loads(raw)

        assert result["status"] == "success"
        assert result["response"] == "The answer is 42"
        assert "calculator: success" in result["tools_used"]

    async def test_empty_response(self):
        outputs = [AgentOutput(type=AgentOutputType.DONE)]
        agent = _MockWorkerAgent(outputs)
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="do nothing")
        result = json.loads(raw)

        assert result["status"] == "success"
        assert result["response"] == ""
        assert "tools_used" not in result

    async def test_timeout_returns_partial(self):
        agent = _SlowAgent(delay=5.0)
        tool = WorkerTool(
            name="test", description="test",
            worker_agent=agent, timeout=0.1,
        )

        raw = await tool.execute(task="slow task")
        result = json.loads(raw)

        assert result["status"] == "timeout"
        assert "timed out" in result["message"]

    async def test_error_returns_error_status(self):
        agent = _ErrorAgent(RuntimeError("boom"))
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="fail")
        result = json.loads(raw)

        assert result["status"] == "error"
        assert "boom" in result["message"]

    async def test_ignores_non_token_non_tool_outputs(self):
        """THOUGHT and TOOL_CALLING outputs should be silently consumed."""
        outputs = [
            AgentOutput(type=AgentOutputType.THOUGHT, content="thinking..."),
            AgentOutput(type=AgentOutputType.TOOL_CALLING, content="", metadata={"name": "calc"}),
            AgentOutput(type=AgentOutputType.TOKEN, content="result"),
            AgentOutput(type=AgentOutputType.DONE),
        ]
        agent = _MockWorkerAgent(outputs)
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="think and compute")
        result = json.loads(raw)

        assert result["status"] == "success"
        assert result["response"] == "result"

    async def test_stops_at_done(self):
        """Should stop collecting after DONE even if more outputs follow."""
        outputs = [
            AgentOutput(type=AgentOutputType.TOKEN, content="before"),
            AgentOutput(type=AgentOutputType.DONE),
            AgentOutput(type=AgentOutputType.TOKEN, content="after"),
        ]
        agent = _MockWorkerAgent(outputs)
        tool = WorkerTool(name="test", description="test", worker_agent=agent)

        raw = await tool.execute(task="test")
        result = json.loads(raw)

        assert result["response"] == "before"
