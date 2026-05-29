"""Pin the concurrent-safe tool set used by the LLM streaming loop.

When the LLM emits multiple tool calls in one assistant turn, the loop
runs concurrent-safe tools in parallel via ``asyncio.gather``. Mutating
or stateful tools must stay sequential — this test pins both lists so
accidental additions of mutating tools fail loudly.
"""

from __future__ import annotations

from tank_backend.llm.llm import _CONCURRENT_SAFE_TOOLS, _is_concurrent_safe

# Read-only / pure-query tools that are safe to gather.
EXPECTED_CONCURRENT_SAFE = frozenset({
    "agent",
    "file_read", "file_list", "file_search",
    "web_search", "web_fetch",
    "get_weather", "get_time", "calculate",
    "get_user_memory", "get_context_usage",
})

# Tools that mutate filesystem, shell state, memory, channels, or the
# approval queue. These must NEVER appear in _CONCURRENT_SAFE_TOOLS.
MUTATING_TOOLS = frozenset({
    "file_write", "file_edit", "file_delete",
    "run_command", "persistent_shell", "manage_process",
    "confirm_action",
    "remember", "consolidate_memory", "compact_context",
})


def test_concurrent_safe_set_matches_expected() -> None:
    assert _CONCURRENT_SAFE_TOOLS == EXPECTED_CONCURRENT_SAFE


def test_mutating_tools_are_not_concurrent_safe() -> None:
    overlap = _CONCURRENT_SAFE_TOOLS & MUTATING_TOOLS
    assert overlap == frozenset(), (
        f"Mutating tools must not be concurrent-safe: {sorted(overlap)}"
    )


def test_is_concurrent_safe_helper_agrees() -> None:
    for name in EXPECTED_CONCURRENT_SAFE:
        assert _is_concurrent_safe(name), f"{name} should be concurrent-safe"
    for name in MUTATING_TOOLS:
        assert not _is_concurrent_safe(name), f"{name} must NOT be concurrent-safe"
    # Unknown tool names default to sequential.
    assert not _is_concurrent_safe("totally_made_up_tool")
