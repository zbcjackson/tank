"""Historical raw protocol replay only; production models use native SDK calls."""
from __future__ import annotations
import math
from uuid import uuid4
from dataclasses import dataclass

import httpx
from agent_computer_use.contracts import ActionSet, DecisionResult
from agent_computer_use.jev import CONTROLS
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.llm.model_call import TaskModelCallRunner
from tank_backend.llm.model_data import ModelRequest, json_object, parse_chat_usage

@dataclass(frozen=True)
class _Response:
    payload: dict[str, object]
    input_tokens: int
    output_tokens: int

class TaskJSONModel:
    def __init__(self, task_id: str, context: SubAgentContext, url: str, model: str,
                 credential: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.url, self.model, self.context, self.task_id = url, model, context, task_id
        self.calls = TaskModelCallRunner(task_id, context)
        self.client = httpx.AsyncClient(transport=transport or httpx.AsyncHTTPTransport(),
            headers={"Authorization": "Bearer " + credential}, follow_redirects=False,
            trust_env=False, timeout=30)

    async def request(self, payload: dict[str, object]) -> dict[str, object]:
        # Experimental admission remains outside production SDK bookkeeping.
        await self.context.runtime.write_audit(ExecutionRecord(
            self.task_id, uuid4().hex, "raw_replay", "not_sent", category="model", phase="prepared"))
        self.context.check("network")
        async def invoke() -> _Response:
            response = await self.client.post(self.url, json=payload)
            response.raise_for_status()
            data = json_object(response.content)
            usage = data.get("usage")
            if self.url.endswith("systemone"):
                if not isinstance(usage, dict):
                    raise ValueError("unknown usage")
                inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
                if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
                    raise ValueError("unknown usage")
            else:
                inputs, outputs = parse_chat_usage(usage)
            return _Response(data, inputs, outputs)
        result = await self.calls.run(ModelRequest(self.url, self.model, payload), invoke)
        return result.payload

    async def aclose(self) -> None:
        await self.calls.aclose()
        await self.client.aclose()


def parse_choice(
    response: dict[str, object], actions: ActionSet, version: str,
) -> DecisionResult:
    """Validate a Jev wire decision after host accounting; shared by frozen replay."""
    criteria = {action.id for action in actions.actions} | set(CONTROLS)
    answers = response.get("answers")
    if (response.get("model") != version or not isinstance(answers, dict)
            or set(answers) != {"next_action"}
            or not isinstance(answers.get("next_action"), dict)):
        raise SubAgentStopped("invalid_decision")
    answer = answers["next_action"]
    choice = answer.get("choice")
    probabilities = answer.get("probabilities")
    if (answer.get("type") != "choice" or not isinstance(choice, str)
            or choice not in criteria or not probability(answer.get("confidence"))
            or not isinstance(probabilities, dict) or set(probabilities) != set(criteria)
            or not all(probability(value) for value in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02)
            or probabilities[choice] != max(probabilities.values())):
        raise SubAgentStopped("invalid_decision")
    for control in CONTROLS:
        if choice == control:
            return DecisionResult(actions.binding, control)
    if isinstance(choice, str) and any(action.id == choice for action in actions.actions):
        return DecisionResult(actions.binding, "candidate", choice)
    raise SubAgentStopped("invalid_decision")


def probability(value: object) -> bool:
    return type(value) in (int, float) and isinstance(value, (int, float)) and 0 <= value <= 1

