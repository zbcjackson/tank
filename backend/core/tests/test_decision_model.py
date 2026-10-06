"""Provider calls are usable independently of task/runtime/HTTP governance."""

import httpx2
import pytest


def response(choice="a"):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": choice,
                "confidence": 1.0,
                "probabilities": {"a": 1.0, "b": 0.0},
            }
        },
        "usage": {"input_tokens": 7, "output_tokens": 2},
    }


async def test_standalone_decision_model_has_no_task_or_custom_transport(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a"
        assert (result.input_tokens, result.output_tokens) == (7, 2)
        assert len(calls) == 1
        assert calls[0].headers["authorization"] == "Bearer secret"
    finally:
        await model.aclose()


async def test_bad_choice_retains_known_usage(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError) as error:
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert (error.value.input_tokens, error.value.output_tokens) == (7, 2)
    finally:
        await model.aclose()


@pytest.mark.parametrize("failure", ["disabled", "enter", "update", "exit"])
async def test_optional_observability_never_changes_decision(monkeypatch, failure):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    class Span:
        def __enter__(self):
            if failure == "enter":
                raise RuntimeError("tracing unavailable")
            return self

        def update(self, **kwargs):
            if failure == "update":
                raise RuntimeError("tracing unavailable")

        def __exit__(self, *args):
            if failure == "exit":
                raise RuntimeError("tracing unavailable")

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(
        telemetry, "get_langfuse", lambda: None if failure == "disabled" else Client()
    )
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a" and result.input_tokens == 7 and len(calls) == 1
    finally:
        await model.aclose()


async def test_failed_decision_trace_keeps_usage_and_error_level(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    updates = []

    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def update(self, **kwargs):
            updates.append(kwargs)

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(telemetry, "get_langfuse", lambda: Client())
    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError):
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert any(u.get("level") == "ERROR" for u in updates)
        assert any(
            u.get("usage_details") == {"input_tokens": 7, "output_tokens": 2} for u in updates
        )
    finally:
        await model.aclose()


async def test_choice_is_bound_to_options_at_invocation(monkeypatch):
    import json

    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    options: dict[str, object] = {"a": "A", "b": "B"}

    async def respond(request):
        assert set(json.loads(request.content)["questions"]["next_action"]["criteria"]) == {
            "a",
            "b",
        }
        options["late"] = "Not offered in this invocation"
        data = response("late")
        data["answers"]["next_action"]["probabilities"] = {"a": 0.0, "b": 0.0, "late": 1.0}
        return httpx2.Response(200, json=data)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError, match="invalid_decision"):
            await model.choose(state={}, instructions="Choose", options=options)
    finally:
        await model.aclose()


async def test_task_choice_capture_and_sdk_share_input_snapshot(monkeypatch):
    import asyncio
    import json

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    ticket, option = {"text": "original"}, {"label": "original"}
    state: dict[str, object] = {"ticket": ticket}
    options: dict[str, object] = {"a": option, "b": "B"}
    captured = []

    class Capture:
        async def request(self, call_id, request):
            import copy

            captured.append(copy.deepcopy(request.parameters))
            request.parameters["state"] = {"recorder": "redacted"}
            ticket["text"] = "changed"
            option["label"] = "changed"
            options["late"] = "Not in the captured question"
            await asyncio.sleep(0)

        async def response(self, call_id, response):
            pass

    async def respond(request):
        assert json.loads(request.content) == captured[0]
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    context = SubAgentContext(SubAgentAuthorization(frozenset({"network"})),
                              SubAgentBudget(), asyncio.Event(), model_capture=Capture())
    task_model = TaskDecisionModel("task", context, model)
    try:
        result = await task_model.choose(state=state, instructions="Choose", options=options)
        assert result.choice == "a" and context.budget.total_tokens == 9
    finally:
        await task_model.aclose()
        await model.aclose()
