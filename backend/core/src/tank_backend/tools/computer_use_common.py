"""Platform-agnostic input normalization for computer-use tools.

Models don't always emit the argument shapes the schema asks for. Two
forms showed up in the 2026-09-11 baseline traces and must be accepted
by BOTH platform backends:

- ``keys='["return"]'`` — a JSON-encoded array where a plain key string
  was declared (qwen);
- ``x=[100, 100, 200, 200]`` — a bbox quadruple where a point was
  declared (Qwen-VL emits 0-1000 bboxes natively; clicking a corner
  misses small targets).

All normalization lives here so Linux and macOS stay behaviorally
identical; platform files call these at tool entry.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from .base import BaseTool

# Canonical spellings for keys that models write inconsistently.
_KEY_SYNONYMS = {"return": "enter"}

# The key vocabulary key_press advertises (A4). Modifiers combine with
# '+'; single letters/digits are also valid (checked structurally).
CANONICAL_KEYS = frozenset({
    "enter", "tab", "escape", "backspace", "delete", "space",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    *(f"f{i}" for i in range(1, 13)),
    "cmd", "ctrl", "alt", "shift",
})

# Modifier translation per Linux backend: ydotool speaks libevdev names,
# pyautogui (X11 fallback) its own key list.
YDOTOOL_KEY_ALIASES = {"cmd": "meta", "win": "meta"}
PYAUTOGUI_KEY_ALIASES = {"cmd": "winleft", "win": "winleft"}


def _is_valid_key(part: str) -> bool:
    return part in CANONICAL_KEYS or (len(part) == 1 and part.isalnum())

# Appended to every screenshot result, identically on both platforms —
# the coordinate contract the models are told to follow.
COORDINATE_NOTE = (
    "When reporting element positions, use NORMALIZED coordinates "
    "on a 0-1000 scale where (0, 0) is the top-left corner and "
    "(1000, 1000) is the bottom-right corner. "
    "For example, the center of the screen is (500, 500). "
    "All coordinate tools (click, scroll, mouse_move) expect this "
    "0-1000 normalized format."
)


def normalized_to_pixel(
    nx: int, ny: int, size: tuple[int, int]
) -> tuple[int, int]:
    """Map a 0-1000 normalized point to pixel space for ``size``."""
    w, h = size
    return round(nx * (w - 1) / 1000), round(ny * (h - 1) / 1000)


# Coordinate parameter descriptions — identical strings on both platforms
# (a cross-platform consistency test pins this).
COORDINATE_X_DESCRIPTION = (
    "X coordinate (0-1000 normalized); a bbox array [x1,y1,x2,y2] is "
    "accepted (its center is used)"
)
COORDINATE_Y_DESCRIPTION = "Y coordinate (0-1000 normalized)"


def _as_part_list(raw: Any) -> str | None:
    """Coerce str/list input into a '+'-joined string (or None)."""
    if isinstance(raw, list):
        if not raw or not all(isinstance(k, str) for k in raw):
            return None
        joined = "+".join(raw)
    elif isinstance(raw, str):
        joined = raw.strip()
    else:
        return None
    if not joined:
        return None
    # Unwrap one level of JSON encoding: '["return"]' / '["cmd", "c"]'.
    # A bracket-wrapped string that isn't valid JSON is a mangled model
    # artifact, never a real key name — reject it outright.
    if joined.startswith("[") and joined.endswith("]"):
        try:
            parsed = json.loads(joined)
        except ValueError:
            return None
        if not (isinstance(parsed, list) and parsed):
            return None
        if not all(isinstance(k, str) for k in parsed):
            return None
        joined = "+".join(parsed)
    return joined


def normalize_keys(raw: Any) -> list[str] | None:
    """Normalize a key argument to a list of lowercase parts.

    Returns ``None`` when the input can't be interpreted or contains an
    unknown key name — callers turn that into an error result listing
    valid key names (models can then self-correct on the next turn).
    """
    joined = _as_part_list(raw)
    if joined is None:
        return None
    parts = [_KEY_SYNONYMS.get(p, p) for p in (s.strip().lower() for s in joined.split("+")) if p]
    if not parts or not all(_is_valid_key(p) for p in parts):
        return None
    return parts


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(v: Any) -> int | None:
    """Coerce int/float/numeric-string to int; None otherwise."""
    if _is_number(v):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except ValueError:
            return None
    return None


def _clamp(v: int) -> int:
    return max(0, min(1000, v))


def normalize_point(x: Any, y: Any) -> tuple[int, int] | None:
    """Normalize a coordinate argument to a clamped 0-1000 point.

    Accepted forms (observed across models):
    - ``(x: int, y: int)`` — declared shape (numeric strings tolerated);
    - ``x=[x1, y1]`` — a 2-element list (legacy macOS quirk);
    - ``x=[x1, y1, x2, y2]`` — a bbox (Qwen-VL native); its CENTER is used.

    Lists may arrive JSON-encoded as strings. Returns ``None`` otherwise.
    """
    seq: Any = x
    if isinstance(seq, str):
        try:
            seq = json.loads(seq)
        except ValueError:
            seq = None
    if isinstance(seq, (list, tuple)):
        nums = [_num(v) for v in seq[:4]]
        if any(n is None for n in nums) or len(seq) < 2:
            return None
        if len(seq) >= 4:
            x1, y1, x2, y2 = (cast(int, n) for n in nums)
            return _clamp((x1 + x2) // 2), _clamp((y1 + y2) // 2)
        px, py = cast(int, nums[0]), cast(int, nums[1])
        return _clamp(px), _clamp(py)
    nx, ny = _num(x), _num(y)
    if nx is None or ny is None:
        return None
    return _clamp(nx), _clamp(ny)


# ── A10: batch executor ───────────────────────────────────────────────

# Actions allowed inside a computer_batch (primitives + wait; screenshot
# is taken automatically by the batch itself, launch_app is one-shot).
BATCH_ACTIONS = frozenset({
    "click", "type_text", "key_press", "scroll", "mouse_move",
    "mouse_down", "mouse_up", "hold_key", "drag", "wait",
})

_WAIT_DEFAULT_S = 1.0
_WAIT_MAX_S = 5.0
_WAIT_MIN_S = 0.1


class ComputerBatchTool(BaseTool):
    """Execute a sequence of computer actions in one call.

    Dispatches to the platform tool instances passed at construction, so
    the class itself is platform-agnostic. Fails fast (first error stops
    the batch, remaining steps are reported as skipped) and captures one
    screenshot after the batch so the model sees the combined effect.
    """

    def __init__(self, tools: dict[str, Any]) -> None:
        self._tools = tools

    # -- BaseTool-compatible surface -----------------------------------

    def get_metadata(self) -> Any:
        from .base import ToolMetadata

        return ToolMetadata(category="computer")

    def get_info(self) -> Any:
        from .base import ToolInfo, ToolParameter

        return ToolInfo(
            name="computer_batch",
            description=(
                "Execute a sequence of computer actions in ONE call — much "
                "faster than one action per turn. Stops at the first failure "
                "and reports remaining steps as skipped. A screenshot of the "
                "final state is captured automatically after the batch."
            ),
            parameters=[
                ToolParameter(
                    name="actions",
                    type="array",
                    description=(
                        "Ordered action objects. Each has an 'action' field: "
                        "click(x,y), type_text(text), key_press(keys), "
                        "scroll(amount[,x,y]), mouse_move(x,y), "
                        "mouse_down(button), mouse_up(button), "
                        "hold_key(keys,duration_s), "
                        "drag(x1,y1,x2,y2), wait(delay_s). Coordinates use "
                        "the same 0-1000 normalized form as click."
                    ),
                ),
                ToolParameter(
                    name="screenshot",
                    type="boolean",
                    description="Capture a screenshot after the batch",
                    required=False,
                    default=True,
                ),
            ],
        )

    async def execute(
        self, actions: Any = None, screenshot: bool = True,
    ) -> Any:
        import json as json_mod

        from .base import ToolResult  # noqa: F811 — narrow for readers

        if not isinstance(actions, list) or not actions:
            return ToolResult(
                content="computer_batch: 'actions' must be a non-empty list",
                error=True,
            )

        steps: list[dict[str, Any]] = []
        failed_at: int | None = None
        skipped: list[str] = []
        for index, raw in enumerate(actions):
            if not isinstance(raw, dict):
                return ToolResult(
                    content=f"computer_batch: action #{index} is not an object",
                    error=True,
                )
            name = raw.get("action")
            if name not in BATCH_ACTIONS:
                return ToolResult(
                    content=(
                        f"computer_batch: unknown action {name!r} at #{index}; "
                        f"valid: {sorted(BATCH_ACTIONS)}"
                    ),
                    error=True,
                )
            if name == "wait":
                try:
                    raw_delay = float(raw.get("delay_s", _WAIT_DEFAULT_S))
                except (TypeError, ValueError):
                    raw_delay = _WAIT_DEFAULT_S
                delay = max(_WAIT_MIN_S, min(_WAIT_MAX_S, raw_delay))
                await asyncio.sleep(delay)
                steps.append({"action": "wait", "status": "ok", "detail": f"{delay}s"})
                continue
            tool = self._tools.get(name)
            if tool is None:
                return ToolResult(
                    content=f"computer_batch: action {name!r} unavailable on this platform",
                    error=True,
                )
            kwargs = {k: v for k, v in raw.items() if k != "action"}
            result = await tool.execute(**kwargs)
            failed = isinstance(result, ToolResult) and result.error
            steps.append({
                "action": name,
                "status": "error" if failed else "ok",
                "detail": result.content if failed else "",
            })
            if failed:
                failed_at = index
                skipped = [a.get("action", "?") for a in actions[index + 1:]]
                break

        shot_text = ""
        if screenshot and "screenshot" in self._tools:
            shot = await self._tools["screenshot"].execute(task="batch result")
            if isinstance(shot, ToolResult) and isinstance(shot.content, list):
                for block in shot.content:
                    text = getattr(block, "text", "")
                    if text:
                        shot_text = text
                        break

        ok = failed_at is None
        suffix = f" (failed at {failed_at})" if failed_at is not None else ""
        return ToolResult(
            content=json_mod.dumps({
                "steps": steps,
                "failed_at": failed_at,
                "skipped": skipped,
                "screenshot": shot_text,
            }, ensure_ascii=False),
            display=f"Batch: {len(steps)} steps{suffix}",
            error=not ok,
        )
