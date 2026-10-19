"""Explicit finite-candidate Jev image selection and bounded candidate review."""

import asyncio
from dataclasses import replace
from typing import cast

from tank_backend.agents.subagent import SubAgentContext, SubAgentRequest, SubAgentStopped
from tank_backend.llm.model_call import model_purpose

from .contracts import ActionSet, AdvisorResult, DecisionResult, GoalContract, Snapshot
from .jev import check_eligible
from .jev_image import normalize_frame
from .model_selector import ModelSelector
from .model_view import candidate_aliases, decision_question
from .visual_selector import VisualSelector


class JevImageSelector(VisualSelector):
    async def choose(self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
                     context: SubAgentContext) -> DecisionResult:
        if actions.reason not in {"jev_eligible", "visual_required", "repeated_state"}:
            raise SubAgentStopped("ineligible_decision")
        return await self.decide(goal, snapshot, actions, context, review=False)

    async def decide(self, goal: GoalContract, snapshot: Snapshot, actions: ActionSet,
                     context: SubAgentContext, *, review: bool) -> DecisionResult:
        ModelSelector.check(context)
        check_eligible(goal, snapshot, replace(actions, reason="jev_eligible"))
        if any(item.value is None and item.source == "user" for item in goal.inputs):
            raise SubAgentStopped("missing_user_input")
        model = context.runtime.decision_model
        if model is None or not model.images_enabled:
            raise SubAgentStopped("decision_images_denied")
        previous = await self.capture_frame(snapshot, actions, context)
        for _ in range(2):
            await asyncio.sleep(0.1)
            ModelSelector.check(context)
            captured = await self.capture_frame(snapshot, actions, context)
            if (captured.frame.image_sha256 == previous.frame.image_sha256
                    and captured.frame.image_size == previous.frame.image_size
                    and captured.frame.window_bounds == previous.frame.window_bounds):
                break
            previous = captured
        else:
            raise SubAgentStopped("unstable_visual_frame")
        try:
            image = normalize_frame(captured)
        except (ValueError, OSError):
            raise SubAgentStopped("invalid_visual_frame") from None
        # Native and managed-browser adapters capture upright PNGs. Other image
        # orientations remain supported by the read-only probe, not this executor.
        if image.orientation != 1:
            raise SubAgentStopped("unsupported_visual_orientation")
        left, top, right, bottom = image.content
        sx = (right - left) / captured.frame.image_size[0]
        sy = (bottom - top) / captured.frame.image_size[1]
        bounds = dict(captured.bounds)
        candidates = candidate_aliases(actions)
        packet = decision_question(goal, snapshot, actions)
        state = cast(dict[str, object], packet["state"])
        state.update(image_candidates={
            alias: [left + bounds[action.target_ref][0] * sx,
                    top + bounds[action.target_ref][1] * sy,
                    bounds[action.target_ref][2] * sx, bounds[action.target_ref][3] * sy]
            for alias, action in candidates.items()}, image_metadata=image.metadata(),
            selection_reason=actions.reason)
        question = cast(dict[str, dict[str, object]], packet["questions"])["next_action"]
        instructions = str(question["instructions"]) + (
            " Image evidence is available in state.image. image_candidates gives each offered "
            "alias [x,y,width,height] in pixels of that attached image; snapshot bounds are "
            "source-observation geometry, not normalized image coordinates. "
            "Use the image to resolve visible semantics. "
            + ("Review recent attempts against the original goal before choosing the next action. "
               if review else "")
        )
        with model_purpose("computer_use.jev_image_review" if review else "computer_use.jev_image"):
            result = await model.choose_image(state=state, image=image.asset,
                instructions=instructions, options=cast(dict[str, object], question["criteria"]))
        ModelSelector.check(context)
        context.observe("computer_use_decision", source="jev_image", confidence=result.confidence,
            probabilities=result.probabilities, candidates=len(candidates),
            candidate_set_id=actions.binding.candidate_set_id)
        if result.choice in ("none", "ambiguous", "need_more_context", "escalate"):
            return DecisionResult(actions.binding, result.choice, confidence=result.confidence,
                                  probabilities=tuple(result.probabilities.items()))
        action = candidates.get(result.choice)
        if action is None:
            raise SubAgentStopped("invalid_decision")
        context.observe("computer_use_proposal", source="jev_image", model_choice=result.choice,
            action_id=action.id, candidate_set_id=actions.binding.candidate_set_id,
            frame_id=captured.frame.frame_id, image_sha256=image.metadata()["image_sha256"])
        return DecisionResult(actions.binding, "candidate", action.id, result.confidence,
                              tuple(result.probabilities.items()))

    async def assist(self, request: SubAgentRequest, goal: GoalContract, snapshot: Snapshot,
                     actions: ActionSet, context: SubAgentContext) -> AdvisorResult:
        if any(item.value is None and item.source == "user" for item in goal.inputs):
            return AdvisorResult(actions.binding, "needs_user_input")
        if (actions.reason not in {"goal_progress_unverified", "repeated_state", "escalate"}
                or not actions.actions or actions.truncated):
            return AdvisorResult(actions.binding, "unable")
        result = await self.decide(goal, snapshot, actions, context, review=True)
        if result.choice == "candidate":
            return AdvisorResult(actions.binding, "candidate", candidate_id=result.candidate_id)
        return AdvisorResult(actions.binding, "need_observation" if result.choice in {
            "ambiguous", "need_more_context"} else "unable")
