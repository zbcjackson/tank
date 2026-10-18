"""Bounded same-candidate selection through host-owned models; no tools or clients."""

from __future__ import annotations

import json

from tank_backend.llm.model_call import model_purpose
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped
from tank_backend.llm.model_data import json_object

from .contracts import ActionSet, DecisionResult, GoalContract, Snapshot
from .jev import JevSelector, check_eligible
from .model_view import CONTROLS, candidate_aliases, decision_question


class ModelSelector:
    def __init__(self, *, use_jev: bool) -> None:
        self.primary = JevSelector() if use_jev else None

    @staticmethod
    def check(context: SubAgentContext) -> None:
        context.check("desktop")
        context.check("network")
        if context.budget.unknown_calls:
            raise SubAgentStopped("unknown_usage")

    async def choose(
        self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
        context: SubAgentContext,
    ) -> DecisionResult:
        self.check(context)
        check_eligible(goal, snapshot, actions)
        model = context.runtime.model
        if model is None:
            raise SubAgentStopped("model_unavailable")
        if self.primary is not None:
            # Only valid, explicitly non-action decisions may fall through. Hard failures propagate.
            context.observe("computer_use_selection", stage="jev", phase="start")
            decision = await self.primary.choose(goal, snapshot, actions, context)
            self.check(context)
            context.observe("computer_use_selection", stage="jev", phase="result", choice=decision.choice)
            if decision.choice == "candidate":
                return decision
        stage = "fallback" if self.primary is not None else "llm"
        context.observe("computer_use_selection", stage=stage, phase="start")
        with model_purpose("computer_use.fallback" if self.primary is not None else "computer_use.llm"):
            text = await model.complete([
                {"role": "system", "content": 'Return only JSON {"choice":"one offered key"}. '
                 'Answer the supplied choice question. Do not execute actions or use tools.'},
                {"role": "user", "content": json.dumps(decision_question(goal, snapshot, actions),
                                                        ensure_ascii=False, allow_nan=False)},
            ])
        self.check(context)
        try:
            data = json_object(text.encode())
            choice = data.get("choice")
            if set(data) != {"choice"} or not isinstance(choice, str):
                raise ValueError("expected a single choice")
            if choice in CONTROLS:
                # Literal narrowing avoids treating an arbitrary provider string as a control.
                if choice not in ("none", "ambiguous", "need_more_context", "escalate"):
                    raise ValueError("unsupported control")
                result = DecisionResult(actions.binding, choice)
            elif (action := candidate_aliases(actions).get(choice)) is not None:
                context.observe("computer_use_proposal", source="text", model_choice=choice,
                                action_id=action.id, candidate_set_id=actions.binding.candidate_set_id)
                result = DecisionResult(actions.binding, "candidate", action.id)
            else:
                raise ValueError("choice outside offered set")
        except ValueError:
            raise SubAgentStopped("invalid_decision") from None
        context.observe("computer_use_selection", stage=stage, phase="result", choice=result.choice)
        return result
