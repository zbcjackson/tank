"""Opt-in action-level Jev text admission with governed visual fallback."""

from collections import Counter
from dataclasses import replace

from .contracts import ActionSet, DecisionResult, GoalContract, Snapshot
from .jev import JevSelector, check_eligible
from .model_selector import ModelSelector
from .visual_selector import VisualSelector
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped


def text_candidate_ids(actions: ActionSet) -> frozenset[str]:
    """Mechanical text distinguishability only, never a correctness/authority verdict."""
    ids = {action.id for action in actions.actions}
    if (len(ids) != len(actions.actions) or len(actions.details) != len(actions.actions)
            or {detail.action_id for detail in actions.details} != ids):
        raise SubAgentStopped("ineligible_decision")
    # Normalize equivalent checkbox observations before comparing semantic identities.
    identities = [(d.role, d.label, d.ancestors, d.current_value, d.input_key,
                   tuple(("checkbox:checked" if d.role == "checkbox" and
                          (f.key.startswith("dom:checked:") or
                           f.key == f"checkbox:{d.label}") else f.key, f.value)
                         for f in d.effect), d.changes)
                  for d in actions.details]
    counts = Counter(identities)
    return frozenset(d.action_id for d, identity in zip(actions.details, identities)
                     if counts[identity] == 1 and d.label.strip() and d.label != d.role)


class ActionAdmissionSelector(VisualSelector):
    async def choose(self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
                     context: SubAgentContext) -> DecisionResult:
        if actions.reason not in {"jev_eligible", "visual_required"}:
            return await super().choose(goal, snapshot, actions, context)
        ModelSelector.check(context)
        offered = replace(actions, reason="jev_eligible")
        check_eligible(goal, snapshot, offered)
        if any(item.value is None and item.source == "user" for item in goal.inputs):
            raise SubAgentStopped("missing_user_input")
        admissible = text_candidate_ids(actions)
        if not admissible:
            return await super().choose(goal, snapshot, replace(actions, reason="visual_required"),
                                        context)
        decision = await JevSelector().choose(goal, snapshot, offered, context)
        ModelSelector.check(context)
        accepted = decision.choice == "candidate" and decision.candidate_id in admissible
        context.observe("computer_use_action_admission", reason=actions.reason,
                        candidate_set_id=actions.binding.candidate_set_id,
                        candidates=len(actions.actions), text_candidates=len(admissible),
                        selected_id=decision.candidate_id, accepted=accepted,
                        choice=decision.choice,
                        next_route="text_candidate" if accepted else "visual_fallback")
        if accepted:
            return decision
        # Reuse the unchanged visual-only branch; the admission event above records
        # logical fallback, while the physical model call retains its visual purpose.
        return await super().choose(goal, snapshot, replace(actions, reason="visual_required"),
                                    context)
