"""Yutori wire protocol, isolated from Tank's shared LLM transport."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

TOOL_SET = "computer_use_tools-20260830"


def image_part(png: bytes) -> dict[str, Any]:
    with Image.open(io.BytesIO(png)) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, format="WEBP", quality=80)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{encoded}"}}


def tool_result(call_id: str, text: str, png: bytes | None = None) -> dict[str, Any]:
    parts = [{"type": "text", "text": text}]
    if png is not None:
        parts.append(image_part(png))
    return {"role": "tool", "tool_call_id": call_id, "content": parts}


def key_name(key: str) -> str:
    aliases = {"meta": "cmd", "super": "cmd", "command": "cmd", "esc": "escape"}
    aliases.update({"minus": "-", "plus": "shift+=", "equal": "=", "comma": ",",
                    "period": ".", "slash": "/", "backslash": "\\", "semicolon": ";",
                    "quote": "'", "backquote": "`", "bracketleft": "[", "bracketright": "]"})
    return "+".join(aliases.get(part, part) for part in key.lower().split("+"))
