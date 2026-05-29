"""Pin the explore-plan-act phase shape in the main agent's system prompt.

Per the Workflow & Orchestration proposal (backend/ORCHESTRATION.md, Gap A'),
the main agent's system prompt teaches the explore-plan-act loop as a
phase shape — not a sub-agent, not a hard read-only gate.

These tests pin the prompt content so the shape doesn't drift. They
deliberately don't pin exact wording line-by-line; they assert the
phase markers and the simple-request short-circuit are present.
"""

from __future__ import annotations

from tank_backend.pipeline.processors.brain import Brain


def _prompt(agent_catalog: str = "") -> str:
    return Brain._build_main_agent_prompt(agent_catalog)


def test_prompt_includes_three_phase_markers() -> None:
    text = _prompt()
    assert "EXPLORE" in text, "missing EXPLORE phase marker"
    assert "PLAN" in text, "missing PLAN phase marker"
    assert "ACT" in text, "missing ACT phase marker"


def test_prompt_mentions_parallel_explore() -> None:
    text = _prompt()
    # The point of EXPLORE is parallel read-only lookups; if this regresses,
    # voice latency regresses with it.
    assert "parallel" in text.lower()


def test_prompt_short_circuits_simple_requests() -> None:
    text = _prompt().lower()
    # The simple-request override is what keeps "what time is it" from
    # paying the planning tax.
    assert "simple" in text
    assert "act" in text  # the phase to skip to


def test_prompt_does_not_promise_a_plan_subagent() -> None:
    """Planning is a phase, not a sub-agent.

    Reifying planning into a sub-agent would commit Tank to migrating it
    out of the executor when the chat-agent split lands. Phase 1 stays as
    inline reasoning; the prompt should not advertise a 'planner' agent.
    """
    text = _prompt().lower()
    assert "planner" not in text
    assert "plan_enter" not in text
    assert "plan_exit" not in text


def test_prompt_appends_agent_catalog_when_provided() -> None:
    catalog = "- coder: Execute code\n- researcher: Search the web"
    text = _prompt(catalog)
    assert "Available agents:" in text
    assert catalog in text


def test_prompt_omits_catalog_section_when_empty() -> None:
    text = _prompt("")
    assert "Available agents:" not in text
