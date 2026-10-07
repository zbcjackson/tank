"""Finite semantic templates; candidate IDs select the entire bound action."""

from uuid import uuid4

from .contracts import (
    Action, ActionDetails, ActionSet, Binding, GoalContract, GoalContractV2, GoalProgress,
    Milestone, Snapshot,
)


class ActionBuilder:
    def build_goal(
        self, goal_id: str, version: int, goal: GoalContractV2, snapshot: Snapshot,
        progress: GoalProgress = GoalProgress(),
    ) -> ActionSet:
        binding = Binding(goal_id, version, snapshot.observation_id, snapshot.scope,
                          snapshot.generation, uuid4().hex)
        if snapshot.scope != goal.scope:
            return ActionSet(binding, (), "scope_mismatch")
        if not snapshot.ready or not snapshot.complete:
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
                if not effect or all(facts.get(f.key) == f.value for f in effect):
                    continue
                action = Action(uuid4().hex, element.ref, "click", None)
                actions.append(action)
                details.append(ActionDetails(action.id, element.role, element.label,
                                             element.ancestors, element.value, None, effect))
        if len(actions) > 32:
            return ActionSet(binding, (), "candidate_limit", len(actions), truncated=True)
        identities = [(d.role, d.label, d.ancestors, d.current_value, d.input_key, d.effect)
                      for d in details]
        if len(set(identities)) != len(identities):
            return ActionSet(binding, (), "ambiguous_target", len(actions))
        reason = "jev_eligible" if actions else (
            "missing_parameters" if missing else "no_viable_actions")
        return ActionSet(binding, tuple(actions), reason, len(actions), details=tuple(details))

    def build(
        self,
        goal_id: str,
        version: int,
        goal: GoalContract,
        milestone: Milestone,
        snapshot: Snapshot,
    ) -> ActionSet:
        binding = Binding(
            goal_id,
            version,
            snapshot.observation_id,
            snapshot.scope,
            snapshot.generation,
            uuid4().hex,
        )
        value = next((item.value for item in goal.inputs if item.key == milestone.input_key), None)
        if snapshot.scope != goal.scope:
            return ActionSet(binding, (), "scope_mismatch")
        if not snapshot.ready:
            return ActionSet(binding, (), "observation_unavailable")
        if not snapshot.complete:
            return ActionSet(binding, (), "scope_incomplete")
        if milestone.operation == "fill" and value is None:
            return ActionSet(binding, (), "missing_parameters")
        candidates = [
            element
            for element in snapshot.elements
            if element.kind == "control"
            and element.role == milestone.role
            and element.enabled
            and milestone.operation in element.actions
        ]
        exact = [element for element in candidates if element.label == milestone.label]
        if len(exact) > 1:
            return ActionSet(binding, (), "ambiguous_target")
        selected = exact or candidates
        if len({element.label for element in selected}) != len(selected):
            return ActionSet(binding, (), "ambiguous_target")
        if not selected:
            return ActionSet(binding, (), "no_viable_actions")
        total = len(selected)
        selected = sorted(selected, key=lambda element: (element.label, element.ref))[:32]
        return ActionSet(
            binding,
            tuple(
                Action(uuid4().hex, element.ref, milestone.operation, value) for element in selected
            ),
            "rules_unique" if len(exact) == 1 else "jev_eligible",
            total_candidates=total,
            truncated=total > len(selected),
        )
