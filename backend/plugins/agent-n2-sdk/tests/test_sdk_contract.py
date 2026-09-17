"""Exercise the pinned SDK without network or host input."""

from importlib.metadata import version

from yutori.navigator.n2 import N2ComputerAgent
from yutori.navigator.macos.types import CancellationLatch


class Computer:
    def __init__(self):
        self.cancellation = CancellationLatch()
        self.closed = False

    async def get_dimensions(self):
        return 100, 100

    async def aclose(self):
        self.closed = True


class Completions:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def create(self, messages, *, model="n2", **kwargs):
        kwargs.update(messages=messages, model=model)
        self.calls.append(kwargs)
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "done"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }


async def test_pinned_sdk_callbacks_and_close_ownership():
    assert version("yutori") == "0.9.29"
    events = []

    class Callbacks:
        async def on_api_start(self, kwargs):
            events.append("start")

        async def on_api_end(self, kwargs, response):
            events.append("end")

        async def on_usage(self, usage):
            events.append("usage")

        async def on_text(self, item):
            events.append("text")

    computer, completions = Computer(), Completions()
    agent = N2ComputerAgent(
        computer=computer,
        completions=completions,
        callbacks=[Callbacks()],
        screenshot_delay=0,
    )
    frames = [frame async for frame in agent.run("task")]
    assert frames and agent.stopped_by == "final_answer"
    assert events == ["start", "end", "usage", "text"]
    await agent.aclose()
    assert not computer.closed and not completions.closed


async def test_sdk_step_limit_is_not_final_answer():
    agent = N2ComputerAgent(computer=Computer(), completions=Completions(), max_steps=0)
    assert [frame async for frame in agent.run("task")] == []
    assert agent.stopped_by == "max_steps"


async def test_sdk_compactor_uses_injected_completions():
    completions = Completions()

    class Compactor:
        async def compact(self, items, *, completions, **kwargs):
            await completions.create(messages=items, model="n2")
            return None

    agent = N2ComputerAgent(
        computer=Computer(), completions=completions, compactor=Compactor()
    )
    _ = [frame async for frame in agent.run("task")]
    assert len(completions.calls) == 2
