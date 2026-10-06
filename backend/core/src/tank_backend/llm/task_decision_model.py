"""Borrow the standalone decision model and add task lifetime/accounting only."""

from __future__ import annotations

from copy import deepcopy

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .decision_model import ChoiceResult, DecisionModel, DecisionModelError
from .model_call import TaskModelCallRunner
from .model_data import ModelRequest


class TaskDecisionModel:
    def __init__(self, task_id: str, context: SubAgentContext, model: DecisionModel):
        self._model = model
        self._calls = TaskModelCallRunner(task_id, context)

    async def choose(
        self, *, state: dict[str, object], instructions: str, options: dict[str, object]
    ) -> ChoiceResult:
        state, options = deepcopy(state), deepcopy(options)
        profile = self._model.profile
        request = ModelRequest(
            profile.url,
            profile.model,
            {
                "model": profile.model,
                "state": state,
                "questions": {
                    "next_action": {
                        "type": "choice",
                        "instructions": instructions,
                        "criteria": options,
                    }
                },
            },
        )
        try:
            return await self._calls.run(
                request,
                lambda: self._model.choose(state=state, instructions=instructions, options=options),
            )
        except DecisionModelError as exc:
            self._calls.check()
            raise SubAgentStopped(str(exc)) from None

    async def aclose(self) -> None:
        await self._calls.aclose()
