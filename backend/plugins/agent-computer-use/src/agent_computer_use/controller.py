"""Task-owned host loop. Channels provide evidence, never completion claims."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from typing import Literal, Protocol
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
    GENERIC_CONDITIONS,
    Action,
    ActionSet,
    ActionDetails,
    AdvisorResult,
    Binding,
    DecisionResult,
    DispatchReceipt,
    ExecutionStep,
    Fact,
    FocusProposal,
    GoalContract,
    GoalProgress,
    ObservedChange,
    PlanningFocus,
    SelectionSource,
    Snapshot,
    Target,
    TargetBinding,
    TargetUnavailable,
    plain_text,
    progress_json,
)
from .intake import TaskBrief, align_completion, goal_from_brief


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


class TargetBinder(Protocol):
    async def bind(
        self, target: Target, scope: str, context: SubAgentContext, /,
    ) -> TargetBinding: ...


class Intake(Protocol):
    async def read(
        self, request: SubAgentRequest, application: str | None, context: SubAgentContext, /,
    ) -> TaskBrief | str: ...


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


def _occurrences(snapshot: Snapshot, kind: str, expected: str) -> int:
    if kind == "ax:title:":
        titles = {e.ancestors[0][1] for e in snapshot.elements
                  if e.ancestors and e.ancestors[0][0] == "AXWindow"}
        return int(len(titles) == 1 and expected in plain_text(titles.pop()))
    # Labels name controls; only values show what the task produced.
    return sum(plain_text(text) == expected for e in snapshot.elements
               for text in ((e.value,) if kind == "ax:present:" else (e.value, e.label)))


def _generic_holds(snapshot: Snapshot, baseline: Snapshot | None, condition: Fact) -> bool:
    if baseline is None:
        return False
    kind = next(p for p in GENERIC_CONDITIONS if condition.key.startswith(p))
    expected = plain_text(condition.value)
    before, now = (_occurrences(s, kind, expected) for s in (baseline, snapshot))
    if kind == "ax:absent:":
        return before > 0 and now == 0
    return before == 0 and now == 1


def achieved(
    snapshot: Snapshot, predicates: tuple[Fact, ...], baseline: Snapshot | None = None,
) -> bool:
    facts = {fact.key: fact.value for fact in snapshot.facts}
    return (
        snapshot.ready
        and snapshot.complete
        and all(_generic_holds(snapshot, baseline, predicate)
                if predicate.key.startswith(GENERIC_CONDITIONS)
                else facts.get(predicate.key) == predicate.value
                for predicate in predicates)
    )


def effect_achieved(
    snapshot: Snapshot, action: Action, detail: ActionDetails, generation: int,
) -> bool:
    if not snapshot.ready or not snapshot.complete:
        return False
    values = {element.ref: element.value for element in snapshot.elements}
    if action.operation == "fill":
        return action.target_ref in values and values[action.target_ref] == action.value
    if detail.effect:
        return achieved(snapshot, detail.effect)
    if detail.changes:
        facts = {fact.key: fact.value for fact in snapshot.facts}
        return any(change.source_ref in values and change.key in facts
                   and values[change.source_ref] == facts[change.key] != change.before
                   for change in detail.changes)
    return detail.observable and snapshot.generation > generation


@dataclass(frozen=True)
class ActionAttempt:
    binding: Binding
    action: Action
    detail: ActionDetails
    before: Snapshot
    selected_by: SelectionSource


class ComputerUseController:
    """Single task instance; budgets and authorization remain in the supplied context."""

    def __init__(
        self,
        source: ObservationSource,
        executor: ActionExecutor,
        *,
        selector: Selector | None = None,
        advisor: Advisor | None = None,
        binder: TargetBinder | None = None,
        intake: Intake | None = None,
        completion_keys: frozenset[str] | None = None,
        max_candidates: int = 32,
    ) -> None:
        self.source, self.executor = source, executor
        self.selector, self.advisor, self.binder, self.intake = selector, advisor, binder, intake
        self.brief: TaskBrief | None = None
        self.target: TargetBinding | None = None
        self.completion_keys = completion_keys
        self.baselines: dict[str | None, Snapshot] = {}
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
        self.dispatch: TaskOperation[ActionAttempt, DispatchReceipt] | None = None
        self.binding: TaskOperation[tuple[Target, str], TargetBinding] | None = None

    def result(self, status: TaskStatus, reason: str) -> TaskResult:
        self.finish_focus("invalidated", reason)
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
                "progress": progress_json(self.progress),
                **({"target": {"bundle_id": self.target.bundle_id, "launched": self.target.launched}}
                   if self.target is not None else {}),
                **({"intake": self.brief.model_dump(mode="json")} if self.brief is not None else {}),
            },
        )

    async def observe(
        self, goal: GoalContract, context: SubAgentContext,
    ) -> Snapshot:
        assert self.observation is not None
        # Bounded timing/count events only; never element data or labels.
        context.observe("computer_use_observe", phase="started")
        started = time.monotonic()
        snapshot = await context.runtime.execute(self.observation, goal.scope)
        context.observe(
            "computer_use_observe", phase="returned",
            elapsed_ms=(time.monotonic() - started) * 1000,
            elements=len(snapshot.elements), facts=len(snapshot.facts),
            ready=snapshot.ready, complete=snapshot.complete)
        if snapshot.scope != goal.scope:
            raise SubAgentStopped("scope_mismatch")
        if snapshot.observation_id in self.observation_ids or snapshot.generation < self.generation:
            raise SubAgentStopped("stale_observation")
        self.observation_ids.add(snapshot.observation_id)
        self.generation = snapshot.generation
        if not snapshot.ready or not snapshot.complete:
            self.finish_focus("invalidated", "observation_unavailable", snapshot)
        elif (self.target is not None and self.target.generic_conditions
                and snapshot.window not in self.baselines
                # The bound window's baseline predates any action; later windows start when first seen.
                and (self.baselines or not self.receipts)):
            self.baselines[snapshot.window] = snapshot
        return snapshot

    def holds(self, snapshot: Snapshot, predicates: tuple[Fact, ...]) -> bool:
        return achieved(snapshot, predicates, self.baselines.get(snapshot.window))

    def register_operations(self, context: SubAgentContext) -> None:
        async def preflight(value: ActionAttempt) -> None:
            if not await self.executor.is_current(value.binding, value.action, context):
                raise SubAgentStopped("stale_reference")

        async def dispatch(value: ActionAttempt) -> DispatchReceipt:
            binding, action = value.binding, value.action
            # Journal at the admitted boundary, before a possible external effect.
            self.bindings.append(binding)
            self.receipts.append(DispatchReceipt(action.id, "unknown"))
            self.pending_effect = True
            step = ExecutionStep(
                len(self.receipts), action.id, action.operation, value.detail.role,
                value.detail.label, value.detail.ancestors, action.value, value.selected_by,
                value.before.observation_id,
            )
            self.progress = replace(self.progress, recent_action=action, pending_action=action,
                                    recent_steps=(*self.progress.recent_steps[-9:], step))
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
        if self.binder is not None:
            binder = self.binder
            self.binding = TaskOperation(
                "computer_use.bind", frozenset({"desktop"}), "action",
                lambda value: binder.bind(*value, context),
            )
            context.runtime.register(self.binding)

    def record_result(
        self, attempt: ActionAttempt, receipt: DispatchReceipt,
        after: Snapshot | None = None, *, verified: bool = False,
    ) -> None:
        changes: list[ObservedChange] = []
        if after is not None and after.ready and after.complete:
            if attempt.action.operation == "fill":
                before_values = {e.ref: e.value for e in attempt.before.elements}
                after_values = {e.ref: e.value for e in after.elements}
                ref = attempt.action.target_ref
                if ref in before_values and ref in after_values and before_values[ref] != after_values[ref]:
                    changes.append(ObservedChange("target_value", before_values[ref], after_values[ref]))
            else:
                before_facts = {fact.key: fact.value for fact in attempt.before.facts}
                after_facts = {fact.key: fact.value for fact in after.facts}
                keys = dict.fromkeys((*[fact.key for fact in attempt.detail.effect],
                                      *[change.key for change in attempt.detail.changes]))
                changes.extend(ObservedChange(key, before_facts.get(key), after_facts.get(key))
                               for key in keys if before_facts.get(key) != after_facts.get(key))
        step = replace(
            self.progress.recent_steps[-1], dispatch_status=receipt.status,
            effect_status="not_sent" if receipt.status == "not_sent" else "verified" if verified else "unknown",
            observation_after=after.observation_id if after is not None else None,
            changes=tuple(changes),
        )
        self.progress = replace(self.progress, recent_steps=(*self.progress.recent_steps[:-1], step))

    def finish_focus(
        self, status: Literal["completed", "invalidated"], reason: str, snapshot: Snapshot | None = None,
    ) -> None:
        focus = self.progress.current_focus
        if focus is not None:
            finished = replace(focus, status=status, reason=reason,
                               final_observation_id=snapshot.observation_id if snapshot else None)
            self.progress = replace(self.progress, current_focus=None,
                                    focus_history=(*self.progress.focus_history, finished))

    def check_focus(self, snapshot: Snapshot) -> str | None:
        focus = self.progress.current_focus
        if focus is None:
            return None
        if focus.goal_version != self.version or focus.scope != snapshot.scope:
            self.finish_focus("invalidated", "goal_changed", snapshot)
            return "focus_invalidated"
        if self.holds(snapshot, focus.proposal.completion):
            self.finish_focus("completed", "focus_verified", snapshot)
        elif len(self.receipts) - focus.started_action >= 3:
            self.finish_focus("invalidated", "action_limit", snapshot)
            return "focus_expired"
        return None

    def adopt_focus(self, proposal: FocusProposal | None, goal: GoalContract,
                    snapshot: Snapshot, actions: ActionSet) -> None:
        if not isinstance(proposal, FocusProposal):
            raise SubAgentStopped("invalid_focus")
        try:
            proposal = FocusProposal.model_validate_json(proposal.model_dump_json())
        except ValueError:
            raise SubAgentStopped("invalid_focus") from None
        keys = {fact.key for fact in (*snapshot.facts, *goal.completion)}
        keys.update(fact.key for outcome in goal.outcomes for fact in outcome.conditions)
        keys.update(fact.key for detail in actions.details for fact in detail.effect)
        keys.update(change.key for detail in actions.details for change in detail.changes)
        if (not snapshot.ready or not snapshot.complete or actions.truncated
                or any(fact.key not in keys for fact in proposal.completion)):
            raise SubAgentStopped("unsupported_focus_evidence")
        if self.holds(snapshot, proposal.completion):
            raise SubAgentStopped("focus_already_satisfied")
        if self.selector is None:
            raise SubAgentStopped("focus_selector_unavailable")
        self.finish_focus("invalidated", "replaced", snapshot)
        self.progress = replace(self.progress, current_focus=PlanningFocus(
            self.advisor_calls, proposal, goal.scope, self.version, len(self.receipts), snapshot.observation_id))

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
            task_input = dict(request.task_input or {})
            target_input = task_input.pop("target", None)
            try:
                target = None if target_input is None else Target.from_input(target_input)
            except (ValueError, ValidationError):
                return self.result("needs_input", "invalid_target")
            if self.intake is not None and not task_input:
                brief = await self.intake.read(
                    request, None if target is None else target.application, context)
                if isinstance(brief, str):
                    return self.result("needs_input", brief)
                try:
                    goal = goal_from_brief(brief, request.task)
                except ValueError:
                    raise SubAgentStopped("invalid_intake") from None
                self.brief = brief
                target = target or Target(application=brief.application)
            elif request.task_input is None:
                return self.result("needs_input", "goal_contract_required")
            else:
                try:
                    goal = GoalContract.from_input(task_input)
                except (ValueError, ValidationError):
                    return self.result("needs_input", "invalid_goal_contract")
            if (target is None) != (self.binder is None):
                return self.result("needs_input", "target_required" if target is None else "invalid_target")
            if goal.authorization_ref not in {"current_task", request.task_id}:
                raise SubAgentStopped("authorization_mismatch")
            self.goal_id = goal.goal_id
            if target is not None:
                assert self.binding is not None
                self.target = await context.runtime.execute(self.binding, (target, goal.scope))
                self.completion_keys = self.target.completion_keys
                if self.brief is not None:
                    goal = align_completion(goal, self.target.completion_keys)
            return await self.loop(request, goal, context)
        except TargetUnavailable as exc:
            return self.result("needs_input", exc.reason)
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
        def supported(key: str) -> bool:
            if self.completion_keys is None:
                return key.startswith("status:")
            return key in self.completion_keys or (
                self.target is not None and self.target.generic_conditions
                and key.startswith(GENERIC_CONDITIONS))

        if not all(supported(fact.key) for fact in goal.completion):
            return self.result("needs_input", "unsupported_completion_evidence")
        snapshot = await self.observe(goal, context)
        visited: dict[tuple[object, ...], int] = {}
        seen_evidence: set[tuple[str, str, str]] = set()
        incomplete_retries = 0
        while True:
            context.check("desktop")
            focus_reason = self.check_focus(snapshot)
            # A changed readout is a local effect, not evidence of goal advancement.
            conditions = (*goal.completion, *(f for item in goal.outcomes for f in item.conditions))
            markers = {("fact", f.key, f.value) for f in conditions
                       if self.holds(snapshot, (f,))}
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
                    if (set(item.depends_on) <= outcomes
                            and self.holds(snapshot, item.conditions)):
                        outcomes.add(item.id)
            self.progress = replace(self.progress, verified_outcomes=tuple(sorted(outcomes)))
            if (self.holds(snapshot, goal.completion)
                    and len(outcomes) == len(goal.outcomes)):
                self.evidence.append({"observation_id": snapshot.observation_id,
                                      "goal_version": self.version,
                                      "completion": [item.key for item in goal.completion]})
                return self.result("completed", "goal_verified")
            state = (self.version,
                self.progress.current_focus.revision if self.progress.current_focus else 0,
                snapshot.ready, snapshot.complete,
                tuple((e.role, e.label, e.ancestors, e.value, e.enabled, e.actions)
                      for e in snapshot.elements), snapshot.facts,
            )
            repeated = state in visited
            if repeated and not snapshot.complete and incomplete_retries < 20:
                incomplete_retries += 1
                await asyncio.sleep(0.05)
                snapshot = await self.observe(goal, context)
                continue
            if repeated:
                self.finish_focus("invalidated", "repeated_state", snapshot)
                self.progress = replace(self.progress, no_progress=self.progress.no_progress + 1)
                if not snapshot.ready:
                    # A channel that never produced a usable observation is
                    # unavailable, not merely unchanged; keep the honest reason.
                    return self.result("stopped", "observation_unavailable")
                if (self.advisor is None
                        or visited[state] == len(self.progress.verified_actions)):
                    return self.result("stopped", "no_progress")
            if snapshot.complete:
                incomplete_retries = 0
            visited[state] = len(self.progress.verified_actions)
            actions = replace(self.builder.build(self.goal_id, self.version, goal, snapshot,
                                                        self.progress),
                              progress=self.progress)
            if repeated:
                actions = replace(actions, reason="repeated_state")
            elif focus_reason is not None:
                actions = replace(actions, reason=focus_reason)
            elif (self.progress.unverified_goal_steps >= 3
                    and len(self.progress.verified_actions) - self.last_review_action >= 3):
                actions = replace(actions, reason="goal_progress_unverified")
            context.observe("computer_use_route", goal_id=self.goal_id, goal_version=self.version,
                            observation_id=snapshot.observation_id, reason=actions.reason)
            action = actions.actions[0] if actions.reason == "rules_unique" else None
            selected_by: SelectionSource = "rules"
            if actions.reason == "jev_eligible" and self.selector is not None:
                context.check("desktop")
                decision = await self.selector.choose(goal, snapshot, actions, context)
                context.check("desktop")
                if decision.binding != actions.binding:
                    raise SubAgentStopped("stale_decision")
                if decision.choice == "candidate":
                    action = self.candidate(actions, decision.candidate_id)
                    selected_by = "selector"
                elif decision.choice not in {"none", "ambiguous", "need_more_context", "escalate"}:
                    raise SubAgentStopped("invalid_decision")
                else:
                    if decision.choice in {"none", "escalate"}:
                        self.finish_focus("invalidated", decision.choice, snapshot)
                    actions = replace(actions, reason=decision.choice, progress=self.progress)
            if action is None:
                if any(item.value is None and item.source == "user" for item in goal.inputs):
                    return self.result("needs_input", "missing_user_input")
                if actions.reason == "none":
                    return self.result("stopped", "none")
                if actions.reason in {"need_more_context", "ambiguous"}:
                    snapshot = await self.observe(goal, context)
                    continue
                if actions.reason in {"observation_unavailable", "scope_incomplete"}:
                    if incomplete_retries >= 20:
                        return self.result("stopped", actions.reason)
                    incomplete_retries += 1
                    await asyncio.sleep(0.05)
                    snapshot = await self.observe(goal, context)
                    continue
                advice = await self.advise(request, goal, snapshot, actions, context)
                if advice is None:
                    return self.result("needs_input" if actions.reason == "missing_parameters"
                                       else "stopped", actions.reason)
                if advice.kind == "inputs":
                    self.finish_focus("invalidated", "goal_changed", snapshot)
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
                if advice.kind == "focus":
                    self.adopt_focus(advice.focus, goal, snapshot, actions)
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
                selected_by = "advisor"
            detail = next(item for item in actions.details if item.action_id == action.id)
            assert self.dispatch is not None
            attempt = ActionAttempt(actions.binding, action, detail, snapshot, selected_by)
            dispatch_started = time.monotonic()
            receipt = await context.runtime.execute(self.dispatch, attempt)
            context.observe(
                "computer_use_dispatch", phase="returned",
                elapsed_ms=(time.monotonic() - dispatch_started) * 1000,
                status=receipt.status, operation=action.operation,
                selected_by=selected_by)
            if receipt.action_id != action.id or receipt.status not in {"not_sent", "sent", "unknown"}:
                raise SubAgentStopped("invalid_receipt")
            self.receipts[-1] = receipt
            self.record_result(attempt, receipt)
            if receipt.status == "not_sent":
                self.pending_effect = False
                self.progress = replace(self.progress, pending_action=None)
                return self.result("stopped", "not_sent")
            for retry in range(3):
                if retry:
                    await asyncio.sleep(0.05)
                snapshot = await self.observe(goal, context)
                verified = effect_achieved(snapshot, action, detail, actions.binding.generation)
                self.record_result(attempt, receipt, snapshot, verified=verified)
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
            advice.kind not in {"inputs", "candidate", "focus", "need_observation", "needs_user_input", "unable"}
            or advice.kind != "inputs"
            and advice.inputs
            or advice.kind != "candidate"
            and advice.candidate_id is not None
            or (advice.kind == "focus") != (advice.focus is not None)
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
