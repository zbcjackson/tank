"""Finite semantic templates; candidate IDs select the entire bound action."""

from uuid import uuid4

from .contracts import (
    Action, ActionDetails, ActionSet, Binding, GoalContract, GoalProgress,
    Snapshot,
)


class ActionBuilder:
    def __init__(self, max_candidates: int = 32, *, visual: bool = False) -> None:
        if not 1 <= max_candidates <= 251:
            raise ValueError("Candidate limit must leave room for control options")
        self.max_candidates = max_candidates
        self.visual = visual

    def build(
        self, goal_id: str, version: int, goal: GoalContract, snapshot: Snapshot,
        progress: GoalProgress = GoalProgress(),
    ) -> ActionSet:
        binding = Binding(goal_id, version, snapshot.observation_id, snapshot.scope,
                          snapshot.generation, uuid4().hex)
        if snapshot.scope != goal.scope:
            return ActionSet(binding, (), "scope_mismatch")
        if not snapshot.ready:
            return ActionSet(binding, (), "observation_unavailable")
        if not snapshot.complete:
            return ActionSet(binding, (), "scope_incomplete")
        actions: list[Action] = []
        details: list[ActionDetails] = []
        missing = False
        bindings = dict(progress.input_bindings)
        fields = {
            item.key: [e for e in snapshot.elements
                       if e.kind == "control" and e.enabled and "fill" in e.actions
                       and e.role == "textbox"
                       and e.input_type == item.input_type
                       and (item.field_scope is None
                            or item.field_scope in {name for _, name in e.ancestors})
                       and (item.field_label is None or item.field_label == e.label)
                       and (item.key not in bindings or bindings[item.key] == e.ref)]
            for item in goal.inputs
        }
        inputs_satisfied = all(
            item.value is not None and len(fields[item.key]) == 1
            and fields[item.key][0].value == item.value for item in goal.inputs
        )
        # Prefer pending fills over unverifiable clicks; keep clicks that reveal fields.
        pending_fill = any(
            item.value is not None
            and any(field.value != item.value for field in fields[item.key])
            for item in goal.inputs
        )
        for element in snapshot.elements:
            if element.kind != "control" or not element.enabled:
                continue
            if "fill" in element.actions and "fill" in goal.allowed_operations:
                for item in goal.inputs:
                    if element not in fields[item.key]:
                        continue
                    if item.value is None:
                        missing = True
                        continue
                    if item.value == element.value:
                        continue
                    action = Action(uuid4().hex, element.ref, "fill", item.value)
                    actions.append(action)
                    details.append(ActionDetails(action.id, element.role, element.label,
                                                 element.ancestors, element.value, item.key))
            if "click" in element.actions and "click" in goal.allowed_operations:
                if element.submits and not inputs_satisfied:
                    continue
                effect = goal.completion if element.submits else element.click_effect
                facts = {fact.key: fact.value for fact in snapshot.facts}
                if not effect and not element.click_changes and not element.click_observable:
                    continue
                if (element.click_observable and not effect and not element.click_changes
                        and pending_fill):
                    continue
                if effect and all(facts.get(f.key) == f.value for f in effect):
                    continue
                action = Action(uuid4().hex, element.ref, "click", None)
                actions.append(action)
                details.append(ActionDetails(action.id, element.role, element.label,
                                             element.ancestors, element.value, None, effect,
                                             element.click_changes, element.click_observable))
        if len(actions) > self.max_candidates:
            return ActionSet(binding, (), "candidate_limit", len(actions), truncated=True)
        # Node-bound readback keys identify effects, not human-distinguishable targets.
        identities = [(d.role, d.label, d.ancestors, d.current_value, d.input_key,
                       tuple(("checkbox:checked" if d.role == "checkbox" and
                              (f.key.startswith("dom:checked:") or
                               f.key == f"checkbox:{d.label}") else f.key, f.value)
                             for f in d.effect), d.changes)
                      for d in details]
        ambiguous = len(set(identities)) != len(identities)
        if ambiguous and not self.visual:
            return ActionSet(binding, (), "ambiguous_target", len(actions))
        # Ask for visible missing values before navigating away; known fills may proceed.
        reason = "missing_parameters" if missing and not pending_fill else (
            "jev_eligible" if actions else "no_viable_actions")
        if (self.visual and reason == "jev_eligible"
                and (ambiguous or any(not d.label.strip() or d.label == d.role for d in details))):
            reason = "visual_required"
        if len(actions) == 1 and reason == "jev_eligible":
            detail = details[0]
            explicitly_bound = any(
                item.key == detail.input_key and item.field_label == detail.label
                for item in goal.inputs
            )
            if explicitly_bound:
                reason = "rules_unique"
        return ActionSet(binding, tuple(actions), reason, len(actions), details=tuple(details))
