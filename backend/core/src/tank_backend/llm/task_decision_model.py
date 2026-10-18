"""Borrow the standalone decision model and add task lifetime/accounting only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import TypeVar

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .decision_model import BoxResult, ChoiceResult, DecisionModel, DecisionModelError
from .model_call import TaskModelCallRunner, get_model_call
from .model_data import ModelImageAsset, ModelRequest

T = TypeVar("T")


class TaskDecisionModel:
    def __init__(self, task_id: str, context: SubAgentContext, model: DecisionModel):
        self._model = model
        self._calls = TaskModelCallRunner(task_id, context)

    @property
    def images_enabled(self) -> bool:
        return self._model.profile.images

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
        return await self._execute(
            request,
            lambda: self._model.choose(state=state, instructions=instructions, options=options),
        )

    async def choose_image(
        self,
        *,
        state: dict[str, object],
        image: ModelImageAsset,
        instructions: str,
        options: dict[str, object],
    ) -> ChoiceResult:
        from .decision_image import image_choice_questions, image_request

        self._calls.check()
        state, options = deepcopy(state), deepcopy(options)
        try:
            request = image_request(
                self._model.profile,
                state,
                image,
                image_choice_questions(instructions, options),
            )
        except (ValueError, OSError):
            raise SubAgentStopped("invalid_decision_image") from None
        return await self._execute(
            request,
            lambda: self._model.choose_image(
                state=state, image=image, instructions=instructions, options=options
            ),
        )

    async def _execute(self, request: ModelRequest, invoke: Callable[[], Awaitable[T]]) -> T:
        try:
            return await self._calls.run(request, invoke)
        except DecisionModelError as exc:
            record = get_model_call(self._calls.task_id)
            self._calls.context.observe(
                "decision_error",
                task_id=self._calls.task_id,
                call_id=record.call_id if record is not None else None,
                **exc.diagnostics,
            )
            self._calls.check()
            raise SubAgentStopped(str(exc)) from None

    async def locate_image(
        self,
        *,
        state: dict[str, object],
        image: ModelImageAsset,
        target: str,
    ) -> BoxResult:
        from .decision_image import box_questions, image_request

        self._calls.check()
        state = deepcopy(state)
        try:
            if self._model.profile.model != "jev-1.14.0":
                raise ValueError("unsupported Box version")
            request = image_request(self._model.profile, state, image, box_questions(target))
        except (ValueError, OSError):
            raise SubAgentStopped("invalid_decision_image") from None
        return await self._execute(
            request, lambda: self._model.locate_image(state=state, image=image, target=target)
        )

    async def aclose(self) -> None:
        await self._calls.aclose()
