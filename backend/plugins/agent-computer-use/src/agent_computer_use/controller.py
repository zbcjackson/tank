"""Task-owned host loop. Channels provide evidence, never completion claims."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from typing import Protocol
from uuid import uuid4

from pydantic import JsonValue, ValidationError

from tank_backend.agents.subagent import (
    SubAgentCancelled,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)
from tank_backend.agents.task_result import TaskResult, TaskStatus
from tank_backend.agents.task_runtime import TaskOperation

from .action_builder import ActionBuilder
from .contracts import (
    Action,
    ActionSet,
    ActionDetails,
    AdvisorResult,
    Binding,
    DecisionResult,
    DispatchReceipt,
    Fact,
    GoalContract,
    GoalProgress,
    Snapshot,
)


class ObservationSource(Protocol):
    async def observe(self, scope: str, context: SubAgentContext, /) -> Snapshot: ...


class ActionExecutor(Protocol):
    async def is_current(
        self,
        binding: Binding,
        action: Action,
        context: SubAgentContext,
        /,
    ) -> bool: ...

    async def dispatch(
        self,
        binding: Binding,
        action: Action,
        context: SubAgentContext,
        /,
    ) -> DispatchReceipt:
        """Recheck authority and reference at native dispatch; never retry unknown effects."""
        ...


class Selector(Protocol):
    async def choose(
        self,
        goal: GoalContract,
        snapshot: Snapshot,
        actions: ActionSet,
        context: SubAgentContext,
        /,
    ) -> DecisionResult: ...


class Advisor(Protocol):
    async def assist(
        self,
        request: SubAgentRequest,
        goal: GoalContract,
        snapshot: Snapshot,
        actions: ActionSet,
        context: SubAgentContext,
        /,
    ) -> AdvisorResult: ...


def achieved(snapshot: Snapshot, predicates: tuple[Fact, ...]) -> bool:
    facts = {fact.key: fact.value for fact in snapshot.facts}
    return (
        snapshot.ready
        and snapshot.complete
        and all(facts.get(predicate.key) == predicate.value for predicate in predicates)
    )


def effect_achieved(snapshot: Snapshot, action: Action, detail: ActionDetails) -> bool:
    if not snapshot.ready or not snapshot.complete:
        return False
    values = {element.ref: element.value for element in snapshot.elements}
    if action.operation == "fill":
        return action.target_ref in values and values[action.target_ref] == action.value
    if detail.effect:
        return achieved(snapshot, detail.effect)
    facts = {fact.key: fact.value for fact in snapshot.facts}
    return any(change.source_ref in values and change.key in facts
               and values[change.source_ref] == facts[change.key] != change.before
               for change in detail.changes)


class ComputerUseController:
    """Single task instance; budgets and authorization remain in the supplied context."""

    def __init__(
        self,
        source: ObservationSource,
        executor: ActionExecutor,
        *,
        selector: Selector | None = None,
        advisor: Advisor | None = None,
        completion_keys: frozenset[str] | None = None,
        max_candidates: int = 32,
    ) -> None:
        self.source, self.executor = source, executor
        self.selector, self.advisor = selector, advisor
        self.completion_keys = completion_keys
        self.builder = ActionBuilder(max_candidates)
        self.version = 1
        self.goal_id = uuid4().hex
        self.task_id = ""
        self.evidence: list[JsonValue] = []
        self.bindings: list[Binding] = []
        self.receipts: list[DispatchReceipt] = []
        self.pending_effect = False
        self.observation_ids: set[str] = set()
        self.generation = -1
        self.advisor_calls = 0
        self.last_review_action = 0
        self.progress = GoalProgress()
        self.started = False
        self.observation: TaskOperation[str, Snapshot] | None = None
        self.dispatch: TaskOperation[tuple[Binding, Action], DispatchReceipt] | None = None

    def result(self, status: TaskStatus, reason: str) -> TaskResult:
        if self.pending_effect:
            status = "unknown"
        elif status == "stopped" and self.progress.verified_actions:
            status = "partial"
        return TaskResult(
            status=status,
            summary=reason,
            reason=reason,
            details={
                "task_id": self.task_id,
                "evidence": list(self.evidence),
                "goal_id": self.goal_id,
                "goal_version": self.version,
                "receipts": [
                    {
                        "action_id": item.action_id,
                        "status": item.status,
                        "observation_id": binding.observation_id,
                        "goal_version": binding.goal_version,
                        "candidate_set_id": binding.candidate_set_id,
                        "scope": binding.scope,
                        "generation": binding.generation,
                    }
                    for item, binding in zip(self.receipts, self.bindings, strict=True)
                ],
                "pending_effect": self.pending_effect,
                "progress": {**asdict(self.progress),
                             "verified_actions": list(self.progress.verified_actions),
                             "verified_outcomes": list(self.progress.verified_outcomes),
                             "input_bindings": [list(item) for item in self.progress.input_bindings]},
            },
        )

    async def observe(
        self, goal: GoalContract, context: SubAgentContext,
    ) -> Snapshot:
        assert self.observation is not None
        snapshot = await context.runtime.execute(self.observation, goal.scope)
        if snapshot.scope != goal.scope:
            raise SubAgentStopped("scope_mismatch")
        if snapshot.observation_id in self.observation_ids or snapshot.generation < self.generation:
            raise SubAgentStopped("stale_observation")
        self.observation_ids.add(snapshot.observation_id)
        self.generation = snapshot.generation
        return snapshot

    def register_operations(self, context: SubAgentContext) -> None:
        async def preflight(value: tuple[Binding, Action]) -> None:
            if not await self.executor.is_current(*value, context):
                raise SubAgentStopped("stale_reference")

        async def dispatch(value: tuple[Binding, Action]) -> DispatchReceipt:
            binding, action = value
            # Journal at the admitted boundary, before a possible external effect.
            self.bindings.append(binding)
            self.receipts.append(DispatchReceipt(action.id, "unknown"))
            self.pending_effect = True
            self.progress = replace(self.progress, recent_action=action, pending_action=action)
            return await self.executor.dispatch(binding, action, context)

        self.observation = TaskOperation(
            "computer_use.observe", frozenset({"desktop"}), "read",
            lambda scope: self.source.observe(scope, context),
        )
        self.dispatch = TaskOperation(
            "computer_use.dispatch", frozenset({"desktop"}), "action", dispatch, preflight,
        )
        context.runtime.register(self.observation)
        context.runtime.register(self.dispatch)

    async def run(self, request: SubAgentRequest, context: SubAgentContext) -> TaskResult:
        if self.started:
            raise RuntimeError("A controller cannot restart a task or reset its budget")
        self.started = True
        self.task_id = request.task_id
        try:
            context.check("desktop")
            context.runtime.bind(request.task_id)
            context.runtime.restrict_operations(
                actions=min(32, context.max_steps) if context.max_steps is not None else 32,
                observations=64,
            )
            self.register_operations(context)
            if request.task_input is None:
                return self.result("needs_input", "goal_contract_required")
            try:
                goal = GoalContract.from_input(request.task_input)
            except (ValueError, ValidationError):
                return self.result("needs_input", "invalid_goal_contract")
            if goal.authorization_ref not in {"current_task", request.task_id}:
                raise SubAgentStopped("authorization_mismatch")
            self.goal_id = goal.goal_id
            return await self.loop(request, goal, context)
        except asyncio.CancelledError as exc:
            raise SubAgentCancelled(self.result("stopped", "cancelled")) from exc
        except SubAgentStopped as exc:
            return self.result("stopped", exc.reason)
        except TimeoutError:
            return self.result("stopped", "timeout")
        except Exception as exc:
            # Preserve a possibly sent action even if a channel raises before returning a receipt.
            context.observe("computer_use_error", error_type=type(exc).__name__)
            return self.result("stopped", "backend_error")

    async def loop(
        self, request: SubAgentRequest, goal: GoalContract, context: SubAgentContext,
    ) -> TaskResult:
        if any((fact.key not in self.completion_keys if self.completion_keys is not None
                else not fact.key.startswith("status:")) for fact in goal.completion):
            return self.result("needs_input", "unsupported_completion_evidence")
        snapshot = await self.observe(goal, context)
        visited: dict[tuple[object, ...], int] = {}
        seen_evidence: set[tuple[str, str, str]] = set()
        while True:
            context.check("desktop")
            # A changed readout is a local effect, not evidence of goal advancement.
            conditions = (*goal.completion, *(f for item in goal.outcomes for f in item.conditions))
            markers = {("fact", f.key, f.value) for f in conditions
                       if snapshot.ready and snapshot.complete and f in snapshot.facts}
            values = {e.ref: e.value for e in snapshot.elements}
            bindings = dict(self.progress.input_bindings)
            markers.update(("input", item.key, item.value) for item in goal.inputs
                           if snapshot.ready and snapshot.complete and item.value is not None
                           and item.key in bindings and values.get(bindings[item.key]) == item.value)
            if markers - seen_evidence:
                self.progress = replace(self.progress, unverified_goal_steps=0)
            seen_evidence.update(markers)
            outcomes: set[str] = set()
            for _ in goal.outcomes:
                for item in goal.outcomes:
                    if set(item.depends_on) <= outcomes and achieved(snapshot, item.conditions):
                        outcomes.add(item.id)
            self.progress = replace(self.progress, verified_outcomes=tuple(sorted(outcomes)))
            if achieved(snapshot, goal.completion) and len(outcomes) == len(goal.outcomes):
                self.evidence.append({"observation_id": snapshot.observation_id,
                                      "goal_version": self.version,
                                      "completion": [item.key for item in goal.completion]})
                return self.result("completed", "goal_verified")
            state = (self.version, snapshot.ready, snapshot.complete,
                tuple((e.role, e.label, e.ancestors, e.value, e.enabled, e.actions)
                      for e in snapshot.elements), snapshot.facts,
            )
            repeated = state in visited
            if repeated:
                self.progress = replace(self.progress, no_progress=self.progress.no_progress + 1)
                if (self.advisor is None
                        or visited[state] == len(self.progress.verified_actions)):
                    return self.result("stopped", "no_progress")
            visited[state] = len(self.progress.verified_actions)
            actions = replace(self.builder.build(self.goal_id, self.version, goal, snapshot,
                                                        self.progress),
                              progress=self.progress)
            if repeated:
                actions = replace(actions, reason="repeated_state")
            elif (self.progress.unverified_goal_steps >= 3
                    and len(self.progress.verified_actions) - self.last_review_action >= 3):
                actions = replace(actions, reason="goal_progress_unverified")
            context.observe("computer_use_route", goal_id=self.goal_id, goal_version=self.version,
                            observation_id=snapshot.observation_id, reason=actions.reason)
            action = actions.actions[0] if actions.reason == "rules_unique" else None
            if actions.reason == "jev_eligible" and self.selector is not None:
                context.check("desktop")
                decision = await self.selector.choose(goal, snapshot, actions, context)
                context.check("desktop")
                if decision.binding != actions.binding:
                    raise SubAgentStopped("stale_decision")
                if decision.choice == "candidate":
                    action = self.candidate(actions, decision.candidate_id)
                elif decision.choice not in {"none", "ambiguous", "need_more_context", "escalate"}:
                    raise SubAgentStopped("invalid_decision")
                else:
                    actions = replace(actions, reason=decision.choice)
            if action is None:
                if any(item.value is None and item.source == "user" for item in goal.inputs):
                    return self.result("needs_input", "missing_user_input")
                if actions.reason == "none":
                    return self.result("stopped", "none")
                if (actions.reason in {"need_more_context", "ambiguous"}
                        or self.advisor is not None and actions.reason in {
                            "observation_unavailable", "scope_incomplete", "ambiguous_target",
                        }):
                    snapshot = await self.observe(goal, context)
                    continue
                advice = await self.advise(request, goal, snapshot, actions, context)
                if advice is None:
                    return self.result("needs_input" if actions.reason == "missing_parameters"
                                       else "stopped", actions.reason)
                if advice.kind == "inputs":
                    missing = {item.key for item in goal.inputs
                               if item.value is None and item.source == "generated"}
                    supplied = {item.key: item.value for item in advice.inputs}
                    if (not supplied or len(supplied) != len(advice.inputs)
                            or not supplied.keys() <= missing):
                        raise SubAgentStopped("invalid_goal_patch")
                    goal = GoalContract.from_input({
                        **goal.model_dump(mode="json"),
                        "inputs": [{**item.model_dump(mode="json"),
                                    "value": supplied.get(item.key, item.value)}
                                   for item in goal.inputs],
                    })
                    self.version += 1
                    self.progress = replace(self.progress, goal_version=self.version)
                    snapshot = await self.observe(goal, context)
                    continue
                if advice.kind == "need_observation":
                    snapshot = await self.observe(goal, context)
                    continue
                if advice.kind == "needs_user_input":
                    return self.result("needs_input", "needs_user_input")
                if advice.kind != "candidate":
                    return self.result("stopped", "advisor_unable")
                action = self.candidate(actions, advice.candidate_id)
            detail = next(item for item in actions.details if item.action_id == action.id)
            assert self.dispatch is not None
            receipt = await context.runtime.execute(self.dispatch, (actions.binding, action))
            if receipt.action_id != action.id or receipt.status not in {"not_sent", "sent", "unknown"}:
                raise SubAgentStopped("invalid_receipt")
            self.receipts[-1] = receipt
            if receipt.status == "not_sent":
                self.pending_effect = False
                self.progress = replace(self.progress, pending_action=None)
                return self.result("stopped", "not_sent")
            for attempt in range(3):
                if attempt:
                    await asyncio.sleep(0.05)
                snapshot = await self.observe(goal, context)
                verified = effect_achieved(snapshot, action, detail)
                if verified:
                    self.pending_effect = False
                    inputs = dict(self.progress.input_bindings)
                    if detail.input_key is not None:
                        inputs[detail.input_key] = action.target_ref
                    self.progress = replace(
                        self.progress, pending_action=None,
                        verified_actions=(*self.progress.verified_actions, action.id),
                        input_bindings=tuple(inputs.items()),
                        unverified_goal_steps=self.progress.unverified_goal_steps + 1,
                    )
                    self.evidence.append({"action_id": action.id,
                                          "observation_id": snapshot.observation_id})
                    break
            if self.pending_effect:
                return self.result("unknown", "effect_unknown")

    async def advise(
        self,
        request: SubAgentRequest,
        goal: GoalContract,
        snapshot: Snapshot,
        actions: ActionSet,
        context: SubAgentContext,
        /,
    ) -> AdvisorResult | None:
        if self.advisor is None:
            return None
        context.check("desktop")
        if self.advisor_calls >= 4:
            raise SubAgentStopped("advisor_limit")
        self.advisor_calls += 1
        context.observe("computer_use_advisor", phase="started", reason=actions.reason,
                        call_number=self.advisor_calls, observation_id=snapshot.observation_id)
        advice = await self.advisor.assist(request, goal, snapshot, actions, context)
        context.check("desktop")
        if advice.binding != actions.binding:
            raise SubAgentStopped("stale_advice")
        if (
            advice.kind not in {"inputs", "candidate", "need_observation", "needs_user_input", "unable"}
            or advice.kind != "inputs"
            and advice.inputs
            or advice.kind != "candidate"
            and advice.candidate_id is not None
        ):
            raise SubAgentStopped("invalid_advice")
        context.observe("computer_use_advisor", phase="returned", advice_kind=advice.kind,
                        call_number=self.advisor_calls, observation_id=snapshot.observation_id)
        self.last_review_action = len(self.progress.verified_actions)
        return advice

    @staticmethod
    def candidate(actions: ActionSet, candidate_id: str | None) -> Action:
        for action in actions.actions:
            if action.id == candidate_id:
                return action
        raise SubAgentStopped("invalid_candidate")
