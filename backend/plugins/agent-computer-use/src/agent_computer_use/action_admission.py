"""Opt-in action-level Jev text admission with governed visual fallback."""

from collections import Counter
from dataclasses import replace
from math import isfinite

from .contracts import ActionDetails, ActionSet, DecisionResult, GoalContract, Snapshot
from .jev import JevSelector, check_eligible
from .model_selector import ModelSelector
from .visual_selector import VisualSelector
from tank_backend.agents.subagent import SubAgentContext, SubAgentStopped


def _text_identity(detail: ActionDetails) -> tuple[object, ...]:
    # Normalize node-bound checkbox keys; they do not distinguish human targets.
    return (detail.role, detail.label, detail.ancestors, detail.current_value, detail.input_key,
            tuple(("checkbox:checked" if detail.role == "checkbox" and
                   (fact.key.startswith("dom:checked:") or
                    fact.key == f"checkbox:{detail.label}") else fact.key, fact.value)
                  for fact in detail.effect), detail.changes)


def text_candidate_ids(actions: ActionSet) -> frozenset[str]:
    """Mechanical text distinguishability only, never a correctness/authority verdict."""
    ids = {action.id for action in actions.actions}
    if (len(ids) != len(actions.actions) or len(actions.details) != len(actions.actions)
            or {detail.action_id for detail in actions.details} != ids):
        raise SubAgentStopped("ineligible_decision")
    identities = [_text_identity(detail) for detail in actions.details]
    counts = Counter(identities)
    return frozenset(d.action_id for d, identity in zip(actions.details, identities)
                     if counts[identity] == 1 and d.label.strip() and d.label != d.role)


def spatial_candidate_ids(
    goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
) -> frozenset[str]:
    """One strict extremum in a fully observed, otherwise equivalent DOM group."""
    hint, viewport = goal.spatial_hint, snapshot.viewport
    if (hint is None or not hint.label.strip() or hint.label == hint.role
            or viewport is None or len(viewport) != 2
            or any(type(n) is not int or n <= 0 for n in viewport)):
        return frozenset()
    peers = [detail for detail in actions.details
             if (detail.role, detail.label) == (hint.role, hint.label)]
    if len(peers) < 2 or len({_text_identity(detail) for detail in peers}) != 1:
        return frozenset()
    elements = {element.ref: element for element in snapshot.elements}
    targets = {action.id: action for action in actions.actions}
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for peer in peers:
        action = targets[peer.action_id]
        element = elements.get(action.target_ref)
        if element is None or element.source != "dom" or action.operation != "click":
            return frozenset()
        box = element.bounds
        if (box is None or len(box) != 4
                or any(type(n) not in (int, float) or not isfinite(n) for n in box)):
            return frozenset()
        x, y, width, height = box
        if (x < 0 or y < 0 or width <= 0 or height <= 0
                or x + width > viewport[0] or y + height > viewport[1]):
            return frozenset()
        boxes[peer.action_id] = box
    axis = 0 if hint.relation in {"leftmost", "rightmost"} else 1
    low = hint.relation in {"leftmost", "topmost"}
    return frozenset(key for key, box in boxes.items() if all(
        (box[axis] + box[axis + 2] <= other[axis] if low else
         box[axis] >= other[axis] + other[axis + 2])
        for other_key, other in boxes.items() if other_key != key))


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
        spatial = spatial_candidate_ids(goal, snapshot, actions)
        admissible |= spatial
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
                        next_route="text_candidate" if accepted else "visual_fallback",
                        **({"spatial_candidates": len(spatial)} if goal.spatial_hint else {}))
        if accepted:
            return decision
        # Reuse the unchanged visual-only branch; the admission event above records
        # logical fallback, while the physical model call retains its visual purpose.
        return await super().choose(goal, snapshot, replace(actions, reason="visual_required"),
                                    context)
