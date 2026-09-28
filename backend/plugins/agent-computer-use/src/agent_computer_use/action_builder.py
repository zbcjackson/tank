"""Finite semantic templates; candidate IDs select the entire bound action."""

from uuid import uuid4

from .contracts import Action, ActionSet, Binding, GoalContract, Milestone, Snapshot


class ActionBuilder:
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
        if len(selected) > 32:
            return ActionSet(binding, (), "candidate_limit")
        return ActionSet(
            binding,
            tuple(
                Action(uuid4().hex, element.ref, milestone.operation, value) for element in selected
            ),
            "rules_unique" if len(exact) == 1 else "jev_eligible",
        )
