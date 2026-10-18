"""UI choice semantics over the core-owned decision capability; no provider configuration."""

from __future__ import annotations

from typing import cast

from tank_backend.llm.model_call import model_purpose
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped

from .contracts import (
    ActionSet, DecisionResult, GoalContract, Snapshot,
)
from .model_view import candidate_aliases, decision_question


def check_eligible(goal: GoalContract, snapshot: Snapshot, actions: ActionSet) -> None:
    binding = actions.binding
    if (not snapshot.ready or not snapshot.complete or actions.truncated or not actions.actions
            or actions.reason != "jev_eligible" or snapshot.scope != goal.scope
            or binding.scope != snapshot.scope or binding.observation_id != snapshot.observation_id
            or binding.generation != snapshot.generation):
        raise SubAgentStopped("ineligible_decision")


class JevSelector:
    async def choose(self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
                     context: SubAgentContext) -> DecisionResult:
        context.check("desktop")
        check_eligible(goal, snapshot, actions)
        model = context.runtime.decision_model
        if model is None:
            raise SubAgentStopped("model_unavailable")
        payload = decision_question(goal, snapshot, actions)
        questions = cast(dict[str, dict[str, object]], payload["questions"])
        question = questions["next_action"]
        with model_purpose('computer_use.jev'):
            result = await model.choose(state=cast(dict[str, object], payload["state"]),
                                        instructions=cast(str, question["instructions"]),
                                        options=cast(dict[str, object], question["criteria"]))
        context.observe("computer_use_decision", confidence=result.confidence,
                        probabilities=result.probabilities, candidates=len(actions.actions),
                        candidate_set_id=actions.binding.candidate_set_id)
        if result.choice in ("none", "ambiguous", "need_more_context", "escalate"):
            return DecisionResult(actions.binding, result.choice, confidence=result.confidence,
                                  probabilities=tuple(result.probabilities.items()))
        action = candidate_aliases(actions).get(result.choice)
        if action is not None:
            context.observe("computer_use_proposal", source="jev", model_choice=result.choice,
                            action_id=action.id, candidate_set_id=actions.binding.candidate_set_id)
            return DecisionResult(actions.binding, "candidate", action.id, result.confidence,
                                  tuple(result.probabilities.items()))
        raise SubAgentStopped("invalid_decision")
