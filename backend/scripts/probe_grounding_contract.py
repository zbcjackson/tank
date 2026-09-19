"""Probe coordinate hypotheses using generated images only; no desktop input.

From backend: uv run python scripts/probe_grounding_contract.py --output /tmp/probe-new
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import time
from pathlib import Path

os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from tank_backend.benchmarks.grounding_probe import response_point, score_point
from tank_backend.config.app_config import AppConfig
from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.llm.llm import _build_follow_up_user_message
from tank_backend.llm.profile import create_llm_from_profile
from tank_backend.tools.computer_use_common import COORDINATE_NOTE
from tank_backend.tools.computer_use_macos import ClickTool

ROOT = Path(__file__).resolve().parents[1]


def scene(size: tuple[int, int], position: tuple[float, float]):
    image = Image.new("RGB", size, "#25272c")
    draw = ImageDraw.Draw(image)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    small = ImageFont.truetype(font_path, 13)
    for row in range(size[1] // 18):
        draw.text((3, row * 18), f"Synthetic calibration log {row:03d} generated background only",
                  font=small, fill="#cccccc")
    width = min(672, int(size[0] * .7))
    scale = width / 672
    height = round(407 * scale)
    left = round((size[0] - width) * position[0])
    top = round((size[1] - height) * position[1])
    draw.rounded_rectangle((left, top, left + width, top + height),
                           radius=round(22 * scale), fill="#302d31")
    font = ImageFont.truetype(font_path, round(24 * scale))
    draw.text((left + width - 52, top + 65 * scale), "35", font=font, fill="white")
    labels = [
        ["(", ")", "mc", "m+", "m-", "mr", "DEL", "AC", "%", "/"],
        ["2nd", "x2", "x3", "xy", "ex", "10x", "7", "8", "9", "x"],
        ["1/x", "sqrt", "cbrt", "root", "ln", "log", "4", "5", "6", "-"],
        ["x!", "sin", "cos", "tan", "e", "EE", "1", "2", "3", "+"],
        ["Rand", "sinh", "cosh", "tanh", "pi", "Rad", "+/-", "0", ".", "="],
    ]
    targets = {}
    for row, labels_row in enumerate(labels):
        for col, label in enumerate(labels_row):
            x = left + round((39 + 66 * col) * scale)
            y = top + round((156 + 54 * row) * scale)
            rx, ry = round(30 * scale), round(24 * scale)
            draw.rounded_rectangle((x-rx, y-ry, x+rx, y+ry), radius=round(22*scale),
                                   fill="#ee9900" if col == 9 else "#555257")
            draw.text((x, y), label, font=font, fill="white", anchor="mm")
            if label in ("AC", "7"):
                targets[label] = (x, y)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), targets


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--point-only", action="store_true",
                        help="Diagnostic control: advertise x/y only, without bbox/oneOf")
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    load_dotenv(ROOT / "core/.env")
    profile = AppConfig.load(ROOT / "core/config.yaml").get_llm_profile("computer_use")
    llm = create_llm_from_profile(profile)
    llm.client.max_retries = 0
    prompt = (ROOT / "agents/computer_use.md").read_text().split("---", 2)[2].strip()
    tool = ClickTool()
    schema = {"type": "function", "function": {"name": "click",
              "description": tool.get_info().description, "parameters": tool.get_raw_schema()}}
    if args.point_only:
        schema["function"]["parameters"] = {
            "type": "object", "properties": {
                "x": {"type": "integer", "minimum": 0, "maximum": 1000},
                "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            }, "required": ["x", "y"], "additionalProperties": False,
        }
    report = {"model": profile.model, "prompt": prompt, "schema": schema,
              "coordinate_note": COORDINATE_NOTE, "results": []}
    try:
        for size in [(1920, 1080), (1280, 720), (1080, 1920), (1000, 1000)]:
            for placement, position in enumerate([(.1, .15), (.85, .8)]):
                png, targets = scene(size, position)
                name = f"{size[0]}x{size[1]}-{placement}.png"
                (args.output / name).write_bytes(png)
                digest = hashlib.sha256(png).hexdigest()
                blocks = [TextBlock(text=COORDINATE_NOTE), ImageBlock(
                    source="data:image/png;base64," + base64.b64encode(png).decode(),
                    mime_type="image/png")]
                for repeat in range(args.repeats):
                    for target, center in targets.items():
                        question = (f"Locate the Calculator button labeled {target}. Call click once "
                                    "at its center, using full-screen normalized coordinates. "
                                    "Do not call any other tool.")
                        messages = [{"role": "system", "content": prompt},
                                    {"role": "user", "content": question},
                                    _build_follow_up_user_message("probe", "screenshot", blocks)]
                        requests = []
                        async def on_request(request):
                            body = json.loads(request.content)
                            urls = [p["image_url"]["url"] for m in body["messages"]
                                    if isinstance(m.get("content"), list) for p in m["content"]
                                    if p.get("type") == "image_url"]
                            hashes = [hashlib.sha256(base64.b64decode(u.split(",", 1)[1])).hexdigest()
                                      for u in urls]
                            assert hashes == [digest]
                            requests.append({"sha256": hashes, "model": body["model"],
                                             "temperature": body.get("temperature")})
                        llm.client._client.event_hooks["request"] = [on_request]
                        row = {"image": name, "size": size, "target": target, "center": center,
                               "repeat": repeat, "sha256": digest, "question": question,
                               "calls": [], "requests": requests}
                        started = time.monotonic()
                        try:
                            async with asyncio.timeout(60):
                                async for kind, content, meta in llm.chat_stream(
                                    messages, tools=[schema], max_tokens=4000,
                                ):
                                    if kind.name == "MESSAGE":
                                        for call in meta.get("message", {}).get("tool_calls", []):
                                            fn = call["function"]
                                            observed = {"name": fn["name"], "raw": fn["arguments"]}
                                            try:
                                                arguments = json.loads(fn["arguments"])
                                                point = response_point(arguments) if isinstance(arguments, dict) else None
                                            except json.JSONDecodeError:
                                                point = None
                                            if fn["name"] == "click" and point is not None:
                                                observed["point"] = point
                                                observed["errors"] = score_point(point, size, center)
                                            row["calls"].append(observed)
                                    if kind.name == "USAGE":
                                        row["usage"] = meta
                        except Exception as exc:
                            row["error"] = type(exc).__name__ + ": " + str(exc)[:200]
                        row["seconds"] = round(time.monotonic() - started, 2)
                        report["results"].append(row)
                        (args.output / "results.json").write_text(json.dumps(report, indent=2))
                        print(json.dumps(row), flush=True)
    finally:
        await llm.client.close()


if __name__ == "__main__":
    asyncio.run(main())
