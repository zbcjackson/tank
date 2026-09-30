"""Task-owned host loop. Channels provide evidence, never completion claims."""

from __future__ import annotations

import asyncio
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
    AdvisorResult,
    Binding,
    DecisionResult,
    DispatchReceipt,
    Fact,
    GoalContract,
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


class ComputerUseController:
    """Single task instance; budgets and authorization remain in the supplied context."""

    def __init__(
        self,
        source: ObservationSource,
        executor: ActionExecutor,
        *,
        selector: Selector | None = None,
        advisor: Advisor | None = None,
    ) -> None:
        self.source, self.executor = source, executor
        self.selector, self.advisor = selector, advisor
        self.version = 1
        self.goal_id = uuid4().hex
        self.task_id = ""
        self.evidence: list[JsonValue] = []
        self.bindings: list[Binding] = []
        self.completed: list[str] = []
        self.receipts: list[DispatchReceipt] = []
        self.pending_effect = False
        self.observation_ids: set[str] = set()
        self.generation = -1
        self.advisor_calls = 0
        self.started = False
        self.observation: TaskOperation[str, Snapshot] | None = None
        self.dispatch: TaskOperation[tuple[Binding, Action], DispatchReceipt] | None = None

    def result(self, status: TaskStatus, reason: str) -> TaskResult:
        if self.pending_effect:
            status = "unknown"
        elif status == "stopped" and self.completed:
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
                "milestones": list(self.completed),
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
            },
        )

    async def observe(self, goal: GoalContract, context: SubAgentContext) -> Snapshot:
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
        advice = await self.advisor.assist(request, goal, snapshot, actions, context)
        context.check("desktop")
        if advice.binding != actions.binding:
            raise SubAgentStopped("stale_advice")
        if (
            advice.kind != "inputs"
            and advice.inputs
            or advice.kind != "candidate"
            and advice.candidate_id is not None
        ):
            raise SubAgentStopped("invalid_advice")
        return advice

    async def loop(
        self,
        request: SubAgentRequest,
        goal: GoalContract,
        context: SubAgentContext,
        /,
    ) -> TaskResult:
        snapshot = await self.observe(goal, context)
        index = 0
        selected_states: set[tuple[object, ...]] = set()
        for _ in range(100):
            context.check("desktop")
            if index == len(goal.milestones):
                if achieved(snapshot, goal.completion):
                    return self.result("completed", "goal_verified")
                return self.result("unknown", "completion_unverified")
            milestone = goal.milestones[index]
            if achieved(snapshot, (milestone.postcondition,)):
                self.evidence.append(
                    {
                        "milestone": milestone.id,
                        "observation_id": snapshot.observation_id,
                        "generation": snapshot.generation,
                        "predicate_key": milestone.postcondition.key,
                    }
                )
                self.completed.append(milestone.id)
                index += 1
                continue
            actions = ActionBuilder().build(self.goal_id, self.version, goal, milestone, snapshot)
            context.observe(
                "computer_use_route",
                goal_id=self.goal_id,
                goal_version=self.version,
                observation_id=snapshot.observation_id,
                reason=actions.reason,
            )
            action = actions.actions[0] if actions.reason == "rules_unique" else None
            selection_state = (
                self.version,
                index,
                snapshot.generation,
                snapshot.elements,
                snapshot.facts,
            )
            if (
                actions.reason == "jev_eligible"
                and self.selector is not None
                and selection_state not in selected_states
            ):
                selected_states.add(selection_state)
                context.check("desktop")
                decision = await self.selector.choose(goal, snapshot, actions, context)
                context.check("desktop")
                if decision.binding != actions.binding:
                    raise SubAgentStopped("stale_decision")
                if decision.choice == "candidate":
                    action = self.candidate(actions, decision.candidate_id)
                elif decision.choice not in {"none", "ambiguous", "need_more_context", "escalate"}:
                    raise SubAgentStopped("invalid_decision")
            if action is None:
                advice = await self.advise(request, goal, snapshot, actions, context)
                if advice is None:
                    status: TaskStatus = (
                        "needs_input" if actions.reason == "missing_parameters" else "stopped"
                    )
                    return self.result(status, actions.reason)
                if advice.kind == "inputs":
                    missing = {item.input_key for item in goal.milestones if item.input_key}
                    missing -= {item.key for item in goal.inputs}
                    if (
                        not advice.inputs
                        or len({item.key for item in advice.inputs}) != len(advice.inputs)
                        or any(item.key not in missing for item in advice.inputs)
                    ):
                        raise SubAgentStopped("invalid_goal_patch")
                    goal = GoalContract.from_input(
                        {
                            **goal.model_dump(mode="json"),
                            "inputs": [
                                item.model_dump() for item in (*goal.inputs, *advice.inputs)
                            ],
                        }
                    )
                    self.version += 1
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
            assert self.dispatch is not None
            receipt = await context.runtime.execute(self.dispatch, (actions.binding, action))
            if receipt.action_id != action.id or receipt.status not in {
                "not_sent",
                "sent",
                "unknown",
            }:
                raise SubAgentStopped("invalid_receipt")
            self.receipts[-1] = receipt
            if receipt.status == "not_sent":
                self.pending_effect = False
                raise SubAgentStopped("not_sent")
            # Only bounded readback is permitted while an effect is unresolved.
            for _ in range(2):
                snapshot = await self.observe(goal, context)
                if achieved(snapshot, (milestone.postcondition,)):
                    self.pending_effect = False
                    break
            if self.pending_effect:
                return self.result("unknown", "effect_unknown")
        return self.result("stopped", "no_progress")

    @staticmethod
    def candidate(actions: ActionSet, candidate_id: str | None) -> Action:
        for action in actions.actions:
            if action.id == candidate_id:
                return action
        raise SubAgentStopped("invalid_candidate")
